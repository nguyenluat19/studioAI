"""Admin-managed models stored in the DB (`app_models`).

The admin adds/edits models on the admin UI; every change is synced into the in-memory
model registry cache so the rest of the app (dropdowns, validation, pricing, pipeline)
picks it up without touching code or restarting the server.

Gateway protocol (same family as MiniMax-H3):
    video  -> POST {base_url}/v2/video_generation  (Bearer api_key, field "model" = model_name)
    llm/image -> POST {base_url}/chat/completions  (OpenAI-compatible chat, same as Inkstone)
"""
import ipaddress
import os
import re
import socket
import unicodedata
import urllib.parse

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import modelregistry
from .config import env_upsert, model_key_env, settings
from .db import SessionLocal
from .models import AppModel, PricingItem

STEPS_ALLOWED = ("llm", "image_generate", "video_i2v")
STEP_LABELS = {
    "llm": "LLM (tạo prompt/kịch bản)",
    "image_generate": "Gen ảnh",
    "video_i2v": "Gen video",
}


class AdminModelError(ValueError):
    pass


def _effective_key(row: AppModel) -> str:
    """API key lives in .env (MODEL_<ID>_API_KEY); legacy DB value is only a fallback."""
    return os.environ.get(model_key_env(row.id)) or (row.api_key or "")


def _spec(row: AppModel) -> modelregistry.ModelSpec:
    """Turn a DB row into the registry record the rest of the app consumes."""
    durations = _normalize_durations(row.supported_durations)
    if row.step == "video_i2v":
        return modelregistry.ModelSpec(
            row.id, row.name, "video_i2v", "custom", "api",
            desc=f"Model admin thêm ({row.base_url})",
            max_clip_seconds=max(1, row.max_clip_seconds),
            min_clip_seconds=1,
            resolutions=["768P"], supports_first_frame=True, supports_audio=False,
            price_unit="second", default_price=0.0, enabled=row.enabled,
            supported_durations=durations,
        )
    return modelregistry.ModelSpec(
        row.id, row.name, row.step, "custom", "api",
        desc=f"Model admin thêm ({row.base_url})",
        max_clip_seconds=0, price_unit="call", default_price=0.0, enabled=row.enabled,
    )


def sync(db: Session | None = None) -> None:
    """Reload admin models from the DB into the model registry cache.

    Also migrates any legacy key still stored in the DB row into .env
    (MODEL_<ID>_API_KEY) and clears the DB copy."""
    own = db is None
    if own:
        db = SessionLocal()
    try:
        rows = db.scalars(select(AppModel)).all()
        dirty = False
        for r in rows:
            if r.api_key:
                env_upsert(model_key_env(r.id), r.api_key)
                r.api_key = ""
                dirty = True
        if dirty:
            db.commit()
        modelregistry.set_dynamic_models([_spec(r) for r in rows])
    finally:
        if own:
            db.close()


def _normalize_durations(raw) -> list[int]:
    """Accept list or comma-separated string; return sorted unique positive ints."""
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = [p for p in re.split(r"[,;\s]+", raw.strip()) if p]
    else:
        parts = list(raw)
    out = []
    for p in parts:
        try:
            v = int(p)
        except (TypeError, ValueError):
            raise AdminModelError(f"Thời gian không hợp lệ: {p}")
        if v <= 0:
            raise AdminModelError(f"Thời gian phải > 0 giây: {v}")
        out.append(v)
    return sorted(set(out))


def _mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "•" * len(key)
    return key[:4] + "•" * (len(key) - 8) + key[-4:]


def to_dict(row: AppModel, price: float | None = None) -> dict:
    key = _effective_key(row)
    return {
        "id": row.id,
        "name": row.name,
        "step": row.step,
        "step_label": STEP_LABELS.get(row.step, row.step),
        "base_url": row.base_url,
        "api_key_masked": _mask(key),
        "has_key": bool(key),
        "model_name": row.model_name,
        "enabled": row.enabled,
        "max_clip_seconds": row.max_clip_seconds,
        "supported_durations": _normalize_durations(row.supported_durations),
        "price": price,
    }


def list_all(db: Session) -> list[dict]:
    rows = db.scalars(select(AppModel).order_by(AppModel.created_at, AppModel.id)).all()
    prices = {p.key: p.price for p in db.scalars(select(PricingItem)).all()}
    return [to_dict(r, prices.get(f"m.{r.id}")) for r in rows]


def creds(db: Session, model_id: str) -> dict | None:
    """Per-model gateway credentials for a model the admin added, or None for built-ins."""
    row = db.get(AppModel, model_id)
    if row is None:
        return None
    return {"base_url": row.base_url, "api_key": _effective_key(row), "model_name": row.model_name}


def _slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:40] or "model"


def _unique_id(db: Session, name: str) -> str:
    base = _slug(name)
    candidate = base
    n = 1
    while db.get(AppModel, candidate) is not None:
        n += 1
        candidate = f"{base}-{n}"
    return candidate


def _validate_base_url(url: str) -> None:
    u = urllib.parse.urlsplit(url.strip())
    if u.scheme not in ("http", "https"):
        raise AdminModelError("Base URL phải bắt đầu bằng http:// hoặc https://")
    if not u.hostname:
        raise AdminModelError("Base URL thiếu hostname")
    try:
        ip = ipaddress.ip_address(u.hostname)
    except ValueError:
        ip = None
    if ip is not None:
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            raise AdminModelError("Base URL không được trỏ tới mạng nội bộ hoặc metadata service")
    elif settings.app_env != "production" or settings.allow_private_model_urls:
        # Explicit local/dev opt-in for placeholder or local service URLs.
        return
    else:
        try:
            resolved = socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80), type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise AdminModelError("Không phân giải được hostname của Base URL") from exc
        for item in resolved:
            try:
                resolved_ip = ipaddress.ip_address(item[4][0])
            except ValueError:
                continue
            if resolved_ip.is_private or resolved_ip.is_loopback or resolved_ip.is_link_local or resolved_ip.is_multicast or resolved_ip.is_reserved:
                raise AdminModelError("Base URL không được trỏ tới mạng nội bộ hoặc metadata service")


def _validate(step: str, base_url: str, name: str) -> None:
    if step not in STEPS_ALLOWED:
        raise AdminModelError(f"Bước không hợp lệ: {step}")
    if not name.strip():
        raise AdminModelError("Tên model không được để trống")
    if not base_url.strip():
        raise AdminModelError("Base URL không được để trống")
    _validate_base_url(base_url)


def _seed_price(db: Session, model_id: str) -> None:
    key = f"m.{model_id}"
    if db.get(PricingItem, key) is None:
        db.add(PricingItem(key=key, price=0.0, enabled=True))
        db.commit()


def create(db: Session, *, name: str, step: str, base_url: str, api_key: str = "",
           model_name: str = "", enabled: bool = True, max_clip_seconds: int = 15,
           supported_durations: list[int] | None = None) -> AppModel:
    _validate(step, base_url, name)
    durations = _normalize_durations(supported_durations)
    try:
        max_sec = max(1, int(max_clip_seconds or 1))
    except (TypeError, ValueError):
        raise AdminModelError("Thời lượng tối đa phải là số nguyên")
    row = AppModel(
        id=_unique_id(db, name),
        name=name.strip(),
        step=step,
        base_url=base_url.strip().rstrip("/"),
        api_key="",                       # keys live in .env, never in the DB
        model_name=model_name.strip(),
        enabled=bool(enabled),
        max_clip_seconds=max_sec,
        supported_durations=durations,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    if api_key.strip():
        env_upsert(model_key_env(row.id), api_key.strip())
    _seed_price(db, row.id)
    sync(db)
    return row


def update(db: Session, model_id: str, **fields) -> AppModel:
    row = db.get(AppModel, model_id)
    if row is None:
        raise AdminModelError("Không tìm thấy model")
    if fields.get("name") is not None:
        if not str(fields["name"]).strip():
            raise AdminModelError("Tên model không được để trống")
        row.name = str(fields["name"]).strip()
    if fields.get("step") is not None:
        if fields["step"] not in STEPS_ALLOWED:
            raise AdminModelError(f"Bước không hợp lệ: {fields['step']}")
        row.step = fields["step"]
    if fields.get("base_url") is not None:
        url = str(fields["base_url"]).strip().rstrip("/")
        if not url:
            raise AdminModelError("Base URL không được để trống")
        row.base_url = url
    if fields.get("api_key"):
        env_upsert(model_key_env(model_id), str(fields["api_key"]).strip())  # blank = keep the old key
        row.api_key = ""
    if fields.get("model_name") is not None:
        row.model_name = str(fields["model_name"]).strip()
    if fields.get("enabled") is not None:
        row.enabled = bool(fields["enabled"])
        # đồng bộ trạng thái sang bảng giá (m.<id>) để /api/assistant/models phản ánh đúng
        price_row = db.get(PricingItem, f"m.{model_id}")
        if price_row is not None:
            price_row.enabled = bool(fields["enabled"])
    if fields.get("max_clip_seconds") is not None:
        try:
            row.max_clip_seconds = max(1, int(fields["max_clip_seconds"]))
        except (TypeError, ValueError):
            raise AdminModelError("Thời lượng tối đa phải là số nguyên")
    if fields.get("supported_durations") is not None:
        durations = _normalize_durations(fields["supported_durations"])
        row.supported_durations = durations
    db.commit()
    db.refresh(row)
    sync(db)
    return row


def delete(db: Session, model_id: str) -> None:
    row = db.get(AppModel, model_id)
    if row is None:
        raise AdminModelError("Không tìm thấy model")
    db.delete(row)
    price_row = db.get(PricingItem, f"m.{model_id}")
    if price_row is not None:
        db.delete(price_row)
    db.commit()
    env_upsert(model_key_env(model_id), "")   # remove the key from .env as well
    sync(db)

"""Pick an admin-managed LLM for secondary tasks (subtitle refine/translate, support chat)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from . import adminmodels
from . import pricing as _pricing
from .modelregistry import all_models


def resolve_llm(db: Session, requested_id: str = "") -> dict | None:
    """Return {id, name, creds, price} for a chat model, or None when none is usable.

    Ưu tiên model user chọn; không thì model LLM đang bật có giá rẻ nhất (0 = Free).
    """
    llms = [m for m in all_models() if m.step == "llm" and m.enabled]
    if not llms:
        return None

    def _price(m) -> float:
        key = f"m.{m.id}"
        try:
            return _pricing.price(db, key) if key in _pricing.catalog() else 0.0
        except Exception:
            return 0.0

    chosen = next((m for m in llms if m.id == (requested_id or "").strip()), None)
    if chosen is None:
        chosen = sorted(llms, key=lambda m: (_price(m), m.name))[0]
    creds = adminmodels.creds(db, chosen.id) or {}
    if not creds.get("api_key") or not creds.get("model_name"):
        return None
    return {"id": chosen.id, "name": chosen.name, "creds": creds, "price": _price(chosen)}

"""Support links shared by the public widget, the app UI and the admin panel.

Admin-configured values live in the `app_settings` table under `support.<key>`;
`.env` values are only the fallback. DB wins so the admin can change links live.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .config import settings
from .models import AppSetting

_KEYS = ("zalo", "facebook", "telegram", "email")


def _row(db: Session, key: str) -> str:
    row = db.get(AppSetting, f"support.{key}")
    return (row.value or "").strip() if row else ""


def _env(key: str) -> str:
    return {"zalo": settings.support_zalo_url,
            "facebook": settings.support_facebook_url,
            "telegram": settings.support_telegram_url,
            "email": settings.support_email}.get(key, "")


def get_links(db: Session) -> dict:
    """Effective support links: DB first, then .env."""
    out = {"site_name": settings.site_name}
    for key in _KEYS:
        out[key] = _row(db, key) or _env(key)
    return out


def set_links(db: Session, values: dict) -> dict:
    """Persist support links; values are validated and may be emptied."""
    import re
    url = re.compile(r"^https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]{4,250}$")
    email = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}$")
    for key in _KEYS:
        if key not in values:
            continue
        val = str(values[key] or "").strip()
        if val:
            if key == "email":
                if not email.match(val):
                    raise ValueError(f"Email không hợp lệ: {val}")
            elif not url.match(val):
                raise ValueError(f"URL không hợp lệ cho {key}: {val}")
        row = db.get(AppSetting, f"support.{key}")
        if row is None:
            row = AppSetting(key=f"support.{key}", value=val)
            db.add(row)
        else:
            row.value = val
    db.commit()
    return get_links(db)

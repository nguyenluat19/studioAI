"""Phone number validation + OTP (SMS) for registration.

Dev mode convenience: when ESMS is NOT configured and APP_ENV != production, the
otp is never sent anywhere — the user is auto-verified and the code is written to
the server log only. In production with ESMS unconfigured, registration is refused
with 503 so a public launch can never leak a bypass.
"""
from __future__ import annotations

import hashlib
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import ratelimit
from .config import settings
from .models import PhoneOtp

log = logging.getLogger(__name__)

OTP_TTL_MINUTES = 5
OTP_MAX_ATTEMPTS = 5
SEND_LIMIT_PER_HOUR = 5


def now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_phone(raw: str) -> str | None:
    """VN mobile → dạng 10 chữ số '0xxxxxxxxx'. Trả None nếu không hợp lệ."""
    s = re.sub(r"[^\d+]", "", (raw or "").strip())
    if s.startswith("+84"):
        s = "0" + s[3:]
    elif s.startswith("84") and len(s) >= 11:
        s = "0" + s[2:]
    if not re.fullmatch(r"0(3|5|7|8|9)\d{8}", s):
        return None
    return s


def mask_phone(p: str) -> str:
    return p[:4] + "****" + p[-3:] if len(p) >= 10 else p


def _hash(phone: str, code: str) -> str:
    return hashlib.sha256(f"{phone}:{code}".encode()).hexdigest()


def sms_ready() -> bool:
    return bool(settings.esms_api_key and settings.esms_api_secret)


def sms_send(phone: str, content: str) -> bool:
    """Gửi SMS qua ESMS (https://esms.vn). Trả True khi đã chấp nhận gửi."""
    if not sms_ready():
        return False
    try:
        r = httpx.post(
            "https://api.esms.vn/MainService.svc/json/SendMultipleMessage_V4_post_json",
            json={"ApiKeySms": settings.esms_api_key,
                  "SecretKeySms": settings.esms_api_secret,
                  "Content": content,
                  "Phone": phone,
                  "SmsType": 2,
                  "Brandname": settings.esms_brandname},
            timeout=15)
        data = r.json()
        ok = str(data.get("CodeResult", data.get("ApiResultCode", ""))) in ("100", "101")
        if not ok:
            log.warning("[otp] ESMS trả về: %s", data)
        return ok
    except Exception as e:
        log.warning("[otp] ESMS lỗi: %s", e)
        return False


def issue_otp(db: Session, phone: str, user_id: int | None = None) -> str | None:
    """Tạo OTP 6 số, lưu hash; gửi SMS nếu đã cấu hình. Trả về code (dùng để log/test)."""
    if ratelimit.hit(f"otp_send:{phone}", 3600) > SEND_LIMIT_PER_HOUR:
        return None
    code = f"{secrets.randbelow(10**6):06d}"
    expires = now() + timedelta(minutes=OTP_TTL_MINUTES)
    db.add(PhoneOtp(phone=phone, code_hash=_hash(phone, code),
                    user_id=user_id, attempts=0, expires_at=expires))
    db.commit()

    content = (settings.esms_content or "Ma xac minh dang ky la {code}").replace("{code}", code)
    if sms_ready():
        ok = sms_send(phone, content)
        if not ok:
            log.warning("[otp] Không gửi được SMS cho %s (kiểm tra ESMS_* trong .env)", mask_phone(phone))
    else:
        # Dev/staging: không gửi SMS, chỉ log code để chủ tool tự kiểm thử.
        log.warning("[otp] ESMS chưa cấu hình — OTP cho %s là %s (chỉ log, không gửi)",
                    mask_phone(phone), code)
    return code


def verify_otp(db: Session, phone: str, code: str) -> tuple[bool, str]:
    """Kiểm tra OTP của số điện thoại. Trả (True, '') khi hợp lệ."""
    row = db.scalar(select(PhoneOtp).where(PhoneOtp.phone == phone)
                    .order_by(PhoneOtp.id.desc()))
    if row is None:
        return False, "Chưa có mã xác minh cho số điện thoại này."
    if row.expires_at and row.expires_at.replace(tzinfo=timezone.utc) < now():
        return False, "Mã xác minh đã hết hạn. Bấm “Gửi lại mã”."
    if row.attempts >= OTP_MAX_ATTEMPTS:
        return False, "Bạn nhập sai quá nhiều lần. Bấm “Gửi lại mã”."
    row.attempts += 1
    db.commit()
    if row.code_hash != _hash(phone, (code or "").strip()):
        return False, "Mã xác minh không đúng. Kiểm tra lại SMS."
    db.execute(delete(PhoneOtp).where(PhoneOtp.phone == phone))
    db.commit()
    return True, ""

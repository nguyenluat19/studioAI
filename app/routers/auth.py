from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import otp, ratelimit
from ..config import settings
from ..db import get_db
from ..deps import current_user
from ..activity import log_activity
from ..models import ActivityLog, CreditLedgerEntry, User
from ..security import hash_password, make_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    email: str = Field(max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=128)
    # Tạm thời ẩn xác minh SĐT (REQUIRE_PHONE_VERIFICATION=0) -> phone không bắt buộc.
    phone: str = Field(default="", max_length=16)


class LoginIn(BaseModel):
    username: str
    password: str


class OtpVerifyIn(BaseModel):
    username: str
    code: str = Field(min_length=4, max_length=8)


class OtpResendIn(BaseModel):
    username: str


def user_out(u: User) -> dict:
    return {"id": u.id, "username": u.username, "email": u.email,
            "credits_balance": u.credits_balance, "role": u.role}


def _ip(request: Request) -> str:
    return request.client.host if request.client else "?"


@router.post("/register")
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    if ratelimit.hit(f"reg:{_ip(request)}", 3600) > settings.register_per_hour:
        raise HTTPException(429, "Đăng ký quá nhiều lần, vui lòng thử lại sau")

    require_phone = settings.require_phone_verification
    phone = otp.normalize_phone(body.phone) if body.phone.strip() else None
    if require_phone and not phone:
        raise HTTPException(422, "Số điện thoại không hợp lệ (dạng 03x/05x/07x/08x/09x, 10 chữ số)")

    sms_ready = otp.sms_ready()
    if require_phone and not sms_ready and settings.app_env == "production":
        raise HTTPException(503, "Dịch vụ SMS chưa được cấu hình — vui lòng liên hệ quản trị viên.")

    # Tắt xác minh SĐT -> tài khoản dùng được ngay. Bật lại: dev/staging tự xác minh,
    # production thì phải nhận mã OTP qua SMS.
    auto_verify = (not require_phone) or (not sms_ready)

    user = User(username=body.username, email=body.email.lower(),
                password_hash=hash_password(body.password), role="user",
                phone=phone, phone_verified=auto_verify)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Tên đăng nhập, email hoặc số điện thoại đã tồn tại")

    if auto_verify:
        log_activity(db, user.id, "register", ip=_ip(request),
                     details={"username": user.username, "email": user.email,
                              "phone": otp.mask_phone(phone) if phone else "",
                              "sms": "skipped"})
        return {"token": make_token(user.id), "user": user_out(user)}

    # SMS đã cấu hình: gửi OTP, chỉ trả token sau khi xác minh.
    code = otp.issue_otp(db, phone, user.id)
    if code is None:
        raise HTTPException(429, "Bạn đã yêu cầu gửi mã quá nhiều lần. Thử lại sau ít phút.")
    log_activity(db, user.id, "register", ip=_ip(request),
                 details={"username": user.username, "email": user.email, "phone": otp.mask_phone(phone)})
    return {"ok": True, "need_verify": True, "masked_phone": otp.mask_phone(phone)}


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    key = f"login:{_ip(request)}:{body.username.lower()}"
    if ratelimit.count(key, 600) >= settings.login_max_failures:
        raise HTTPException(429, "Đăng nhập sai quá nhiều lần, vui lòng thử lại sau 10 phút")
    user = db.scalar(select(User).where(or_(User.username == body.username,
                                            User.email == body.username.lower())))
    if not user or not verify_password(body.password, user.password_hash):
        ratelimit.hit(key, 600)
        raise HTTPException(401, "Sai tên đăng nhập hoặc mật khẩu")
    if settings.require_phone_verification and not user.phone_verified:
        raise HTTPException(403, {"message": "Tài khoản chưa xác minh số điện thoại. "
                                             "Hãy nhập mã OTP đã gửi tới số điện thoại của bạn.",
                                  "need_verify": True, "username": user.username})
    ratelimit.clear(key)
    log_activity(db, user.id, "login", ip=_ip(request), details={"username": user.username})
    return {"token": make_token(user.id), "user": user_out(user)}


def _otp_enabled() -> None:
    """Xác minh SĐT đang tạm ẩn (REQUIRE_PHONE_VERIFICATION=0) -> các endpoint OTP trả 409."""
    if not settings.require_phone_verification:
        raise HTTPException(409, "Xác minh số điện thoại đang tạm tắt — tài khoản dùng được ngay khi đăng ký.")


@router.post("/verify-phone")
def verify_phone(body: OtpVerifyIn, request: Request, db: Session = Depends(get_db)):
    """Xác minh mã OTP gửi qua SMS → trả token đăng nhập."""
    _otp_enabled()
    user = db.scalar(select(User).where(or_(User.username == body.username,
                                            User.email == body.username.lower())))
    if not user:
        raise HTTPException(404, "Không tìm thấy tài khoản này")
    if user.phone_verified:
        return {"token": make_token(user.id), "user": user_out(user)}
    if not user.phone:
        raise HTTPException(400, "Tài khoản này không có số điện thoại để xác minh.")
    ok, err = otp.verify_otp(db, user.phone, body.code)
    if not ok:
        raise HTTPException(400, err)
    user.phone_verified = True
    db.commit()
    log_activity(db, user.id, "verify_phone", ip=_ip(request),
                 details={"username": user.username, "phone": otp.mask_phone(user.phone)})
    return {"token": make_token(user.id), "user": user_out(user)}


@router.post("/resend-otp")
def resend_otp(body: OtpResendIn, db: Session = Depends(get_db)):
    """Gửi lại mã OTP (giới hạn số lần gửi)."""
    _otp_enabled()
    user = db.scalar(select(User).where(or_(User.username == body.username,
                                            User.email == body.username.lower())))
    if not user:
        raise HTTPException(404, "Không tìm thấy tài khoản này")
    if user.phone_verified:
        return {"ok": True, "already_verified": True}
    if not otp.sms_ready():
        raise HTTPException(503, "Dịch vụ SMS chưa được cấu hình — liên hệ quản trị viên.")
    if not user.phone:
        raise HTTPException(400, "Tài khoản này không có số điện thoại để xác minh.")
    code = otp.issue_otp(db, user.phone, user.id)
    if code is None:
        raise HTTPException(429, "Bạn đã yêu cầu gửi mã quá nhiều lần. Thử lại sau ít phút.")
    return {"ok": True, "masked_phone": otp.mask_phone(user.phone)}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


class UpdateMeIn(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    email: str | None = Field(default=None, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    current_password: str = ""
    new_password: str | None = Field(default=None, min_length=8, max_length=128)


@router.put("/me")
def update_me(body: UpdateMeIn, request: Request, db: Session = Depends(get_db),
              user: User = Depends(current_user)):
    """Người dùng tự sửa thông tin đăng ký (tên, email, mật khẩu)."""
    changed = []
    if body.username and body.username != user.username:
        if db.scalar(select(User.id).where(User.username == body.username, User.id != user.id)):
            raise HTTPException(409, "Tên đăng nhập đã tồn tại")
        user.username, changed = body.username, changed + ["username"]
    if body.email and body.email.lower() != user.email:
        if db.scalar(select(User.id).where(User.email == body.email.lower(), User.id != user.id)):
            raise HTTPException(409, "Email đã được dùng cho tài khoản khác")
        user.email, changed = body.email.lower(), changed + ["email"]
    if body.new_password:
        if not verify_password(body.current_password, user.password_hash):
            raise HTTPException(403, "Mật khẩu hiện tại không đúng")
        user.password_hash = hash_password(body.new_password)
        changed.append("password")
    if not changed:
        return user_out(user)
    db.commit()
    log_activity(db, user.id, "profile_update", ip=_ip(request), details={"fields": changed})
    return user_out(user)


@router.get("/me/activity")
def my_activity(user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(ActivityLog).where(ActivityLog.user_id == user.id).order_by(ActivityLog.id.desc()).limit(100)
    logs = db.scalars(q).all()
    return [{
        "id": a.id,
        "action": a.action,
        "ip": a.ip,
        "details": a.details or {},
        "created_at": a.created_at
    } for a in logs]


@router.get("/me/credit-ledger")
def my_credit_ledger(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Lịch sử dòng tiền của chính tài khoản này — mọi cộng/trừ credit."""
    q = select(CreditLedgerEntry).where(CreditLedgerEntry.user_id == user.id).order_by(CreditLedgerEntry.id.desc()).limit(200)
    rows = db.scalars(q).all()
    return [{
        "id": r.id,
        "kind": r.kind,
        "amount": r.amount,
        "balance_after": r.balance_after,
        "reason": r.reason,
        "ref_type": r.ref_type,
        "ref_id": r.ref_id,
        "created_at": r.created_at,
    } for r in rows]

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import math
<<<<<<< HEAD
import json
import logging
import re
=======
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

<<<<<<< HEAD
from datetime import datetime, timedelta, timezone

from .. import credits, pricing, promotions
from .. import featurebilling as featurebilling_mod
from .. import tts as tts_mod
from ..config import settings
from ..db import get_db
from ..deps import admin_user
from ..maintenance import as_utc
from ..media import voice_meta_dir as _voice_meta_dir
from ..models import (ActivityLog, AppModel, CreditAdjustment, CreditLedgerEntry, GenerationHistory,
                      PricingLog, Promotion, SharedVideoLibrary, Transaction, User, WebhookLog)
from .billing import tx_out
from .templates import tpl_out

logger = logging.getLogger(__name__)

=======
from datetime import datetime

from .. import credits, pricing, promotions
from ..db import get_db
from ..deps import admin_user
from ..maintenance import as_utc
from ..models import (CreditAdjustment, GenerationHistory, PricingLog, Promotion, SharedVideoLibrary, Transaction, User,
                      WebhookLog)
from .billing import tx_out
from .templates import tpl_out

>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(admin_user)])


@router.get("/templates")
def list_all(status: str | None = None, source: str | None = None, db: Session = Depends(get_db)):
    """source=generated -> entries auto-created from renders; source=created -> hand-made templates."""
    q = select(SharedVideoLibrary).order_by(SharedVideoLibrary.id.desc())
    if status:
        q = q.where(SharedVideoLibrary.status == status)
    if source == "generated":
        q = q.where(SharedVideoLibrary.source_generation_id.is_not(None))
    elif source == "created":
        q = q.where(SharedVideoLibrary.source_generation_id.is_(None))
    return [tpl_out(t) for t in db.scalars(q)]


def _set_status(db: Session, tid: int, status: str) -> dict:
    t = db.get(SharedVideoLibrary, tid)
    if not t:
        raise HTTPException(404, "Không tìm thấy template")
    t.status = status
    db.commit()
    return tpl_out(t)


class TemplateStatusIn(BaseModel):
    status: str = "publish"


@router.patch("/templates/{tid}")
def update_status(tid: int, body: TemplateStatusIn, db: Session = Depends(get_db)):
    st = "publish" if body.status == "publish" else "private"
    return _set_status(db, tid, st)


@router.post("/templates/{tid}/publish")
def publish(tid: int, db: Session = Depends(get_db)):
    return _set_status(db, tid, "publish")


@router.post("/templates/{tid}/unpublish")
def unpublish(tid: int, db: Session = Depends(get_db)):
    return _set_status(db, tid, "private")


@router.delete("/templates/{tid}")
def reject(tid: int, db: Session = Depends(get_db)):
    """Discard an entry that is not fit for the library. Only private entries can be removed."""
    t = db.get(SharedVideoLibrary, tid)
    if not t:
        raise HTTPException(404, "Không tìm thấy template")
    if t.status == "publish":
        raise HTTPException(409, "Hãy gỡ công khai (unpublish) trước khi xoá")
    if db.query(GenerationHistory.id).filter_by(template_id=tid).first():
        raise HTTPException(409, "Template đã có lịch sử render, chỉ có thể để ở trạng thái private")
    db.delete(t)
    db.commit()
    return {"deleted": tid}


@router.get("/users")
def users(q: str | None = None, limit: int = 200, db: Session = Depends(get_db)):
    """All accounts (admins included), optionally filtered by username/email substring."""
    stmt = select(User).order_by(User.id)
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(User.username).like(like), func.lower(User.email).like(like)))
    return [{"id": u.id, "username": u.username, "email": u.email, "role": u.role,
             "credits_balance": round(u.credits_balance, 2), "created_at": u.created_at}
            for u in db.scalars(stmt.limit(max(1, min(limit, 500))))]


MAX_ADJUST = 10_000_000


<<<<<<< HEAD
# ---------------- Analytics ----------------
_PERIODS = ("lifetime", "today", "yesterday", "l7d", "l30d", "custom")


def _utc_naive(dt: datetime) -> datetime:
    """datetime có tz -> datetime naive UTC (SQLite trả datetime naive theo UTC)."""
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _range_bounds(period: str, start: str | None, end: str | None) -> tuple[datetime | None, datetime, str]:
    """Khoảng thời gian theo giờ địa phương của server, trả về (start_utc_naive, end_utc_naive, nhãn)."""
    now_local = datetime.now().astimezone()
    today0 = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    period = (period or "lifetime").lower()
    if period == "today":
        lo, hi = today0, today0 + timedelta(days=1)
    elif period == "yesterday":
        lo, hi = today0 - timedelta(days=1), today0
    elif period == "l7d":
        lo, hi = today0 - timedelta(days=6), today0 + timedelta(days=1)
    elif period == "l30d":
        lo, hi = today0 - timedelta(days=29), today0 + timedelta(days=1)
    elif period == "custom":
        def _d(v, fallback):
            try:
                return datetime.fromisoformat(v).astimezone().replace(tzinfo=None)
            except (TypeError, ValueError):
                return fallback
        lo = _d(start, today0 - timedelta(days=29))
        hi = _d(end, today0 + timedelta(days=1))
        if hi <= lo:
            hi = lo + timedelta(days=1)
    else:
        period = "lifetime"
        lo, hi = None, now_local
    return (_utc_naive(lo) if lo else None, _utc_naive(hi), period)


@router.get("/analytics")
def analytics(period: str = "lifetime", start: str | None = None, end: str | None = None,
              db: Session = Depends(get_db)):
    """Số liệu vận hành: người dùng (mới / hoạt động / tổng), tiền nạp, tiền chi theo kỳ."""
    lo, hi, period = _range_bounds(period, start, end)

    def _where(col):
        if lo is None:
            return col <= hi
        return col.between(lo, hi)

    total_users = db.scalar(select(func.count(User.id))) or 0
    new_users = db.scalar(select(func.count(User.id)).where(_where(User.created_at))) or 0

    active_ids = db.scalars(select(ActivityLog.user_id).where(_where(ActivityLog.created_at)).distinct()).all()
    active_users = len(active_ids)

    now_utc = _utc_naive(datetime.now().astimezone())
    online_ids = db.scalars(
        select(ActivityLog.user_id).where(ActivityLog.created_at >= now_utc - timedelta(minutes=15)).distinct()
    ).all()

    logins = db.scalar(select(func.count(ActivityLog.id)).where(
        _where(ActivityLog.created_at), ActivityLog.action == "login")) or 0

    topup_vnd = float(db.scalar(select(func.coalesce(func.sum(Transaction.amount_vnd), 0)).where(
        _where(Transaction.created_at), Transaction.status == "success")) or 0)
    topup_credits = float(db.scalar(select(func.coalesce(func.sum(Transaction.credits_added), 0)).where(
        _where(Transaction.created_at), Transaction.status == "success")) or 0)
    spend_credits = float(db.scalar(select(func.coalesce(func.sum(CreditLedgerEntry.amount), 0)).where(
        _where(CreditLedgerEntry.created_at), CreditLedgerEntry.kind == "spend")) or 0)
    spend_credits = abs(spend_credits)
    vnd_per_credit = float(pricing.get_setting(db, "vnd_per_credit", 1000) or 1000)

    # Chuỗi theo ngày (tối đa 31 điểm) cho bảng phân tích
    series = []
    if period != "lifetime" and lo is not None:
        days = min(31, max(1, (hi.date() - lo.date()).days))
        for i in range(days):
            d0 = (lo + timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
            d1 = d0 + timedelta(days=1)
            nu = db.scalar(select(func.count(User.id)).where(User.created_at.between(d0, d1))) or 0
            au = len(set(db.scalars(select(ActivityLog.user_id)
                                    .where(ActivityLog.created_at.between(d0, d1))).all()))
            tv = float(db.scalar(select(func.coalesce(func.sum(Transaction.amount_vnd), 0)).where(
                Transaction.created_at.between(d0, d1), Transaction.status == "success")) or 0)
            series.append({"date": d0.date().isoformat(), "new_users": nu,
                           "active_users": au, "topup_vnd": tv})

    return {
        "period": period,
        "range": {"start": lo.isoformat() if lo else None, "end": hi.isoformat()},
        "users": {"total": total_users, "new": new_users, "active": active_users,
                  "online_now": len(online_ids), "logins": logins},
        "money": {"topup_vnd": topup_vnd, "topup_credits": topup_credits,
                  "spend_credits": spend_credits,
                  "spend_vnd": round(spend_credits * vnd_per_credit),
                  "vnd_per_credit": vnd_per_credit},
        "series": series,
    }


@router.get("/users/{uid}/detail")
def user_detail(uid: int, db: Session = Depends(get_db)):
    """Chi tiết 1 tài khoản: thông tin, tiền, lịch sử hoạt động và sản phẩm đã tạo."""
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "Không tìm thấy tài khoản")
    activity = db.scalars(select(ActivityLog).where(ActivityLog.user_id == uid)
                          .order_by(ActivityLog.id.desc()).limit(100)).all()
    gens = db.scalars(select(GenerationHistory).where(GenerationHistory.user_id == uid)
                       .order_by(GenerationHistory.id.desc()).limit(100)).all()
    tpls = db.scalars(select(SharedVideoLibrary).where(SharedVideoLibrary.creator_id == uid)
                      .order_by(SharedVideoLibrary.id.desc()).limit(100)).all()
    txs = db.scalars(select(Transaction).where(Transaction.user_id == uid)
                     .order_by(Transaction.id.desc()).limit(100)).all()
    ledger = db.scalars(select(CreditLedgerEntry).where(CreditLedgerEntry.user_id == uid)
                        .order_by(CreditLedgerEntry.id.desc()).limit(200)).all()
    paid = float(db.scalar(select(func.coalesce(func.sum(Transaction.amount_vnd), 0)).where(
        Transaction.user_id == uid, Transaction.status == "success")) or 0)
    return {
        "user": {"id": u.id, "username": u.username, "email": u.email, "role": u.role,
                 "credits_balance": round(u.credits_balance, 2),
                 "phone": u.phone or "", "created_at": u.created_at,
                 "total_paid_vnd": paid},
        "activity": [{"id": a.id, "action": a.action, "ip": a.ip,
                      "details": a.details or {}, "created_at": a.created_at} for a in activity],
        "generations": [{"id": g.id, "title": g.title, "status": g.status,
                         "render_type": g.render_type, "credits_cost": g.credits_cost,
                         "output_video_url": g.output_video_url, "created_at": g.created_at}
                        for g in gens],
        "templates": [{"id": t.id, "title": t.title, "category": t.category, "status": t.status,
                       "base_video_url": t.base_video_url, "thumbnail_url": t.thumbnail_url,
                       "created_at": t.created_at} for t in tpls],
        "transactions": [{**tx_out(t)} for t in txs],
        "ledger": [{"id": e.id, "kind": e.kind, "amount": e.amount, "balance_after": e.balance_after,
                    "reason": e.reason, "created_at": e.created_at} for e in ledger],
    }


class UserUpdateIn(BaseModel):
    username: str | None = None
    email: str | None = None
    role: str | None = None


@router.put("/users/{uid}")
def user_update(uid: int, body: UserUpdateIn, db: Session = Depends(get_db),
                admin: User = Depends(admin_user)):
    """Admin sửa thông tin tài khoản (tên, email, vai trò)."""
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "Không tìm thấy tài khoản")
    if body.username:
        new_name = body.username.strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,64}", new_name):
            raise HTTPException(422, "Tên đăng nhập không hợp lệ (3-64 ký tự, không dấu cách)")
        if db.scalar(select(User.id).where(User.username == new_name, User.id != uid)):
            raise HTTPException(409, "Tên đăng nhập đã tồn tại")
        u.username = new_name
    if body.email:
        new_email = body.email.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", new_email):
            raise HTTPException(422, "Email không hợp lệ")
        if db.scalar(select(User.id).where(User.email == new_email, User.id != uid)):
            raise HTTPException(409, "Email đã được dùng cho tài khoản khác")
        u.email = new_email
    if body.role:
        if body.role not in ("user", "admin"):
            raise HTTPException(422, "Vai trò chỉ có 'user' hoặc 'admin'")
        if u.id == admin.id and body.role != "admin":
            raise HTTPException(409, "Không thể tự hạ quyền tài khoản đang đăng nhập")
        u.role = body.role
    db.commit()
    return {"id": u.id, "username": u.username, "email": u.email, "role": u.role}


=======
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
class GrantIn(BaseModel):
    amount: float
    reason: str = ""


@router.post("/users/{uid}/credits")
def grant(uid: int, body: GrantIn, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    """Add (positive) or remove (negative) any amount of credits on any account, with an audit entry."""
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "Không tìm thấy người dùng")
    amount = round(body.amount, 2)
    if not math.isfinite(amount) or amount == 0 or abs(amount) > MAX_ADJUST:
        raise HTTPException(422, f"Số credit phải khác 0 và không quá {MAX_ADJUST:,}".replace(",", "."))
    bal = credits.adjust(db, uid, amount, admin.id, body.reason)
    if bal is None:
        raise HTTPException(422, "Số dư không thể âm")
    return {"id": u.id, "credits_balance": bal, "amount": amount}


@router.get("/credit-log")
def credit_log(user_id: int | None = None, limit: int = 200, db: Session = Depends(get_db)):
    stmt = select(CreditAdjustment).order_by(CreditAdjustment.id.desc()).limit(max(1, min(limit, 500)))
    if user_id is not None:
        stmt = stmt.where(CreditAdjustment.user_id == user_id)
    names = {u.id: u.username for u in db.scalars(select(User))}
    return [{"id": a.id, "user_id": a.user_id, "username": names.get(a.user_id, "?"), "amount": a.amount,
             "balance_after": a.balance_after, "reason": a.reason, "admin": names.get(a.admin_id, "?"),
             "created_at": as_utc(a.created_at).isoformat()} for a in db.scalars(stmt)]


@router.get("/transactions")
def transactions(status: str | None = None, db: Session = Depends(get_db)):
    q = select(Transaction).order_by(Transaction.id.desc()).limit(200)
    if status:
        q = q.where(Transaction.status == status)
    return [{**tx_out(t), "user_id": t.user_id} for t in db.scalars(q)]


@router.post("/transactions/{tid}/approve")
def approve(tid: int, db: Session = Depends(get_db)):
    """Manual settlement for cases the webhook refused to auto-credit (amount mismatch, late payment)."""
    if not credits.settle_topup(db, tid, allow_from=("pending", "failed")):
        raise HTTPException(409, "Giao dịch đã thành công hoặc không tồn tại")
    return {"id": tid, "status": "success"}


<<<<<<< HEAD
# ---------------- Giọng clone toàn hệ thống (admin) ----------------


@router.get("/voices-cloned")
def voices_all(db: Session = Depends(get_db)):
    """Danh sách TẤT CẢ giọng clone của mọi tài khoản — admin quản lý data tổng."""
    names = {u.id: u.username for u in db.scalars(select(User))}
    voices = []
    vdir = _voice_meta_dir()
    if vdir.exists():
        for meta_path in vdir.glob("*.json"):
            try:
                m = json.loads(meta_path.read_text(encoding="utf-8"))
                voices.append({
                    "id": m["id"],
                    "name": m.get("name", ""),
                    "owner_id": m.get("user_id"),
                    "owner_username": names.get(m.get("user_id"), "?"),
                    "url": f"/media/voices/{m.get('file', '')}",
                    "size": m.get("size", 0),
                    "provider": m.get("provider", "none"),
                    "provider_voice_id": m.get("provider_voice_id"),
                    "voice_value": m.get("voice_value"),
                    "clone_error": m.get("clone_error"),
                })
            except Exception as e:
                logger.warning("[admin] bỏ qua metadata giọng hỏng %s: %s", meta_path.name, e)
    voices.sort(key=lambda v: v.get("owner_id") or 0)
    return {"voices": voices}


@router.delete("/voices-cloned/{vid}")
def voices_delete(vid: str):
    """Admin xoá bất kỳ giọng clone nào (file + metadata + clone trên provider nếu có)."""
    meta_path = _voice_meta_dir() / f"{vid}.json"
    if not meta_path.exists():
        raise HTTPException(404, "Không tìm thấy giọng này")
    try:
        m = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        m = {}
    if m.get("provider") == "elevenlabs" and m.get("provider_voice_id"):
        tts_mod.delete_elevenlabs_voice(m["provider_voice_id"])
    audio = settings.voices_dir / m.get("file", "")
    meta_path.unlink(missing_ok=True)
    if audio.exists():
        audio.unlink()
    return {"ok": True}


# ---------------- pricing dashboard ----------------
@router.get("/feature-policies")
def feature_policies(db: Session = Depends(get_db)):
    return {"items": featurebilling_mod.list_policies(db)}


class FeaturePolicyIn(BaseModel):
    model_id: str = ""
    unit_price: float | None = None
    free_limit: int | None = None
    enabled: bool | None = None


@router.put("/feature-policies/{feature_key}")
def feature_policy_update(feature_key: str, body: FeaturePolicyIn, db: Session = Depends(get_db)):
    return featurebilling_mod.update_policy(db, feature_key, body.model_id,
                                            unit_price=body.unit_price,
                                            free_limit=body.free_limit,
                                            enabled=body.enabled)


@router.get("/feature-policies/usage")
def feature_usage(db: Session = Depends(get_db), limit: int = 200):
    from ..models import FeatureUsage
    rows = db.execute(select(FeatureUsage, User.username).join(User, User.id == FeatureUsage.user_id)
                      .order_by(FeatureUsage.id.desc()).limit(max(1, min(limit, 1000)))).all()
    return [{"id": u.id, "user_id": u.user_id, "username": name, "feature_key": u.feature_key,
             "model_id": u.model_id, "units": u.units, "charge": u.charge, "is_free": u.is_free,
             "status": u.status, "ref_id": u.ref_id, "created_at": u.created_at}
            for u, name in rows]


=======
# ---------------- pricing dashboard ----------------
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
class PriceIn(BaseModel):
    price: float | None = None
    enabled: bool | None = None


class PricingSettingsIn(BaseModel):
    usd_vnd: float | None = None
    vnd_per_credit: float | None = None
    min_topup_vnd: float | None = None


def _pricing_item_out(db: Session, cat: dict, row) -> dict:
    return {"key": cat["key"], "label": cat["label"], "group": cat["group"],
<<<<<<< HEAD
            "group_label": pricing.GROUP_LABELS.get(cat["group"], cat["group"]), "unit": cat["unit"], "desc": cat.get("desc", ""),
=======
            "group_label": pricing.GROUP_LABELS[cat["group"]], "unit": cat["unit"], "desc": cat.get("desc", ""),
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
            "price": row.price, "default": cat["default"], "enabled": row.enabled, "cost_usd": cat["cost_usd"],
            "margin_percent": pricing.margin_percent(db, cat, row.price),
            "updated_at": row.updated_at, "updated_by": row.updated_by}


def _pricing_settings(db: Session) -> dict:
    return {"usd_vnd": pricing.get_setting(db, "usd_vnd", 25000),
            "vnd_per_credit": pricing.get_setting(db, "vnd_per_credit", 1000),
            "min_topup_vnd": pricing.get_setting(db, "min_topup_vnd", 20000)}


@router.get("/pricing")
def pricing_dashboard(db: Session = Depends(get_db)):
    pricing.seed(db)
    snap, cat = pricing.snapshot(db), pricing.catalog()
    names = {u.id: u.username for u in db.scalars(select(User))}
    log = db.scalars(select(PricingLog).order_by(PricingLog.id.desc()).limit(60)).all()
    return {
        "items": [_pricing_item_out(db, c, snap[k]) for k, c in cat.items()],
        "settings": _pricing_settings(db),
        "log": [{"id": l.id, "key": l.key, "label": cat.get(l.key, {}).get("label", l.key),
                 "old_price": l.old_price, "new_price": l.new_price,
                 "old_enabled": l.old_enabled, "new_enabled": l.new_enabled,
                 "admin": names.get(l.admin_id, "?"), "created_at": l.created_at} for l in log]}


@router.put("/pricing/{key:path}")
def pricing_update(key: str, body: PriceIn, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    if key not in pricing.catalog():
        raise HTTPException(404, "Không có mục giá này")
    try:
        row = pricing.update_item(db, key, price_value=body.price, is_enabled=body.enabled, admin_id=admin.id)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return _pricing_item_out(db, pricing.catalog()[key], row)


@router.post("/pricing-reset/{key:path}")
def pricing_reset(key: str, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    cat = pricing.catalog().get(key)
    if not cat:
        raise HTTPException(404, "Không có mục giá này")
    row = pricing.update_item(db, key, price_value=cat["default"], is_enabled=True, admin_id=admin.id)
    return _pricing_item_out(db, cat, row)


@router.put("/pricing-settings")
def pricing_settings(body: PricingSettingsIn, db: Session = Depends(get_db)):
    try:
        for k in ("usd_vnd", "vnd_per_credit", "min_topup_vnd"):
            if getattr(body, k) is not None:
                pricing.set_setting(db, k, getattr(body, k))
    except ValueError as e:
        raise HTTPException(422, str(e))
    return _pricing_settings(db)


# ---------------- top-up promotions ----------------
class TierIn(BaseModel):
    min_vnd: int
    bonus_percent: float


class PromoIn(BaseModel):
    name: str
    tiers: list[TierIn]
    start_at: datetime | None = None
    end_at: datetime | None = None
    enabled: bool = True


def _promo_out(p: Promotion) -> dict:
    # always send explicit UTC: SQLite hands back naive datetimes and browsers would read them as local time
    return {"id": p.id, "name": p.name, "tiers": p.tiers,
            "start_at": as_utc(p.start_at).isoformat() if p.start_at else None,
            "end_at": as_utc(p.end_at).isoformat() if p.end_at else None,
            "enabled": p.enabled, "state": promotions.state(p), "created_at": p.created_at}


def _apply_promo(p: Promotion, body: PromoIn) -> None:
    name = body.name.strip()
    if not name or len(name) > 120:
        raise HTTPException(422, "Tên chương trình từ 1 đến 120 ký tự")
    try:
        tiers = promotions.validate_tiers([t.model_dump() for t in body.tiers])
        promotions.validate_window(body.start_at, body.end_at)
    except ValueError as e:
        raise HTTPException(422, str(e))
    p.name, p.tiers, p.start_at, p.end_at, p.enabled = name, tiers, body.start_at, body.end_at, body.enabled


@router.get("/promotions")
def promo_list(db: Session = Depends(get_db)):
    return [_promo_out(p) for p in db.scalars(select(Promotion).order_by(Promotion.id.desc()))]


@router.post("/promotions")
def promo_create(body: PromoIn, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    p = Promotion(created_by=admin.id, tiers=[])
    _apply_promo(p, body)
    db.add(p)
    db.commit()
    return _promo_out(p)


@router.put("/promotions/{pid}")
def promo_update(pid: int, body: PromoIn, db: Session = Depends(get_db)):
    p = db.get(Promotion, pid)
    if not p:
        raise HTTPException(404, "Không tìm thấy chương trình")
    _apply_promo(p, body)
    db.commit()
    return _promo_out(p)


@router.delete("/promotions/{pid}")
def promo_delete(pid: int, db: Session = Depends(get_db)):
    p = db.get(Promotion, pid)
    if not p:
        raise HTTPException(404, "Không tìm thấy chương trình")
    db.delete(p)      # past transactions keep their locked bonus and promo_name
    db.commit()
    return {"deleted": pid}


@router.get("/webhook-log")
def webhook_log(result: str | None = None, db: Session = Depends(get_db)):
    q = select(WebhookLog).order_by(WebhookLog.id.desc()).limit(200)
    if result:
        q = q.where(WebhookLog.result == result)
    return [{"id": w.id, "provider": w.provider, "transaction_code": w.transaction_code, "amount": w.amount,
             "content": w.content, "result": w.result, "created_at": w.created_at} for w in db.scalars(q)]


<<<<<<< HEAD
# Model do admin thêm qua giao diện (app/adminmodels.py): CRUD, không cần sửa code
class AdminModelIn(BaseModel):
    name: str
    step: str
    base_url: str = ""
    api_key: str = ""
    model_name: str = ""
    enabled: bool = True
    max_clip_seconds: int = 15
    supported_durations: list[int] | None = None


class AdminModelUpdate(BaseModel):
    name: str | None = None
    step: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    model_name: str | None = None
    enabled: bool | None = None
    max_clip_seconds: int | None = None
    supported_durations: list[int] | None = None


@router.get("/models")
def admin_list_models(db: Session = Depends(get_db)):
    from .. import adminmodels
    return {"models": adminmodels.list_all(db)}


@router.post("/models")
def admin_create_model(body: AdminModelIn, db: Session = Depends(get_db)):
    from .. import adminmodels
    try:
        row = adminmodels.create(
            db, name=body.name, step=body.step, base_url=body.base_url,
            api_key=body.api_key, model_name=body.model_name,
            enabled=body.enabled, max_clip_seconds=body.max_clip_seconds,
            supported_durations=body.supported_durations,
        )
    except adminmodels.AdminModelError as e:
        raise HTTPException(422, str(e))
    return {"model": adminmodels.to_dict(row)}


@router.put("/models/{model_id}")
def admin_update_model(model_id: str, body: AdminModelUpdate, db: Session = Depends(get_db)):
    from .. import adminmodels
    try:
        row = adminmodels.update(db, model_id, **body.model_dump(exclude_unset=True))
    except adminmodels.AdminModelError as e:
        raise HTTPException(422, str(e))
    return {"model": adminmodels.to_dict(row)}


@router.delete("/models/{model_id}")
def admin_delete_model(model_id: str, db: Session = Depends(get_db)):
    from .. import adminmodels
    try:
        adminmodels.delete(db, model_id)
    except adminmodels.AdminModelError as e:
        raise HTTPException(422, str(e))
    return {"ok": True}


_PCACHE = {"ts": 0.0, "data": None}


@router.get("/provider-costs")
def provider_costs(db: Session = Depends(get_db)):
    """Kéo giá GỐC của từng model admin từ gateway (GET {base_url}/models — chuẩn OpenAI/NewAPI).

    Trả về giá thô đúng như provider trả (đ/request hoặc token/1M token) + đơn vị + seconds
    của model video — để admin so sánh với giá tool và chỉnh "Hoà vốn". Cache 60s."""
    import time
    from .. import adminmodels
    now = time.time()
    if _PCACHE["data"] is not None and now - _PCACHE["ts"] < 60:
        return _PCACHE["data"]
    out = []
    for row in db.scalars(select(AppModel)):
        item = {"id": row.id, "name": row.name, "step": row.step, "model_name": row.model_name,
                "max_clip_seconds": row.max_clip_seconds, "supported_durations": row.supported_durations,
                "active": None, "pricing_mode": "", "model_type": "",
                "price_per_request": None, "price_per_input_token": None, "price_per_output_token": None,
                "cached_input_price": None, "cache_creation_price": None, "min_price_per_request": None,
                "seconds": [], "error": None}
        creds = adminmodels.creds(db, row.id) or {}
        key = creds.get("api_key")
        if not key:
            item["error"] = "Model chưa có API key"
            out.append(item)
            continue
        base = (creds.get("base_url") or "").rstrip("/")
        try:
            from .. import provider
            data = provider.fetch_models(base, key, timeout=15)
            match = provider.match_model(data, row.model_name)
            if not match:
                item["error"] = f"Không thấy '{(row.model_name or '').strip()}' trong /v1/models"
            else:
                mo = match.get("model_options") or {}
                item.update({
                    "active": bool(match.get("active", True)),
                    "pricing_mode": match.get("pricing_mode") or "",
                    "model_type": match.get("model_type") or "",
                    "price_per_request": match.get("price_per_request"),
                    "price_per_input_token": match.get("price_per_input_token"),
                    "price_per_output_token": match.get("price_per_output_token"),
                    "cached_input_price": match.get("cached_input_price"),
                    "cache_creation_price": match.get("cache_creation_price"),
                    "min_price_per_request": match.get("min_price_per_request"),
                    "seconds": mo.get("seconds") or [],
                })
        except Exception as e:
            item["error"] = str(e)[:120] if isinstance(e, RuntimeError) else f"Không gọi được API: {str(e)[:120]}"
        out.append(item)
    _PCACHE["ts"] = now
    _PCACHE["data"] = {"models": out}
    return _PCACHE["data"]
=======
# Muse AI endpoints removed - only Wan2.1 video model remains
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    return {
        "users": db.scalar(select(func.count(User.id))),
        "revenue_vnd": db.scalar(select(func.coalesce(func.sum(Transaction.amount_vnd), 0))
                                 .where(Transaction.status == "success")),
        "generations": {s: n for s, n in db.execute(
            select(GenerationHistory.status, func.count()).group_by(GenerationHistory.status))},
        "pending_templates": db.scalar(select(func.count(SharedVideoLibrary.id))
                                       .where(SharedVideoLibrary.status == "private")),
    }
<<<<<<< HEAD


# ─── Liên hệ hỗ trợ (nút Zalo/Facebook/Telegram trong UI + widget) ──────────────
class SupportIn(BaseModel):
    zalo: str | None = None
    facebook: str | None = None
    telegram: str | None = None
    email: str | None = None


@router.get("/support")
def admin_get_support(db: Session = Depends(get_db)):
    from .. import support as support_mod
    return support_mod.get_links(db)


@router.put("/support")
def admin_set_support(body: SupportIn, db: Session = Depends(get_db)):
    from .. import support as support_mod
    try:
        out = support_mod.set_links(db, body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(422, str(e))
    return out
=======
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa

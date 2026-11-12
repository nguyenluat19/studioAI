"""Centralized admin policy for per-feature pricing, free trials and usage quotas."""
import math

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from fastapi import HTTPException

from . import credits
from .models import FeaturePolicy, FeatureUsage

FEATURES = {
    "template_render": "Tạo video từ Template",
    "assistant_pipeline": "Trợ lý AI — video",
    "assistant_images": "Trợ lý AI — chỉ tạo ảnh",
    "assistant_batch_item": "Gen hàng loạt — mỗi sản phẩm",
    "article_video": "Bài viết → Video",
    "subtitle_transcribe": "Phiên âm & dịch video",
    "library_script": "Thư viện — viết kịch bản",
    "library_analyze": "Thư viện — phân tích ảnh",
    "support_chat": "Chat hỗ trợ AI",
}


def seed(db: Session) -> None:
    for key, label in FEATURES.items():
        if db.get(FeaturePolicy, (key, "")) is None:
            db.add(FeaturePolicy(feature_key=key, model_id="", label=label, unit_price=0,
                                 free_limit=0, enabled=True))
    db.commit()


def policy(db: Session, key: str, model_id: str = "") -> FeaturePolicy:
    if key not in FEATURES:
        raise HTTPException(404, "Tính năng chưa có chính sách quản lý")
    model_id = (model_id or "")[:64]
    row = db.get(FeaturePolicy, (key, model_id))
    if row is None:
        base = db.get(FeaturePolicy, (key, ""))
        if base is None:
            base = FeaturePolicy(feature_key=key, model_id="", label=FEATURES[key],
                                 unit_price=0, free_limit=0, enabled=True)
            db.add(base)
            db.commit()
        if model_id:
            row = FeaturePolicy(feature_key=key, model_id=model_id, label=base.label,
                                unit_price=base.unit_price, free_limit=base.free_limit,
                                enabled=base.enabled)
            db.add(row)
            db.commit()
        else:
            row = base
    return row


def reserve(db: Session, user_id: int, key: str, *, model_id: str = "", units: int = 1,
            ref_id: str = "", model_cost: float = 0.0) -> FeatureUsage:
    """Atomically decide free allowance or charge policy + selected model API cost.

    Charge upfront, then callers call `finish` after the feature work succeeds.
    A failed feature automatically releases the free-use reservation / refunds charge.
    """
    try:
        row = policy(db, key, model_id)
        if not row.enabled:
            raise HTTPException(403, f"Tính năng đang tạm dừng: {row.label}")
        units = max(1, int(units or 1))
        used = db.scalar(select(func.coalesce(func.sum(FeatureUsage.units), 0)).where(
            FeatureUsage.user_id == user_id,
            FeatureUsage.feature_key == key,
            FeatureUsage.model_id == (model_id or ""),
            FeatureUsage.is_free.is_(True),
            FeatureUsage.status.in_(("reserved", "success")),
        )) or 0
        if int(used) + units <= int(row.free_limit or 0):
            is_free = True
        elif model_id:
            base = db.get(FeaturePolicy, (key, ""))
            if base is not None and base.free_limit > 0:
                base_used = db.scalar(select(func.coalesce(func.sum(FeatureUsage.units), 0)).where(
                    FeatureUsage.user_id == user_id,
                    FeatureUsage.feature_key == key,
                    FeatureUsage.model_id == "",
                    FeatureUsage.is_free.is_(True),
                    FeatureUsage.status.in_(("reserved", "success")),
                )) or 0
                is_free = int(base_used) + units <= int(base.free_limit)
            else:
                is_free = False
        else:
            is_free = False
        api_cost = round(float(model_cost) * units, 2)
        service_cost = 0.0 if is_free else round(row.unit_price * units, 2)
        total = round(api_cost + service_cost, 2)
        usage = FeatureUsage(user_id=user_id, feature_key=key, model_id=(model_id or ""),
                             units=units, charge=total, model_unit_cost=api_cost,
                             service_unit_cost=service_cost, is_free=is_free, status="reserved",
                             ref_id=(ref_id or "")[:64])
        if total > 0 and not credits.charge(db, user_id, total, kind="spend",
                                            reason=f"{row.label} ({model_id or 'không chọn model'})",
                                            ref_type="feature", ref_id=key):
            db.rollback()
            raise HTTPException(402, detail={"message": "Không đủ credit cho tính năng này",
                                             "required": total})
        db.add(usage)
        db.commit()
        return usage
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, "Không thể ghi nhận lượt sử dụng") from exc


def finish(db: Session, usage_id: int, *, success: bool, actual_charge: float | None = None) -> None:
    row = db.get(FeatureUsage, usage_id)
    if row is None or row.status != "reserved":
        return
    if success:
        row.status = "success"
        if actual_charge is not None:
            actual = round(max(0.0, float(actual_charge)), 2)
            target = round(actual + (0.0 if row.is_free else row.service_unit_cost), 2)
            if target < row.charge:
                credits.add_credits(db, row.user_id, row.charge - target, kind="refund",
                                    reason=f"Hoàn phần phí model không sử dụng: {row.feature_key}",
                                    ref_type="feature_usage", ref_id=row.id)
            elif target > row.charge and not credits.charge(db, row.user_id, target - row.charge,
                                                            kind="spend", reason=f"Phí model phát sinh: {row.feature_key}",
                                                            ref_type="feature_usage", ref_id=row.id):
                db.rollback()
                raise HTTPException(402, detail={"message": "Số dư không đủ cho chi phí API phát sinh",
                                                 "required": target - row.charge})
            row.charge = target
    else:
        row.status = "failed"
        if row.charge > 0:
            credits.add_credits(db, row.user_id, row.charge, kind="refund",
                                reason=f"Hoàn phí tính năng thất bại: {row.feature_key}",
                                ref_type="feature_usage", ref_id=row.id)
    db.commit()


def list_policies(db: Session) -> list[dict]:
    seed(db)
    usage = db.execute(select(FeatureUsage.feature_key, FeatureUsage.model_id, FeatureUsage.user_id,
                              func.sum(FeatureUsage.units), func.sum(FeatureUsage.charge))
                        .where(FeatureUsage.status == "success")
                        .group_by(FeatureUsage.feature_key, FeatureUsage.model_id, FeatureUsage.user_id)).all()
    stats = {}
    for key, model_id, uid, units, charged in usage:
        item = stats.setdefault((key, model_id), {"users": set(), "units": 0, "credits": 0.0})
        item["users"].add(uid)
        item["units"] += int(units or 0)
        item["credits"] += float(charged or 0)
    from .modelregistry import all_models
    models = {m.id: m.name for m in all_models()}
    out = []
    for key, label in FEATURES.items():
        model_ids = [""] + sorted(models)
        for model_id in model_ids:
            row = db.get(FeaturePolicy, (key, model_id))
            if row is None:
                base = db.get(FeaturePolicy, (key, ""))
                if base is not None:
                    row = FeaturePolicy(feature_key=key, model_id=model_id, label=base.label,
                                        unit_price=base.unit_price, free_limit=base.free_limit,
                                        enabled=base.enabled)
                else:
                    row = FeaturePolicy(feature_key=key, model_id=model_id, label=label,
                                        unit_price=0, free_limit=0, enabled=True)
                db.add(row)
                db.flush()
            st = stats.get((key, model_id), {})
            out.append({"feature_key": key, "model_id": model_id,
                        "model_name": models.get(model_id, "Mặc định / tất cả model") if model_id else "Mặc định / tất cả model",
                        "label": row.label, "unit_price": row.unit_price,
                        "free_limit": row.free_limit, "enabled": row.enabled,
                        "users": len(st.get("users", set())), "units": st.get("units", 0),
                        "credits": round(st.get("credits", 0.0), 2)})
        db.flush()
    db.commit()
    return out


def update_policy(db: Session, key: str, model_id: str = "", *, unit_price: float | None = None,
                  free_limit: int | None = None, enabled: bool | None = None) -> dict:
    if key not in FEATURES:
        raise HTTPException(404, "Tính năng không hợp lệ")
    if unit_price is not None and (not math.isfinite(float(unit_price)) or unit_price < 0 or unit_price > 1_000_000):
        raise HTTPException(422, "Giá tính năng phải nằm trong 0..1.000.000 credit/lượt")
    if free_limit is not None and not 0 <= free_limit <= 1_000_000:
        raise HTTPException(422, "Giới hạn dùng thử phải nằm trong 0..1.000.000 lượt")
    row = policy(db, key, model_id)
    if unit_price is not None:
        row.unit_price = round(float(unit_price), 2)
    if free_limit is not None:
        row.free_limit = int(free_limit)
    if enabled is not None:
        row.enabled = bool(enabled)
    db.commit()
    return {"feature_key": row.feature_key, "model_id": row.model_id,
            "label": row.label, "unit_price": row.unit_price,
            "free_limit": row.free_limit, "enabled": row.enabled}

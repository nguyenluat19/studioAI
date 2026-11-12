import secrets
<<<<<<< HEAD
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import ai
from .. import library, pricing
from ..activity import log_activity
from ..config import settings
from ..db import get_db
from ..deps import current_user
from ..media import resolve, url_for
from ..models import GenerationHistory, SharedVideoLibrary, User

router = APIRouter(prefix="/api", tags=["templates"])
logger = logging.getLogger(__name__)
=======
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import ai
from .. import credits, library, pricing
from ..config import MODEL_CATALOG, settings
from ..db import get_db
from ..deps import current_user
from ..media import resolve, url_for
from ..models import SharedVideoLibrary, User

router = APIRouter(prefix="/api", tags=["templates"])
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".webm"}
MAX_UPLOAD = 200 * 1024 * 1024
LAYER_TYPES = {"text", "image", "logo", "background"}


class TemplateIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    category: str = Field(default="full", pattern=r"^(hook|cta|full)$")
    base_video_url: str = ""
    thumbnail_url: str = ""
    template_schema: dict = Field(default_factory=dict)


def validate_schema(schema: dict) -> None:
    if not isinstance(schema.get("defaults", {}), dict):
        raise HTTPException(422, "template_schema.defaults phải là object")
    layers = schema.get("layers", [])
    if not isinstance(layers, list):
        raise HTTPException(422, "template_schema.layers phải là danh sách")
    ids = set()
    for l in layers:
        if not isinstance(l, dict) or l.get("type") not in LAYER_TYPES or not l.get("id"):
            raise HTTPException(422, f"Layer không hợp lệ (type thuộc {sorted(LAYER_TYPES)}, cần id): {l}")
        if l["id"] in ids:
            raise HTTPException(422, f"Trùng layer id: {l['id']}")
        ids.add(l["id"])


def tpl_out(t: SharedVideoLibrary) -> dict:
    return {"id": t.id, "title": t.title, "category": t.category, "base_video_url": t.base_video_url,
            "thumbnail_url": t.thumbnail_url, "preview_video_url": t.preview_video_url,
            "source_generation_id": t.source_generation_id, "template_schema": t.template_schema, "status": t.status,
            "creator_id": t.creator_id, "usage_count": t.usage_count, "created_at": t.created_at}


def visible_to(t: SharedVideoLibrary, user: User) -> bool:
    return t.status == "publish" or t.creator_id == user.id or user.role == "admin"


@router.post("/uploads")
async def upload(file: UploadFile = File(...), user: User = Depends(current_user)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(415, f"Định dạng không hỗ trợ: {ext or '?'}")
<<<<<<< HEAD
    from ..media import user_uploads_dir
    dest = user_uploads_dir(user.id) / f"{secrets.token_hex(8)}{ext}"
=======
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.uploads_dir / f"{user.id}_{secrets.token_hex(8)}{ext}"
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
    size = 0
    with dest.open("wb") as f:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD:
                f.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, "File quá lớn (tối đa 200MB)")
            f.write(chunk)
    return {"url": url_for(dest)}


@router.get("/templates")
def list_templates(category: str | None = None, mine: bool = False,
                   db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = select(SharedVideoLibrary)
    if mine:
        q = q.where(SharedVideoLibrary.creator_id == user.id)
    else:
        q = q.where(SharedVideoLibrary.status == "publish")
    if category:
        q = q.where(SharedVideoLibrary.category == category)
    q = q.order_by(SharedVideoLibrary.usage_count.desc(), SharedVideoLibrary.id.desc())
    return [tpl_out(t) for t in db.scalars(q)]


@router.post("/templates")
def create_template(body: TemplateIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    validate_schema(body.template_schema)
    for u in (body.base_video_url, body.thumbnail_url):
        if u and not resolve(u):
            raise HTTPException(422, f"File chưa được upload: {u}")
    t = SharedVideoLibrary(**body.model_dump(), creator_id=user.id, status="private")  # always private
    db.add(t)
    db.commit()
    if t.base_video_url and not t.thumbnail_url:
        t.thumbnail_url = library.thumbnail_url_for(t.base_video_url, f"tpl_{t.id}")
        db.commit()
    return tpl_out(t)


@router.get("/templates/{tid}")
def get_template(tid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    t = db.get(SharedVideoLibrary, tid)
    if not t or not visible_to(t, user):
        raise HTTPException(404, "Không tìm thấy template")
    return tpl_out(t)


<<<<<<< HEAD
@router.delete("/templates/{tid}")
def delete_template(tid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    t = db.get(SharedVideoLibrary, tid)
    if not t or (t.creator_id != user.id and user.role != "admin"):
        raise HTTPException(404, "Không tìm thấy template")
    used = db.scalar(select(func.count()).select_from(GenerationHistory)
                     .where(GenerationHistory.template_id == tid)) or 0
    if used:
        raise HTTPException(409, f"Template đang được dùng bởi {used} thành phẩm — không thể xóa")
    title = t.title
    db.delete(t)
    db.commit()
    log_activity(db, user.id, "template_delete", details={"template_id": tid, "title": title})
    return {"ok": True}


=======
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
# ---- AI helpers (free, no credit charge) ----
class ScriptIn(BaseModel):
    topic: str = Field(min_length=1, max_length=2000)
    tone: str = "hấp dẫn"
    seconds: int = Field(default=15, ge=5, le=120)
<<<<<<< HEAD
    model: str = ""
=======
    model: str = ai.DEFAULT_SCRIPT_MODEL
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa


class AnalyzeIn(BaseModel):
    image_url: str
    question: str = "Mô tả nội dung hình ảnh này để làm kịch bản video."
<<<<<<< HEAD
    model: str = ""


def _bill_model(db: Session, user: User, model: str, feature_key: str = "library_script"):
    """Reserve API model cost plus the configured feature policy."""
    key = f"m.{model}"
    p = pricing.price(db, key) if key in pricing.catalog() else 0.0
    if key in pricing.catalog() and not pricing.enabled(db, key):
        raise HTTPException(403, f"Model {model} đang được admin tạm tắt")
    from .. import featurebilling
    return featurebilling.reserve(db, user.id, feature_key, model_id=model,
                                  model_cost=p)
=======
    model: str = ai.DEFAULT_VISION_MODEL


def _bill_model(db: Session, user: User, model: str) -> float:
    """Charge the price of the model the user picked (0 = free). Refused if the admin switched it off."""
    if pricing.ai_key(model) not in pricing.catalog():
        return 0.0                                  # unknown id: the AI layer will reject it, nothing to charge
    if not pricing.enabled(db, pricing.ai_key(model)):
        raise HTTPException(403, f"Model {model} đang được admin tạm tắt")
    p = pricing.price(db, pricing.ai_key(model))
    if p > 0 and not credits.charge(db, user.id, p):
        db.rollback()
        raise HTTPException(402, detail={"message": "Không đủ credit, vui lòng nạp thêm", "required": p})
    db.commit()
    return p
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa


def _refund_model(db: Session, user: User, amount: float) -> None:
    if amount > 0:
<<<<<<< HEAD
        from .. import credits
=======
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
        credits.add_credits(db, user.id, amount)
        db.commit()


@router.get("/ai/models")
def ai_models(db: Session = Depends(get_db), user: User = Depends(current_user)):
<<<<<<< HEAD
    from ..modelregistry import all_models
    snap = pricing.snapshot(db)
    models = []
    for m in all_models():
        if m.step not in ("llm", "image_generate"):
            continue
        row = snap.get(f"m.{m.id}")
        p = row.price if row is not None else m.default_price
        enabled = (row.enabled if row is not None else True) and m.enabled
        models.append({**m.to_dict(), "price": p, "enabled": enabled})
    return {"models": models, "configured": bool(settings.vilao_api_key or settings.minimax_api_key)}
=======
    snap = pricing.snapshot(db)
    models = [{**m, "price": snap[pricing.ai_key(m["id"])].price if pricing.ai_key(m["id"]) in snap else 0,
               "enabled": snap[pricing.ai_key(m["id"])].enabled if pricing.ai_key(m["id"]) in snap else True}
              for m in MODEL_CATALOG]
    return {"models": models, "default_vision": ai.DEFAULT_VISION_MODEL,
            "default_script": ai.DEFAULT_SCRIPT_MODEL, "decision": ai.DECISION_MODEL,
            "configured": ai.configured()}
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa


@router.post("/ai/script")
def ai_script(body: ScriptIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
<<<<<<< HEAD
    from ..modelregistry import get_model as gm
    spec = gm(body.model)
    if spec is None:
        raise HTTPException(404, f"Model không tồn tại: {body.model}")
    if spec.step != "llm":
        raise HTTPException(422, f"Model {body.model} không thuộc bước LLM")
    from .. import adminmodels
    if not spec.enabled:
        raise HTTPException(403, f"Model {body.model} đang bị tắt")
    creds = adminmodels.creds(db, body.model)
    base_url = creds["base_url"] if creds else settings.vilao_base_url
    api_key = creds["api_key"] if creds else settings.vilao_api_key
    model_name = creds["model_name"] if creds else body.model
    usage = _bill_model(db, user, body.model)
    try:
        msg = ai.chat(model_name, [
            {"role": "system", "content": "Bạn là biên kịch video ngắn. Viết lời bình tiếng Việt, ngắn gọn, có hook mở đầu và CTA cuối."},
            {"role": "user", "content": f"Chủ đề: {body.topic}\\nGiọng điệu: {body.tone}\\nĐộ dài: khoảng {body.seconds} giây."},
        ], base_url=base_url, api_key=api_key)
        text = msg.get("content") or ""
        from .. import featurebilling
        featurebilling.finish(db, usage.id, success=bool(text))
        return {"script": text, "model_used": body.model, "credits_charged": usage.charge}
    except Exception as e:
        from .. import featurebilling
        featurebilling.finish(db, usage.id, success=False)
        logger.exception("[library-script] generation failed")
        raise HTTPException(502, "Không tạo được kịch bản. Vui lòng thử lại sau.") from e
=======
    paid = _bill_model(db, user, body.model)
    try:
        text, used = ai.generate_script_ex(body.topic, tone=body.tone, seconds=body.seconds, model=body.model,
                                           disabled=frozenset(pricing.disabled_models(db)))
        return {"script": text, "model_used": used, "credits_charged": paid}
    except ai.AIError as e:
        _refund_model(db, user, paid)               # no answer, no charge
        raise HTTPException(502, str(e))
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa


@router.post("/ai/analyze")
def ai_analyze(body: AnalyzeIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = resolve(body.image_url)
    if not p:
        raise HTTPException(404, "Ảnh chưa được upload")
<<<<<<< HEAD
    from ..modelregistry import get_model as gm
    spec = gm(body.model) if body.model else None
    if body.model and spec is None:
        raise HTTPException(404, f"Model không tồn tại: {body.model}")
    if body.model and (spec.step != "image_generate" if spec else False):
        raise HTTPException(422, f"Model {body.model} không thuộc bước Gen ảnh")
    from .. import adminmodels
    creds = adminmodels.creds(db, body.model) if body.model else None
    base_url = (creds["base_url"] if creds else settings.vilao_base_url)
    api_key = (creds["api_key"] if creds else settings.vilao_api_key)
    model_name = (creds["model_name"] if creds else (body.model or ""))
    usage = _bill_model(db, user, body.model, feature_key="library_analyze") if body.model else None
    try:
        from pathlib import Path
        import base64
        with p.open("rb") as f:
            raw = f.read()
        ext = Path(body.image_url).suffix.lower()
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp",
                "gif": "image/gif"}.get(ext.lstrip("."), "image/png")
        b64 = base64.b64encode(raw).decode()
        msg = ai.chat(model_name, [
            {"role": "system", "content": "Bạn là chuyên gia phân tích hình ảnh. Trả lời bằng tiếng Việt."},
            {"role": "user", "content": [
                {"type": "text", "text": body.question},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ]},
        ], base_url=base_url, api_key=api_key)
        text = msg.get("content") or ""
        if usage:
            from .. import featurebilling
            featurebilling.finish(db, usage.id, success=bool(text))
        return {"analysis": text, "model_used": body.model, "credits_charged": usage.charge if usage else 0}
    except Exception as e:
        if usage:
            from .. import featurebilling
            featurebilling.finish(db, usage.id, success=False)
        logger.exception("[library-analyze] model call failed")
        raise HTTPException(502, "Không phân tích được ảnh. Vui lòng thử lại.") from e
=======
    paid = _bill_model(db, user, body.model)
    try:
        text, used = ai.analyze_image_ex(p, body.question, body.model,
                                         disabled=frozenset(pricing.disabled_models(db)))
        return {"analysis": text, "model_used": used, "credits_charged": paid}
    except ai.AIError as e:
        _refund_model(db, user, paid)
        raise HTTPException(502, str(e))
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa

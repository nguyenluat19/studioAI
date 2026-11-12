"""AI Assistant: Pipeline from idea -> script prompt & suggestions -> character image -> video generation & summary table."""
import json
<<<<<<< HEAD
import logging
import secrets
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import pricing
from ..activity import log_activity
from ..config import settings
from ..db import get_db
from ..deps import current_user
from ..media import resolve, url_for, voice_meta_dir as _voice_meta_dir
from ..models import User
from ..modelregistry import get_model, clip_count_for_duration, validate_selections
from .. import videopipeline
from .. import tts as tts_mod

router = APIRouter(prefix="/api/assistant", tags=["assistant"])
logger = logging.getLogger(__name__)


def _assert_models_enabled(db: Session, selections: dict) -> None:
    """Chặn model bị admin tắt (theo key giá duy nhất của model) trước khi chạy pipeline."""
    cat = pricing.catalog()
    snap = pricing.snapshot(db)
    for step, mid in selections.items():
        if not mid:
            continue
        key = pricing.video_pricing_key(mid)
        if key not in cat:
            key = f"m.{mid}"
        if key not in cat:
            continue
        row = snap.get(key)
        if row is not None and not row.enabled:
            raise HTTPException(403, f"Model {mid} đang bị admin tắt")


class VoicePreviewIn(BaseModel):
    voice: str = "vi-VN-HoaiMyNeural"
    text: str = "Xin chào, đây là giọng đọc demo."
    language: str = "vi"
    gender: str | None = None


@router.get("/presets")
def list_sales_presets():
    """Preset bán hàng theo ngành hàng (dùng để kịch bản đi đúng tệp khách & nỗi đau)."""
    from ..presets import list_presets as _list
    return {"presets": _list()}


@router.post("/voice-preview")
def voice_preview(body: VoicePreviewIn, user: User = Depends(current_user)):
    from ..media import url_for, user_outputs_dir
    dest = user_outputs_dir(user.id) / f"voice_preview_{secrets.token_hex(4)}.mp3"
    text = (getattr(body, "text", "") or "").strip() or "Xin chao, day la giong doc demo."
    lang = tts_mod.norm_lang(body.language)
    voice = tts_mod.resolve_voice(body.voice, body.gender, language=lang)
    valid = {v["id"] for v in tts_mod.list_voices()}
    if voice not in valid and not voice.startswith("el:"):
        raise HTTPException(422, "Giọng đọc này không hợp lệ")
    try:
        tts_mod.gen_tts(text, dest, voice=voice)
    except Exception as e:
        raise HTTPException(502, str(e))
    return {"url": url_for(dest), "voice": voice}
=======
import re
import secrets
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import ai, credits, pricing
from ..activity import log_activity
from ..config import MODEL_CATALOG, settings
from ..db import get_db
from ..deps import current_user
from ..media import resolve, url_for
from ..models import GenerationHistory, SharedVideoLibrary, User
from ..tasks import ai_render_task, broker_up, run_generation
from ..modelregistry import models_for_step, get_model, clip_count_for_duration, validate_selections
from ..modelregistry import ModelSpec
from .. import videopipeline
from ..autopipeline import _safe_str

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class IdeaIn(BaseModel):
    idea: str = Field(min_length=3, max_length=3000)
    model_llm: str = Field(default="deepseek-v4-pro-0813")
    model_image: str = Field(default="deepseek-v4-flash-vision")
    model_video: str = Field(default="wan2.1")
    duration: int = Field(default=60, ge=5, le=300)
    aspect_ratio: str = "9:16"
    character_image_url: str = ""
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa


class PlanIn(BaseModel):
    idea: str = Field(min_length=3, max_length=3000)
<<<<<<< HEAD
    model_llm: str = Field(default="")
    model_image: str = Field(default="")
    model_video: str = Field(default="")
    duration: int = Field(default=60, ge=1, le=300)
    aspect_ratio: str = "9:16"
    character_image_url: str = ""
    language: str = "vi"
=======
    model_llm: str = Field(default="deepseek-v4-pro-0813")
    model_image: str = Field(default="deepseek-v4-flash-vision")
    model_video: str = Field(default="wan2.1")
    duration: int = Field(default=60, ge=5, le=300)
    aspect_ratio: str = "9:16"
    character_image_url: str = ""
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa


@router.post("/plan")
def plan_storyboard(body: PlanIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Phân tích yêu cầu + tạo storyboard (kịch bản + các cảnh)."""
    from ..modelregistry import validate_selections
<<<<<<< HEAD
    errs = validate_selections({"llm": body.model_llm, "video_i2v": body.model_video}, required=["llm", "video_i2v"])
    if errs:
        raise HTTPException(422, "; ".join(errs))
    _assert_models_enabled(db, {"llm": body.model_llm, "video_i2v": body.model_video})

    from .. import adminmodels
    creds = adminmodels.creds(db, body.model_llm)
=======
    errs = validate_selections({"llm": body.model_llm, "video_i2v": body.model_video})
    if errs:
        raise HTTPException(422, "; ".join(errs))

    if pricing.ai_key(body.model_llm) in pricing.catalog() and not pricing.enabled(db, pricing.ai_key(body.model_llm)):
        raise HTTPException(403, f"Model {body.model_llm} đang bị admin tắt")
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa

    try:
        result = videopipeline.plan_storyboard(
            topic=body.idea,
            model_id=body.model_llm,
            duration_seconds=body.duration,
            aspect_ratio=body.aspect_ratio,
            character_image_url=body.character_image_url.strip() or None,
<<<<<<< HEAD
            creds=creds,
            language=body.language,
=======
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
        )
    except Exception as e:
        raise HTTPException(502, f"Lỗi tạo storyboard: {e}")

    log_activity(db, user.id, "assistant_plan", details={
        "idea": body.idea[:100], "model_llm": body.model_llm,
        "model_video": body.model_video, "duration": body.duration,
<<<<<<< HEAD
        "num_scenes": result.get("tổng_số_cảnh", 0),
=======
        "num_scenes": result["tong_so_canh"],
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
    })
    return {
        "plan": result,
        "models": {"llm": body.model_llm, "video": body.model_video},
<<<<<<< HEAD
        "clip_count": clip_count_for_duration(
            get_model(body.model_video), body.duration) if get_model(body.model_video) else 1,
=======
        "clip_count": videopipeline.clip_count_for_duration(
            videopipeline.get_model(body.model_video), body.duration) if videopipeline.get_model(body.model_video) else 1,
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
    }


class KeyframesIn(BaseModel):
    plan: dict
    model_image: str = Field(default="deepseek-v4-flash-vision")
    character_image_url: str = ""


@router.post("/keyframes")
def generate_keyframes(body: KeyframesIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Tạo ảnh từng cảnh (keyframe) từ storyboard."""
    from ..modelregistry import validate_selections
    errs = validate_selections({"image_generate": body.model_image})
    if errs:
        raise HTTPException(422, "; ".join(errs))

    plan = body.plan
<<<<<<< HEAD
    scenes = plan.get("các_cảnh") or plan.get("cac_canh", [])
=======
    scenes = plan.get("cac_canh", [])
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
    character_bible = plan.get("character_bible", {})
    style_bible = plan.get("style_bible", {})

    keyframes = []
    for scene in scenes:
        prompt = videopipeline.gen_keyframe_prompt(
            scene, character_bible, style_bible,
            body.character_image_url.strip() or None,
<<<<<<< HEAD
            characters=plan.get("nhân_vật", []) or [],
            location_bible=plan.get("location_bible", {}),
=======
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
        )
        keyframes.append({
            "stt": scene["stt"],
            "prompt": prompt,
            "scene": scene,
        })

    log_activity(db, user.id, "assistant_keyframes", details={
        "num_scenes": len(keyframes), "model_image": body.model_image,
    })
    return {
        "keyframes": keyframes,
        "model_image": body.model_image,
        "num_scenes": len(keyframes),
    }


class GenScenesIn(BaseModel):
    plan: dict
    keyframes: list[dict] = Field(default_factory=list)
<<<<<<< HEAD
    model_video: str = "minimax-h3-768p"
=======
    model_video: str = "wan2.1"
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
    resolution: str = "720P"
    ratio: str = "9:16"
    character_image_url: str = ""


@router.post("/gen-scenes")
def gen_scenes(body: GenScenesIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Chuẩn bị gen video từng cảnh."""
    from ..modelregistry import get_model
    vm = get_model(body.model_video)
    if not vm or vm.step not in ("video_i2v", "video_t2v"):
        raise HTTPException(422, f"Model {body.model_video} không phải model video")

    plan = body.plan
<<<<<<< HEAD
    scenes = plan.get("các_cảnh") or plan.get("cac_canh", [])

    from .. import pricing as _pricing
    vkey = _pricing.video_pricing_key(body.model_video)
    if vkey and vkey in _pricing.catalog():
        price_per_sec = _pricing.price(db, vkey)
        estimated = round(sum(max(2, int(s.get("thời_lượng_giây", 4))) for s in scenes) * price_per_sec, 2)
    else:
        estimated = 0.0
=======
    scenes = plan.get("cac_canh", [])
    total_duration = plan.get("tong_thoi_luong", 60)

    estimated = 0.0
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa

    fresh = db.get(User, user.id)
    if fresh.credits_balance < estimated and estimated > 0:
        raise HTTPException(402, detail={
            "message": "Không đủ credit, vui lòng nạp thêm",
            "required": estimated, "balance": fresh.credits_balance})

    log_activity(db, user.id, "assistant_gen_scenes", details={
        "model_video": body.model_video, "num_scenes": len(scenes),
        "estimated_cost": estimated,
    })
    return {
        "status": "ready",
        "num_scenes": len(scenes),
        "estimated_cost": estimated,
        "model_video": body.model_video,
        "clip_count_per_scene": [videopipeline.scene_clip_count(s, body.model_video) for s in scenes],
        "message": "Sẵn sàng gen video.",
    }


class EditIn(BaseModel):
    scene_video_urls: list[str] = Field(default_factory=list)
    transition: str = "fade"
    music_url: str = ""
    subtitle_srt: str = ""
    output_ratio: str = "9:16"


@router.post("/edit")
def edit_final(body: EditIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Dựng thành phẩm từ các clip rời (FFmpeg)."""
    if not body.scene_video_urls:
        raise HTTPException(422, "Cần ít nhất một clip để dựng")

    from ..media import resolve
    clips = []
    for url in body.scene_video_urls:
        p = resolve(url)
        if p and p.exists():
            clips.append(p)

    if not clips:
        raise HTTPException(422, "Không tìm thấy clip cục bộ để dựng")

    import subprocess
    import tempfile
    from pathlib import Path

<<<<<<< HEAD
    from ..media import user_outputs_dir
    out = user_outputs_dir(user.id) / f"final_{secrets.token_hex(6)}.mp4"
=======
    settings.outputs_dir.mkdir(parents=True, exist_ok=True)
    out = settings.outputs_dir / f"final_{user.id}_{secrets.token_hex(6)}.mp4"
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa

    concat_file = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            concat_file = Path(f.name)
            for clip in clips:
                f.write(f"file '{clip.resolve().as_posix()}'\n")

        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
               "-c:v", "libx264", "-preset", "fast", "-crf", "23",
               "-c:a", "aac", "-shortest", str(out)]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if res.returncode != 0:
            raise HTTPException(500, f"FFmpeg lỗi: {res.stderr[-500:]}")
    finally:
        if concat_file:
            concat_file.unlink(missing_ok=True)

    video_url = url_for(out)
    log_activity(db, user.id, "assistant_edit", details={
        "num_clips": len(clips), "output_url": video_url,
    })
    return {
        "output_video_url": video_url,
        "success": True,
        "num_clips": len(clips),
    }


class EstimateIn(BaseModel):
    selections: dict = Field(default_factory=dict)
    duration: int = Field(default=60)
    num_scenes: int = Field(default=6)


@router.post("/estimate")
def estimate_cost(body: EstimateIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Ước tính chi phí trước khi bấm Gen."""
    est = videopipeline.estimated_cost(
        body.selections, body.duration, body.num_scenes, db=db,
    )
    return est


<<<<<<< HEAD
# ==================== PIPELINE TỰ ĐỘNG 1-CLICK (server-side) ====================

class StartPipelineIn(BaseModel):
    idea: str = Field(min_length=3, max_length=3000)
    model_llm: str = Field(default="")
    model_image: str = Field(default="")
    model_video: str = Field(default="")
    duration: int = Field(default=60, ge=1, le=300)
    aspect_ratio: str = "9:16"
    character_image_url: str = ""
    voice: str = "native"
    use_tts: bool = False
    language: str = "vi"
    mode: str = "standard"
    outfit_image_url: str = ""
    hook_seconds: int = Field(default=3, ge=1, le=10)
    preset: str = ""


def _pipeline_job_or_403(job_id: str, user: User):
    from ..autopipeline import get_job
    job = get_job(job_id)
    if job is None:
        raise HTTPException(404, "Không tìm thấy job pipeline")
    if job.user_id != user.id and getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Không có quyền xem job này")
    return job


@router.post("/pipeline")
def start_auto_pipeline(body: StartPipelineIn, db: Session = Depends(get_db),
                        user: User = Depends(current_user)):
    """Bắt đầu pipeline tự động 1-click: storyboard -> keyframes -> video (MiniMax/model admin) -> dựng."""
    if body.mode not in ("standard", "review_outfit", "images_only", "text_to_video", "image_to_video"):
        raise HTTPException(422, "Chế độ pipeline không hợp lệ")
    images_only = body.mode == "images_only"
    single_clip = body.mode in ("text_to_video", "image_to_video")
    if body.mode == "review_outfit":
        if not body.outfit_image_url.strip() or not body.character_image_url.strip():
            raise HTTPException(422,
                "Chế độ review sản phẩm cần cả ảnh nhân vật và ảnh bộ đồ/sản phẩm muốn review")
    if body.mode == "image_to_video" and not body.character_image_url.strip():
        raise HTTPException(422, "Chế độ Ảnh → Video cần ảnh nhân vật (upload 1 ảnh)")
    sel_check = {"llm": body.model_llm}
    if not images_only:
        sel_check["video_i2v"] = body.model_video
    if not single_clip and not images_only:
        sel_check["image_generate"] = body.model_image
    errs = validate_selections(sel_check)
    if errs:
        raise HTTPException(422, "; ".join(errs))
    _assert_models_enabled(db, sel_check)
    est = videopipeline.estimated_cost(
        {"llm": body.model_llm, "image_generate": body.model_image, "video_i2v": body.model_video},
        body.duration, max(1, __import__("math").ceil(body.duration / 6)), db=db,
    )
    estimated_api_cost = float(est.get("tổng_credit") or 0.0)
    if estimated_api_cost > 0:
        db.refresh(user)
        if user.credits_balance < estimated_api_cost:
            raise HTTPException(402, detail={
                "message": "Không đủ credit dự kiến để chạy pipeline này",
                "required": estimated_api_cost, "balance": user.credits_balance})
    from .. import featurebilling
    feature_key = "assistant_images" if images_only else "assistant_pipeline"
    model_cost = 0.0  # API costs are charged per successful model call inside the pipeline.
    usage_id: int | None = None
    usage = featurebilling.reserve(db, user.id, feature_key, model_id=body.model_video or body.model_llm,
                                   units=1, ref_id="pipeline", model_cost=model_cost)
    usage_id = usage.id
    from .. import autopipeline
    from ..presets import get_preset
    preset = get_preset(body.preset)
    if body.preset and not preset:
        featurebilling.finish(db, usage.id, success=False)
        raise HTTPException(422, "Preset ngành hàng không hợp lệ")
    try:
        job_id = autopipeline.create_job(
            user_id=user.id,
            selections={"llm": body.model_llm, "image_generate": body.model_image, "video_i2v": body.model_video},
            idea=body.idea,
            duration=body.duration,
            aspect_ratio=body.aspect_ratio,
            character_image_url=body.character_image_url.strip() or None,
            voice=getattr(body, "voice", "native"),
            use_tts=getattr(body, "use_tts", False),
            language=getattr(body, "language", "vi"),
            mode=body.mode,
            outfit_image_url=body.outfit_image_url.strip() or None,
            hook_seconds=body.hook_seconds,
            preset=(preset or {}).get("id", ""),
            usage_id=usage_id,
        )
    except Exception:
        featurebilling.finish(db, usage.id, success=False)
        raise HTTPException(500, "Không thể tạo pipeline")
    autopipeline.start_pipeline(job_id)
    log_activity(db, user.id, "assistant_pipeline_start", details={
        "job_id": job_id, "idea": body.idea[:100], "duration": body.duration, "mode": body.mode,
        "models": {"llm": body.model_llm, "image": body.model_image, "video": body.model_video},
    })
    return {"job_id": job_id, "status": "queued"}


@router.post("/pipeline/{job_id}/cancel")
def cancel_pipeline(job_id: str, user: User = Depends(current_user)):
    """Dừng pipeline đang chạy."""
    job = _pipeline_job_or_403(job_id, user)
    job.cancel()
    return {"status": "cancelled", "job_id": job_id}


@router.get("/pipeline/{job_id}/status")
def auto_pipeline_status(job_id: str, user: User = Depends(current_user)):
    """UI poll tiến độ pipeline (mỗi 2s)."""
    return _pipeline_job_or_403(job_id, user).to_dict()


@router.get("/pipeline/{job_id}/result")
def auto_pipeline_result(job_id: str, user: User = Depends(current_user)):
    """Kết quả pipeline khi hoàn tất."""
    job = _pipeline_job_or_403(job_id, user)
    d = job.to_dict()
    if d["status"] not in ("done", "failed"):
        raise HTTPException(409, f"Pipeline chưa hoàn tất (trạng thái: {d['status']})")
    return {"status": d["status"], "error": d["error"], "result": d["result"]}


@router.post("/pipeline/{job_id}/save")
def save_pipeline_as_template(job_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Lưu kết quả pipeline thành template cá nhân (SharedVideoLibrary private).

    Pipeline đã tự động lưu khi hoàn tất; endpoint này idempotent —
    gọi lại chỉ trả về bản đã lưu, không tạo bản trùng."""
    job = _pipeline_job_or_403(job_id, user)
    d = job.to_dict()
    if d["status"] != "done":
        raise HTTPException(409, "Pipeline chưa hoàn tất, không thể lưu")
    from ..autopipeline import save_pipeline_template
    saved = save_pipeline_template(job, db)
    if not saved:
        raise HTTPException(409, "Chưa có kết quả để lưu (không có clip hoặc storyboard)")
    log_activity(db, user.id, "pipeline_save_template",
                 details={"job_id": job_id, "template_id": saved["id"]})
    return saved


@router.post("/pipeline/{job_id}/retry-failed")
def retry_failed(job_id: str, user: User = Depends(current_user)):
    """Gen lại đúng các cảnh CHƯA có clip của job đã xong (người dùng bấm "Tạo lại cảnh lỗi").

    Chạy nền; trừ credit chỉ cho cảnh thành công; tự cập nhật dự án đã lưu trong
    "Template của tôi" (nếu có)."""
    from .. import autopipeline
    job = _pipeline_job_or_403(job_id, user)
    if getattr(job, "mode", "standard") == "images_only":
        raise HTTPException(409, "Chế độ chỉ gen ảnh — không có cảnh video để tạo lại")
    if job.status not in ("done", "failed"):
        raise HTTPException(409, f"Pipeline chưa kết thúc (trạng thái: {job.status})")
    failed = [kf for kf in (job.result or {}).get("keyframes", []) if not kf.get("video_url")]
    if not failed:
        return {"retried": 0, "message": "Không có cảnh lỗi để tạo lại"}
    job.update(status="rendering", progress=60, step=f"Đang tạo lại {len(failed)} cảnh lỗi...")
    threading.Thread(target=autopipeline.retry_failed_scenes, args=(job_id,), daemon=True).start()
    return {"retried": len(failed), "status": "queued"}


# ==================== GEN HÀNG LOẠT (REVIEW TỪNG SẢN PHẨM) ====================

_BATCH_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif")


@router.post("/batch/extract")
def extract_batch_products(file: UploadFile = File(...), user: User = Depends(current_user)):
    """Nhận 1 file .zip (nhiều ảnh sản phẩm) hoặc 1 ảnh lẻ -> danh sách URL đã upload."""
    import io
    import zipfile
    from .. import vilao_image

    raw = file.file.read()
    if not raw:
        raise HTTPException(422, "File rỗng")
    name = (file.filename or "").lower()
    from ..media import user_uploads_dir
    _uploads = user_uploads_dir(user.id)
    urls: list[str] = []
    titles: list[str] = []

    def _save(data: bytes, ext: str, stem: str) -> str:
        dest = _uploads / f"batch_{secrets.token_hex(8)}{ext}"
        dest.write_bytes(data)
        titles.append(stem[:120])
        return url_for(dest)

    if name.endswith(".zip"):
        if len(raw) > 40 * 1024 * 1024:
            raise HTTPException(422, "File ZIP quá lớn (tối đa 40MB)")
        try:
            zf = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile:
            raise HTTPException(422, "File ZIP không hợp lệ")
        entries = [e for e in zf.infolist()
                   if not e.is_dir() and e.filename.lower().endswith(_BATCH_IMAGE_EXT)
                   and not e.filename.startswith("__MACOSX/")]
        if not entries:
            raise HTTPException(422, "File ZIP không có ảnh hợp lệ (.png/.jpg/.jpeg/.webp/.gif)")
        total = 0
        for e in entries:
            if len(urls) >= 20:
                break
            if e.file_size > 15 * 1024 * 1024:
                continue
            total += e.file_size
            if total > 80 * 1024 * 1024:
                break
            try:
                data = zf.read(e)
            except Exception as exc:  # entry hỏng -> bỏ qua
                logger.warning("Bỏ qua ảnh hỏng trong ZIP %s: %s", e.filename, exc)
                continue
            if not vilao_image._is_image(data):
                continue
            ext = Path(e.filename).suffix.lower()
            urls.append(_save(data, ext, Path(e.filename).stem))
    elif name.endswith(_BATCH_IMAGE_EXT):
        if len(raw) > 15 * 1024 * 1024:
            raise HTTPException(422, "Ảnh quá lớn (tối đa 15MB)")
        if not vilao_image._is_image(raw):
            raise HTTPException(422, "Dữ liệu không phải ảnh hợp lệ")
        ext = Path(name).suffix.lower()
        urls.append(_save(raw, ext, Path(name).stem))
    else:
        raise HTTPException(422, "Chỉ nhận ảnh (.png/.jpg/.jpeg/.webp/.gif) hoặc file .zip")
    if not urls:
        raise HTTPException(422, "Không có ảnh sản phẩm hợp lệ nào")
    return {"urls": urls, "titles": titles, "count": len(urls)}


class StartBatchIn(BaseModel):
    idea: str = Field(default="", max_length=3000)
    model_llm: str = Field(default="")
    model_image: str = Field(default="")
    model_video: str = Field(default="")
    duration: int = Field(default=60, ge=1, le=300)
    aspect_ratio: str = "9:16"
    character_image_url: str = ""
    product_image_urls: list[str] = Field(min_length=1, max_length=20)
    product_titles: list[str] = Field(default_factory=list)
    voice: str = "native"
    use_tts: bool = False
    language: str = "vi"
    hook_seconds: int = Field(default=3, ge=1, le=10)


def _batch_or_403(batch_id: str, user: User):
    from ..batchpipeline import get_batch
    batch = get_batch(batch_id)
    if batch is None:
        raise HTTPException(404, "Không tìm thấy batch")
    if batch.user_id != user.id and getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Không có quyền xem batch này")
    return batch


@router.post("/batch")
def start_batch(body: StartBatchIn, db: Session = Depends(get_db),
                user: User = Depends(current_user)):
    """Bắt đầu gen hàng loạt: mỗi ảnh sản phẩm chạy pipeline review, lần lượt từng sản phẩm."""
    errs = validate_selections({
        "llm": body.model_llm, "image_generate": body.model_image, "video_i2v": body.model_video,
    })
    if errs:
        raise HTTPException(422, "; ".join(errs))
    _assert_models_enabled(db, {
        "llm": body.model_llm, "image_generate": body.model_image, "video_i2v": body.model_video,
    })
    if not body.character_image_url.strip():
        raise HTTPException(422, "Cần ảnh nhân vật cho batch review")
    if not resolve(body.character_image_url.strip()):
        raise HTTPException(422, "Không tìm thấy ảnh nhân vật đã upload")
    # Upfront guard: ước tính tổng credit cho cả batch (LLM + ảnh + video mỗi sản phẩm)
    import math
    from .. import videopipeline as _vp
    num_scenes = max(1, math.ceil(body.duration / 6))
    try:
        est = _vp.estimated_cost(
            {"llm": body.model_llm, "image_generate": body.model_image, "video_i2v": body.model_video},
            body.duration, num_scenes, db=db)
        est_total = float(est.get("tổng_credit") or 0.0) * max(len(body.product_image_urls), 1)
    except Exception:
        est_total = 0.0
    if est_total > 0:
        fresh = db.get(User, user.id)
        db.refresh(fresh)
        if fresh.credits_balance < est_total:
            raise HTTPException(402, detail={
                "message": f"Không đủ credit — ước tính cả batch cần tối thiểu {est_total:.0f} credit. Vui lòng nạp thêm.",
                "required": est_total, "balance": fresh.credits_balance})

    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for i, url in enumerate(body.product_image_urls):
        u = (url or "").strip()
        if not u or u in seen:  # mỗi sản phẩm chỉ làm 1 lần
            continue
        if not resolve(u):
            raise HTTPException(422, f"Không tìm thấy ảnh sản phẩm đã upload: {u}")
        seen.add(u)
        title = body.product_titles[i] if i < len(body.product_titles) else ""
        pairs.append((u, title))
    if not pairs:
        raise HTTPException(422, "Cần ít nhất 1 ảnh sản phẩm")

    from .. import featurebilling
    usage_ids = []
    try:
        for _ in pairs:
            usage_ids.append(featurebilling.reserve(
                db, user.id, "assistant_batch_item",
                model_id=body.model_video or body.model_llm,
                units=1, ref_id="batch", model_cost=0.0).id)
    except Exception:
        for usage_id in usage_ids:
            featurebilling.finish(db, usage_id, success=False)
        raise
    from .. import batchpipeline
    try:
        batch_id = batchpipeline.create_batch(
            user_id=user.id,
            selections={"llm": body.model_llm, "image_generate": body.model_image,
                        "video_i2v": body.model_video},
            idea=body.idea.strip() or "Video review sản phẩm",
            duration=body.duration,
            aspect_ratio=body.aspect_ratio,
            character_image_url=body.character_image_url.strip(),
            product_urls=[p[0] for p in pairs],
            product_titles=[p[1] for p in pairs],
            voice=body.voice,
            use_tts=body.use_tts,
            language=body.language,
            hook_seconds=body.hook_seconds,
            usage_ids=usage_ids,
        )
    except Exception as e:
        for usage_id in usage_ids:
            featurebilling.finish(db, usage_id, success=False)
        if isinstance(e, ValueError):
            raise HTTPException(422, str(e))
        raise HTTPException(500, "Không thể tạo batch")
    batchpipeline.start_batch(batch_id)
    log_activity(db, user.id, "assistant_batch_start", details={
        "batch_id": batch_id, "total": len(pairs), "duration": body.duration,
        "models": {"llm": body.model_llm, "image": body.model_image, "video": body.model_video},
    })
    return {"batch_id": batch_id, "status": "queued", "total": len(pairs)}


@router.get("/batch/{batch_id}/status")
def batch_status(batch_id: str, user: User = Depends(current_user)):
    """Tiến độ batch: từng sản phẩm (hàng chờ / đang làm / xong / lỗi + kịch bản, keyframe)."""
    return _batch_or_403(batch_id, user).to_dict()


@router.post("/batch/{batch_id}/cancel")
def cancel_batch(batch_id: str, user: User = Depends(current_user)):
    """Dừng batch: dừng sản phẩm đang chạy, các sản phẩm còn lại bị hủy khỏi hàng chờ."""
    batch = _batch_or_403(batch_id, user)
    batch.cancel()
    return {"status": "cancelled", "batch_id": batch_id}


@router.post("/batch/{batch_id}/retry-failed")
def retry_batch_failed(batch_id: str, user: User = Depends(current_user)):
    """Thử lại CHỈ các sản phẩm bị lỗi của batch (trừ credit như lần chạy đầu, tốn credit thật)."""
    from .. import batchpipeline
    _batch_or_403(batch_id, user)  # check tồn tại/quyền (tự raise 404/403)
    try:
        return batchpipeline.retry_batch_items(batch_id)
    except ValueError as e:
        raise HTTPException(409, str(e))


# ==================== BÀI VIẾT (LINK) → VIDEO 60s ====================
class ArticlePreviewIn(BaseModel):
    url: str = ""
    text: str = ""


class ArticleStartIn(BaseModel):
    url: str = ""
    text: str = ""
    model_llm: str = ""
    model_image: str = ""
    model_video: str = ""
    video_mode: str = "slide"          # slide = ảnh + TTS (rẻ) | video = dùng model video thật
    duration: int = Field(default=60, ge=15, le=180)
    aspect_ratio: str = "9:16"
    voice: str = "auto"
    language: str = "vi"


@router.post("/article/preview")
def article_preview(body: ArticlePreviewIn, user: User = Depends(current_user)):
    """Đọc tiêu đề + đoạn mở đầu của bài viết (chưa tốn credit)."""
    from .. import article as article_mod
    try:
        if body.text.strip():
            art = {"title": body.text.strip()[:120], "text": body.text.strip(),
                   "url": ""}
        else:
            art = article_mod.fetch_article(body.url)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"title": art["title"], "excerpt": art["text"][:600],
            "chars": len(art["text"]), "url": art.get("url", "")}


@router.get("/article/estimate")
def article_estimate(duration: int = 60, model_llm: str = "", model_image: str = "",
                      model_video: str = "", video_mode: str = "slide",
                      db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Ước tính credit: 1 lượt LLM + 1 ảnh mỗi cảnh (+ 1 request model video/cảnh nếu dựng bằng model)."""
    from .. import article as article_mod
    num_scenes = max(3, min(12, round(duration / 8)))
    return article_mod.estimated_cost(model_llm, model_image, num_scenes, db,
                                      model_video=model_video, video_mode=video_mode)


@router.post("/article")
def article_start(body: ArticleStartIn, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    """Bắt đầu dựng video từ bài viết: kịch bản → ảnh → giọng đọc → video + phụ đề."""
    from .. import article as article_mod
    from ..modelregistry import validate_selections
    # Chế độ này KHÔNG dùng model video (ảnh + TTS là đủ) → chỉ bắt buộc LLM + ảnh
    errs = validate_selections({"llm": body.model_llm, "image_generate": body.model_image},
                              required=["llm", "image_generate"])
    if body.video_mode == "video":
        errs += validate_selections({"video_i2v": body.model_video}, required=["video_i2v"])
    if errs:
        raise HTTPException(422, "; ".join(errs))
    _assert_models_enabled(db, {"llm": body.model_llm, "image_generate": body.model_image,
                                "video_i2v": body.model_video if body.video_mode == "video" else ""})

    text = body.text.strip()
    if not text and not body.url.strip():
        raise HTTPException(422, "Cần link bài viết hoặc dán nội dung bài viết")
    num_scenes = max(3, min(12, round(body.duration / 8)))
    try:
        est = article_mod.estimated_cost(body.model_llm, body.model_image, num_scenes, db,
                                         model_video=body.model_video, video_mode=body.video_mode)
    except Exception:
        est = {"tong_credit": 0.0}
    if est.get("tong_credit"):
        fresh = db.get(User, user.id)
        db.refresh(fresh)
        if fresh.credits_balance < est["tong_credit"]:
            raise HTTPException(402, detail={
                "message": f"Không đủ credit — cần tối thiểu {est['tong_credit']:.0f} credit. Vui lòng nạp thêm.",
                "required": est["tong_credit"], "balance": fresh.credits_balance})

    payload = {"url": body.url.strip(), "text": text, "model_llm": body.model_llm,
               "model_image": body.model_image, "model_video": body.model_video,
               "video_mode": body.video_mode, "duration": body.duration,
               "aspect_ratio": body.aspect_ratio, "voice": body.voice,
               "language": body.language}
    from .. import featurebilling
    usage = featurebilling.reserve(db, user.id, "article_video", model_id=body.model_video or body.model_llm,
                                   units=1, model_cost=0.0)
    try:
        job_id = article_mod.create_job(user.id, payload, usage_id=usage.id)
    except Exception:
        featurebilling.finish(db, usage.id, success=False)
        raise
    article_mod.start_job(job_id)
    log_activity(db, user.id, "article_to_video", details={
        "job_id": job_id, "url": body.url.strip()[:200], "duration": body.duration,
        "num_scenes": num_scenes})
    return {"job_id": job_id, "status": "queued", "num_scenes": num_scenes,
            "estimated_cost": est.get("tong_credit", 0.0)}


@router.get("/article/{job_id}/status")
def article_status(job_id: str, user: User = Depends(current_user)):
    """Tiến độ dựng video từ bài viết."""
    from .. import article as article_mod
    job = article_mod.get_job(job_id)
    if job is None:
        raise HTTPException(404, "Không tìm thấy job")
    if job.user_id != user.id and getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Không có quyền xem job này")
    return job.to_dict()


@router.get("/voices")
def list_voices():
    """Giọng đọc TTS tiếng Việt (edge-tts) cho pipeline."""
    return {"voices": tts_mod.list_voices()}


@router.post("/voice-upload")
def voice_upload(file: UploadFile = File(...), user: User = Depends(current_user)):
    """Upload giọng đọc mẫu để clone (lưu vào storage/voices)."""
    import shutil
    if not file.filename or not file.filename.lower().endswith(('.mp3', '.wav', '.ogg', '.m4a', '.flac')):
        raise HTTPException(422, "Chỉ chấp nhận file âm thanh (.mp3, .wav, .ogg, .m4a, .flac)")
    settings.voices_dir.mkdir(parents=True, exist_ok=True)
    vid = secrets.token_hex(8)
    fname = f"voice_{vid}{Path(file.filename).suffix}"
    from ..media import user_voices_dir
    dest = user_voices_dir(user.id) / fname
    # Đường dẫn tương đối trong meta (kèm thư mục riêng của user) → URL /media/voices/u<id>/...
    safe_name = f"u{user.id}/{fname}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    if dest.stat().st_size < 1000:
        dest.unlink(missing_ok=True)
        raise HTTPException(422, "File âm thanh quá nhỏ (tối thiểu ~1 giây)")
    meta = {"id": vid, "name": f"Voice {vid[:6]}", "file": safe_name,
            "size": dest.stat().st_size, "user_id": user.id, "provider": "none"}
    if tts_mod.elevenlabs_enabled():
        # Clone giọng THẬT qua ElevenLabs — trừ API key + credits của provider (người dùng tự chịu).
        try:
            provider_vid = tts_mod.clone_voice(meta["name"], [dest])
            meta["provider"] = "elevenlabs"
            meta["provider_voice_id"] = provider_vid
            meta["voice_value"] = tts_mod.voice_to_value(provider_vid)
        except Exception as e:  # noqa: BLE001
            # Clone lỗi: vẫn lưu file mẫu (dùng được cho chẩn đoán), provider=none
            meta["clone_error"] = str(e)[:300]
    (_voice_meta_dir() / f"{vid}.json").write_text(json.dumps(meta), encoding="utf-8")
    return {"voice_id": vid, "name": meta["name"], "url": f"/media/voices/{safe_name}", "provider": meta["provider"]}


@router.get("/voices-cloned")
def list_cloned_voices(user: User = Depends(current_user)):
    """Danh sách giọng đọc đã upload."""
    voices = []
    vdir = _voice_meta_dir()
    if vdir.exists():
        for meta_path in vdir.glob("*.json"):
            try:
                m = json.loads(meta_path.read_text(encoding="utf-8"))
                if m.get("user_id") == user.id:
                    voices.append({"id": m["id"], "name": m["name"],
                                   "url": f"/media/voices/{m['file']}", "size": m["size"],
                                   "provider": m.get("provider", "none"),
                                   "provider_voice_id": m.get("provider_voice_id"),
                                   "voice_value": m.get("voice_value"),
                                   "clone_error": m.get("clone_error")})
            except Exception as e:
                logger.warning("Bỏ qua voice metadata hỏng %s: %s", meta_path, e)
    return {"voices": voices}


@router.delete("/voices-cloned/{vid}")
def delete_cloned_voice(vid: str, user: User = Depends(current_user)):
    """Xoá giọng đã upload (audio + metadata)."""
    meta_path = _voice_meta_dir() / f"{vid}.json"
    if not meta_path.exists():
        raise HTTPException(404, "Không tìm thấy giọng này")
    try:
        m = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        m = {}
    if m.get("user_id") != user.id and getattr(user, "role", "") != "admin":
        raise HTTPException(404, "Không tìm thấy giọng này")
    audio = settings.voices_dir / m.get("file", "")
    if m.get("provider") == "elevenlabs" and m.get("provider_voice_id"):
        tts_mod.delete_elevenlabs_voice(m["provider_voice_id"])
    meta_path.unlink(missing_ok=True)
    if audio.exists():
        audio.unlink()
    return {"ok": True}


@router.get("/models")
def list_models(step: str = "", db: Session = Depends(get_db)):
    """Models pickable for a pipeline step (llm | image_generate | video_i2v ...), with admin price."""
    from ..modelregistry import all_models, STEPS
    snap = pricing.snapshot(db)

    def _price(mid: str) -> tuple[float, str]:
        key = f"m.{mid}"
        row = snap.get(key)
        cat = pricing.catalog().get(key)
        if row is not None or cat is not None:
            unit = (cat or {}).get("unit", "")
            return (row.price if row else (cat or {}).get("default", 0.0)), unit
=======
# ==================== LOCAL PIPELINE ENDPOINTS ====================

@router.get("/local-pipeline/check")
def local_pipeline_check():
    """Kiểm tra trạng thái pipeline local."""
    from ..localpipeline.config import detect_vram_gb
    vram = detect_vram_gb()
    requirements = {
        "Qwen2-VL-7B-Instruct": {"vram_gb": 8, "disk_gb": 14},
        "FLUX.1-schnell": {"vram_gb": 8, "disk_gb": 36},
        "Wan2.1-T2V-14B": {"vram_gb": 24, "disk_gb": 59},
        "Wan2.1-T2V-1.3B": {"vram_gb": 8, "disk_gb": 10},
    }
    return {
        "vram_gb": vram,
        "has_gpu": vram > 0,
        "requirements": requirements,
        "feasible": {
            "Qwen2-VL-7B-Instruct": vram >= 4,
            "FLUX.1-schnell": vram >= 8,
            "Wan2.1-T2V-14B": vram >= 24,
            "Wan2.1-T2V-1.3B": vram >= 8,
        },
        "warnings": [] if vram >= 8 else ["VRAM < 8GB: chỉ chay duoc model nho voi quantization"],
    }


class LocalVLMIn(BaseModel):
    image_url: str = Field(min_length=1)
    user_instruction: str = ""
    model_id: str = "Qwen/Qwen2-VL-7B-Instruct"


@router.post("/local-vlm")
def local_vlm(body: LocalVLMIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Buoc 1: Chay VLM local de tao prompt tu anh."""
    from ..localpipeline.vlm import run_vlm, VLMError
    from ..localpipeline.config import PipelineConfig

    p = resolve(body.image_url)
    if not p or not p.exists():
        raise HTTPException(422, "Khong tim thay anh dau vao")

    config = PipelineConfig()
    config.vlm_model_id = body.model_id

    try:
        result = run_vlm(str(p), user_instruction=body.user_instruction or None, config=config)
    except VLMError as e:
        raise HTTPException(502, str(e))
    except Exception as e:
        raise HTTPException(500, f"Loi chay VLM: {e}")

    log_activity(db, user.id, "local_vlm", details={
        "model": body.model_id, "image_url": body.image_url,
    })
    return result


class LocalImageGenIn(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)
    seed: int = 42
    model_id: str = "black-forest-labs/FLUX.1-schnell"


@router.post("/local-image-gen")
def local_image_gen(body: LocalImageGenIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Buoc 2: Chay FLUX.1-schnell de tao anh tu prompt."""
    from ..localpipeline.image_gen import run_image_gen, ImageGenError
    from ..localpipeline.config import PipelineConfig

    config = PipelineConfig()
    config.t2i_model_id = body.model_id

    try:
        image_path = run_image_gen(body.prompt, seed=body.seed, config=config)
    except ImageGenError as e:
        raise HTTPException(502, str(e))
    except Exception as e:
        raise HTTPException(500, f"Loi tao anh: {e}")

    log_activity(db, user.id, "local_image_gen", details={
        "model": body.model_id, "prompt": body.prompt[:100],
    })
    return {"image_url": url_for(Path(image_path)), "image_path": image_path}


class LocalPipelineIn(BaseModel):
    image_url: str = ""
    idea: str = ""
    user_instruction: str = ""
    mode: str = "recreate"
    vlm_model_id: str = "Qwen/Qwen2-VL-7B-Instruct"
    t2i_model_id: str = "black-forest-labs/FLUX.1-schnell"
    i2v_model_id: str = "Wan-AI/Wan2.1-T2V-14B"
    duration: int = Field(default=5, ge=1, le=30)


@router.post("/local-pipeline")
def local_pipeline(body: LocalPipelineIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Chay pipeline toan bo: idea -> storyboard -> anh -> video -> thanh pham."""
    from ..localpipeline.pipeline import run_pipeline, PipelineError

    p = resolve(body.image_url) if body.image_url else None
    if body.image_url and (not p or not p.exists()):
        raise HTTPException(422, "Khong tim thay anh dau vao")

    options = {
        "vlm_model_id": body.vlm_model_id,
        "t2i_model_id": body.t2i_model_id,
        "i2v_model_id": body.i2v_model_id,
        "mode": body.mode,
    }

    try:
        result = run_pipeline(
            image_path=str(p) if p else "",
            user_instruction=(body.user_instruction or body.idea) or None,
            mode=body.mode,
            options=options,
        )
        log_activity(db, user.id, "local_pipeline_done", details={
            "job_id": result.job_id, "idea": (body.user_instruction or body.idea or "")[:100],
            "result": result.to_dict(),
        })
        out = result.to_dict()
        if result.image_path and Path(result.image_path).exists():
            out["image_url"] = url_for(Path(result.image_path))
        if result.video_path and Path(result.video_path).exists():
            out["video_url"] = url_for(Path(result.video_path))
        return {
            "status": "done",
            "message": "Pipeline hoan tat.",
            "result": out,
        }
    except Exception as e:
        log_activity(db, user.id, "local_pipeline_failed", details={
            "image_url": body.image_url,
            "mode": body.mode,
            "error": str(e),
        })
        raise HTTPException(502, str(e))


# ==================== REMOTE GPU QUEUE (Kaggle / rented GPU) ====================

class RemotePipelineIn(BaseModel):
    idea: str = Field(min_length=3, max_length=3000)
    duration: int = Field(default=5, ge=1, le=30)
    mode: str = "recreate"
    user_instruction: str = ""


class RemoteJobResult(BaseModel):
    status: str  # done | failed
    result: dict | None = None
    error: str | None = None


# In-memory job store (dev/demo). Worker (Kaggle) polls /next, UI polls /status.
REMOTE_JOBS: dict[str, dict] = {}
REMOTE_JOBS_LOCK = __import__("threading").Lock()


def _new_job_id() -> str:
    return "rpipe_" + secrets.token_hex(8)


@router.post("/remote-pipeline/submit")
def remote_pipeline_submit(body: RemotePipelineIn, user: User = Depends(current_user)):
    """Nguoi dung gui job sang GPU xa (Kaggle). Tra job_id de the doi tien do."""
    job_id = _new_job_id()
    job = {
        "job_id": job_id,
        "user_id": user.id,
        "idea": body.idea,
        "duration": body.duration,
        "mode": body.mode,
        "user_instruction": body.user_instruction,
        "status": "queued",   # queued | processing | done | failed
        "progress": 0,
        "step": "",
        "error": "",
        "result": None,
        "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
    with REMOTE_JOBS_LOCK:
        REMOTE_JOBS[job_id] = job
    return {"job_id": job_id, "status": "queued"}


@router.get("/remote-pipeline/jobs/next")
def remote_pipeline_next():
    """Worker (Kaggle) goi lay lam viec tiep theo trong hang doi."""
    with REMOTE_JOBS_LOCK:
        for job in REMOTE_JOBS.values():
            if job["status"] == "queued":
                job["status"] = "processing"
                job["step"] = "Dang lay nhiem vu"
                return job
    return {"job_id": None}


@router.post("/remote-pipeline/jobs/{job_id}/result")
def remote_pipeline_result(job_id: str, body: RemoteJobResult):
    """Worker (Kaggle) bao ket qua: video duoc upload tro ve tool."""
    with REMOTE_JOBS_LOCK:
        job = REMOTE_JOBS.get(job_id)
        if job is None:
            raise HTTPException(404, "Khong tim thay job")
        job["status"] = body.status
        job["result"] = body.result or {}
        job["error"] = body.error or ""
        if body.status == "done":
            job["progress"] = 100
            job["step"] = "Hoan tat"
        elif body.status == "failed":
            job["step"] = "That bai"
    return {"ok": True}


@router.get("/remote-pipeline/jobs/{job_id}/status")
def remote_pipeline_status(job_id: str, user: User = Depends(current_user)):
    """UI kiem tra tien do job (poll moi 2s)."""
    with REMOTE_JOBS_LOCK:
        job = REMOTE_JOBS.get(job_id)
        if job is None:
            raise HTTPException(404, "Khong tim thay job")
        if job["user_id"] != user.id and getattr(user, "role", "") != "admin":
            raise HTTPException(403, "Khong co quyen xem job nay")
        return {
            "job_id": job["job_id"],
            "status": job["status"],
            "progress": job["progress"],
            "step": job["step"],
            "error": job["error"],
            "result": job["result"],
        }


@router.post("/remote-pipeline/upload")
def remote_pipeline_upload(job_id: str, file: UploadFile = File(...)):
    """Worker (Kaggle) up file video/anh tro ve tool; luu vao outputs, tra URL."""
    job = None
    with REMOTE_JOBS_LOCK:
        job = REMOTE_JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "Khong tim thay job")
    settings.outputs_dir.mkdir(parents=True, exist_ok=True)
    out = settings.outputs_dir / f"remote_{job_id}_{secrets.token_hex(4)}_{Path(file.filename or 'file').name}"
    with out.open("wb") as f:
        f.write(file.file.read())
    return {"url": url_for(out)}


@router.get("/models")
def list_models(step: str = "", db: Session = Depends(get_db)):
    """Models pickable for a pipeline step (llm | image_generate | video_i2v ...), with admin price."""
    from ..modelregistry import ALL_MODELS, STEPS
    snap = pricing.snapshot(db)

    def _price(mid: str) -> tuple[float, str]:
        for key in (f"m.{mid}", pricing.ai_key(mid)):
            row = snap.get(key)
            cat = pricing.catalog().get(key)
            if row is not None or cat is not None:
                unit = (cat or {}).get("unit", "")
                return (row.price if row else (cat or {}).get("default", 0.0)), unit
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
        return 0.0, ""

    def _out(m) -> dict:
        p, unit = _price(m.id)
        enabled = True
<<<<<<< HEAD
        row = snap.get(f"m.{m.id}")
        if row is not None:
            enabled = row.enabled
        label = f"{p:g} credit" if p > 0 else "Free"
        # Public model picker intentionally omits provider URL/engine descriptions.
        return {"id": m.id, "name": m.name, "step": m.step, "group": m.step,
                "price": p, "unit": unit, "enabled": enabled and m.enabled,
                "durations": list(m.supported_durations or []),
                "price_label": f"{label} - {m.name}"}

    steps = [step] if step else ["llm", "image_generate", "video_i2v"]
    out = {"models": [_out(m) for m in all_models() if m.step in steps],
           "steps": {s: STEPS.get(s, s) for s in steps}}
    out["default"] = ""
=======
        for key in (f"m.{m.id}", pricing.ai_key(m.id)):
            row = snap.get(key)
            if row is not None:
                enabled = row.enabled
        label = f"{p:g} credit" if p > 0 else "Free"
        return {"id": m.id, "name": m.name, "step": m.step, "group": m.step,
                "price": p, "unit": unit, "enabled": enabled and m.enabled,
                "price_label": f"{label} - {m.name}"}

    steps = [step] if step else ["llm", "image_generate", "video_i2v"]
    out = {"models": [_out(m) for m in ALL_MODELS if m.step in steps],
           "steps": {s: STEPS.get(s, s) for s in steps}}
    defaults = {"llm": "deepseek-v4-pro-0813", "image_generate": "deepseek-v4-flash-vision",
                "video_i2v": "wan2.1"}
    out["default"] = defaults.get(step, "wan2.1")
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
    return out


@router.get("/check-image-models")
def check_image_models(db: Session = Depends(get_db)):
    """Enabled image-generation models (image_generate step) with price."""
<<<<<<< HEAD
    from ..modelregistry import all_models
    snap = pricing.snapshot(db)
    models = []
    for m in all_models():
=======
    from ..modelregistry import ALL_MODELS
    snap = pricing.snapshot(db)
    models = []
    for m in ALL_MODELS:
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
        if m.step != "image_generate":
            continue
        row = snap.get(f"m.{m.id}") or snap.get(pricing.ai_key(m.id))
        models.append({"id": m.id, "name": m.name,
                       "price": row.price if row else 0.0,
                       "enabled": (row.enabled if row else True) and m.enabled})
    return {"models": models}
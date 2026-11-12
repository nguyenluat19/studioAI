"""Pipeline automation: idea -> storyboard -> images -> video per scene -> final edit.

Mỗi bước dùng MỘT model do người dùng chọn, không tự chuyển model khi lỗi.
Chạy tự động end-to-end, khách hàng chỉ cần nhập yêu cầu và chọn model mỗi giai đoạn.
"""
<<<<<<< HEAD
import logging
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import minimax, pricing, adminmodels, credits, vilao_image
from .db import SessionLocal
from .media import resolve, url_for, user_outputs_dir
from .modelregistry import get_model
from . import videopipeline as vp

logger = logging.getLogger(__name__)

=======
import json
import math
import re
import secrets
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

from . import ai, minimax, pricing
from .config import settings
from .db import SessionLocal
from .media import resolve, url_for
from .modelregistry import clip_count_for_duration, get_model, models_for_step
from .tasks import ai_render_task, broker_up, run_generation
from . import videopipeline as vp

>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_str(s: Any, max_len: int = 500) -> str:
    """Safely convert to string, preserving Unicode characters."""
    try:
        text = str(s)
    except Exception:
        text = repr(s)
    # Encode to UTF-8 then decode with errors='replace' to handle any problematic chars
    try:
        text = text.encode('utf-8', errors='replace').decode('utf-8')
    except Exception:
        pass
    return text[:max_len]


<<<<<<< HEAD
def _pipeline_progress(job: "PipelineJob", status: str, progress: int, step: str) -> None:
    job.update(status=status, progress=progress, step=step)


def _sync_template_progress(job: "PipelineJob") -> None:
    """Persist progress only on the private project owned by this job."""
    saved_id = (job.result or {}).get("saved_template_id")
    if not saved_id:
        return
    try:
        from .models import SharedVideoLibrary
        with SessionLocal() as db:
            template = db.get(SharedVideoLibrary, saved_id)
            if not template or template.creator_id != job.user_id:
                return
            schema = dict(template.template_schema or {})
            schema.update({"status": job.status, "progress": int(job.progress or 0),
                           "step": (job.step or "")[:500], "error": (job.error or "")[:800]})
            template.template_schema = schema
            db.commit()
    except Exception as exc:
        logger.warning("[pipeline] project progress sync failed for %s: %s", job.job_id, exc)


# ---------------------------------------------------------------------------
# Pipeline job store: in-memory (chính) + snapshot DB (pipeline_jobs) để không mất
# tiến trình khi restart; snapshot chỉ đọc để hiển thị, không dùng để resume job.
# ---------------------------------------------------------------------------
def _persist_snapshot(job: "PipelineJob") -> None:
    """Copy trạng thái job vào bảng pipeline_jobs. Lỗi DB không được làm hỏng job."""
    try:
        from .models import PipelineJobState
        with SessionLocal() as s:
            row = s.get(PipelineJobState, job.job_id)
            if row is None:
                row = PipelineJobState(id=job.job_id, user_id=job.user_id, idea=(job.idea or "")[:2000],
                                       mode=job.mode, duration=int(job.duration or 0),
                                       aspect_ratio=job.aspect_ratio or "9:16",
                                       character_image_url=job.character_image_url or "",
                                       voice=job.voice, use_tts=bool(job.use_tts), language=job.language or "vi",
                                       outfit_image_url=job.outfit_image_url or "",
                                       hook_seconds=int(job.hook_seconds or 3), usage_id=job.usage_id,
                                       created_at=job.created_at)
                s.add(row)
            row.status = job.status
            row.progress = int(job.progress or 0)
            row.step = (job.step or "")[:500]
            row.error = job.error or ""
            row.selections = {**(job.selections or {}), "preset": job.preset}
            row.result = job.result or {}
            row.cancelled = bool(job.cancelled)
            row.updated_at = _now()
            s.commit()
    except Exception as e:
        logger.warning("[pipeline] snapshot %s not saved: %s", job.job_id, e)


class PipelineJob:
    def __init__(self, job_id: str, user_id: int, selections: dict,
                 idea: str, duration: int, aspect_ratio: str,
                 character_image_url: str | None, voice: str = "native",
                 use_tts: bool = False, language: str = "vi",
                 mode: str = "standard", outfit_image_url: str | None = None,
                 hook_seconds: int = 3, preset: str = "", usage_id: int | None = None):
=======
# ---------------------------------------------------------------------------
# In-memory pipeline job store (dev/local). Prod có thể chuyển sang DB/Redis.
# ---------------------------------------------------------------------------
class PipelineJob:
    def __init__(self, job_id: str, user_id: int, selections: dict,
                 idea: str, duration: int, aspect_ratio: str,
                 character_image_url: str | None):
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
        self.job_id = job_id
        self.user_id = user_id
        self.selections = selections
        self.idea = idea
        self.duration = duration
        self.aspect_ratio = aspect_ratio
        self.character_image_url = character_image_url
<<<<<<< HEAD
        self.mode = str(mode or "standard")
        self.outfit_image_url = outfit_image_url
        self.preset = str(preset or "")
        self.hook_seconds = max(1, min(int(hook_seconds or 3), 10))
        self.usage_id = usage_id
        self.language = str(language or "vi").strip().lower()
        self.voice = voice
        self.use_tts = use_tts
        self.status = "queued"  # queued | planning | keyframing | rendering | editing | done | failed | cancelled
=======
        self.status = "queued"  # queued | planning | keyframing | rendering | editing | done | failed
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
        self.progress = 0
        self.step = ""
        self.error = ""
        self.result: dict | None = None
<<<<<<< HEAD
        self.cancelled = False
=======
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
        self.created_at = _now()
        self.updated_at = _now()
        self._lock = threading.Lock()

<<<<<<< HEAD
    def cancel(self) -> None:
        with self._lock:
            self.cancelled = True
            if self.status not in ("done", "failed", "cancelled"):
                self.status = "cancelled"
                self.step = "Đã dừng bởi người dùng"
                self.error = "Người dùng đã dừng"
        _persist_snapshot(self)

    def is_cancelled(self) -> bool:
        with self._lock:
            return self.cancelled

=======
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
    def update(self, status: str = None, progress: int = None, step: str = None,
               error: str = None, result: dict = None):
        with self._lock:
            if status is not None:
                self.status = status
            if progress is not None:
                self.progress = progress
            if step is not None:
                self.step = step
            if error is not None:
                self.error = error
            if result is not None:
                self.result = result
            self.updated_at = _now()
<<<<<<< HEAD
        _persist_snapshot(self)
        _sync_template_progress(self)
=======
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "job_id": self.job_id,
                "status": self.status,
                "progress": self.progress,
                "step": self.step,
                "error": self.error,
                "result": self.result,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "selections": self.selections,
<<<<<<< HEAD
                "language": self.language,
                "preset": self.preset,
=======
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
            }


JOBS: dict[str, PipelineJob] = {}
JOBS_LOCK = threading.Lock()


def create_job(user_id: int, selections: dict, idea: str, duration: int,
<<<<<<< HEAD
               aspect_ratio: str, character_image_url: str | None = None,
               voice: str = "native", use_tts: bool = False, language: str = "vi",
               mode: str = "standard", outfit_image_url: str | None = None,
               hook_seconds: int = 3, preset: str = "", usage_id: int | None = None) -> str:
    job_id = "pipe_" + secrets.token_hex(8)
    selections = dict(selections or {})
    selections["from_tool"] = str(selections.get("from_tool") or mode or "pipeline")
    job = PipelineJob(job_id, user_id, selections, idea, duration, aspect_ratio,
                      character_image_url, voice=voice, use_tts=use_tts, language=language,
                      mode=mode, outfit_image_url=outfit_image_url, hook_seconds=hook_seconds,
                      preset=preset, usage_id=usage_id)
    with JOBS_LOCK:
        JOBS[job_id] = job
    _persist_snapshot(job)
=======
               aspect_ratio: str, character_image_url: str | None = None) -> str:
    job_id = "pipe_" + secrets.token_hex(8)
    job = PipelineJob(job_id, user_id, selections, idea, duration, aspect_ratio,
                      character_image_url)
    with JOBS_LOCK:
        JOBS[job_id] = job
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
    return job_id


def get_job(job_id: str) -> PipelineJob | None:
    with JOBS_LOCK:
<<<<<<< HEAD
        job = JOBS.get(job_id)
    if job:
        return job
    # Server restart: job còn trong snapshot DB -> dựng lại để hiển thị trạng thái
    try:
        from .models import PipelineJobState
        with SessionLocal() as s:
            row = s.get(PipelineJobState, job_id)
        if row is None:
            return None
        j = PipelineJob(row.id, row.user_id, row.selections or {}, row.idea or "",
                        row.duration or 0, row.aspect_ratio or "9:16",
                        row.character_image_url or None, voice=row.voice or "native",
                        use_tts=bool(row.use_tts), language=row.language or "vi",
                        mode=row.mode or "standard", outfit_image_url=row.outfit_image_url or None,
                        hook_seconds=row.hook_seconds or 3, preset=(row.selections or {}).get("preset", ""),
                        usage_id=row.usage_id)
        j.status = row.status
        j.progress = row.progress or 0
        j.step = row.step or ""
        j.error = row.error or ""
        j.result = row.result or None
        j.cancelled = bool(row.cancelled)
        j.created_at = row.created_at or _now()
        j.updated_at = row.updated_at or _now()
        return j
    except Exception as e:
        logger.warning("[pipeline] rehydrate %s failed: %s", job_id, e)
        return None


def recover_interrupted_jobs() -> int:
    """Gọi lúc startup: đánh failed cho job còn pending/running lúc server dừng."""
    try:
        from .models import PipelineJobState
        with SessionLocal() as s:
            rows = s.query(PipelineJobState).filter(PipelineJobState.status.notin_(["done", "failed", "cancelled"])).all()
            for r in rows:
                r.status = "failed"
                r.error = ((r.error or "") + " | Server restart — job interrupted").strip(" |")
                r.step = "Job bị gián đoạn do server khởi động lại"
                r.updated_at = _now()
            s.commit()
            return len(rows)
    except Exception as e:
        logger.warning("[pipeline] recover_interrupted_jobs failed: %s", e)
        return 0
=======
        return JOBS.get(job_id)
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa


# ---------------------------------------------------------------------------
# Step runners
# ---------------------------------------------------------------------------

def _run_planning(job: PipelineJob) -> dict:
<<<<<<< HEAD
    """Bước 1: Tạo storyboard bằng model LLM đã chọn (Inkstone hoặc model admin thêm)."""
    job.update(status="planning", progress=10, step="Đang tạo kịch bản...")
    llm_id = job.selections.get("llm", "")
    if not llm_id:
        raise ValueError("Chưa chọn model LLM cho bước tạo kịch bản")
    from . import adminmodels, pricing as _pricing
    with SessionLocal() as db:
        creds = adminmodels.creds(db, llm_id)
        llm_key = f"m.{llm_id}"
        llm_price = _pricing.price(db, llm_key) if llm_key in _pricing.catalog() else 0.0
        vcreds = adminmodels.creds(db, job.selections.get("video_i2v", "") or "") or {}
    # LLM phải viết cảnh theo mốc giây model video chấp nhận (vd Veo 4/6/8) — không thì clip gen ra sai thời lượng/bị từ chối
    clip_steps = None
    try:
        from . import provider as _provider
        clip_steps = _provider.clip_steps_for_model(
            (vcreds.get("base_url") or "").rstrip("/"), vcreds.get("api_key"),
            vcreds.get("model_name") or (job.selections.get("video_i2v") or ""))
    except Exception:
        clip_steps = None
    try:
        from .presets import get_preset
        plan = vp.plan_storyboard(
            topic=job.idea,
            model_id=llm_id,
            duration_seconds=job.duration,
            aspect_ratio=job.aspect_ratio,
            character_image_url=job.character_image_url,
            creds=creds,
            language=job.language,
            mode=job.mode,
            outfit_image_url=job.outfit_image_url,
            hook_seconds=job.hook_seconds,
            clip_steps=clip_steps,
            preset=get_preset(getattr(job, "preset", "")),
        )
    except Exception as e:
        raise ValueError(f"Không tạo được storyboard: {_safe_str(e)}")
    # Trừ credit LLM — mỗi lần gọi LLM tốn tiền admin; người dùng trả 1 lần / kịch bản.
    # Chỉ trừ khi storyboard thành công (lỗi LLM → admin chịu, không thu phí user).
    if llm_price > 0:
        with SessionLocal() as db:
            if not credits.charge(db, job.user_id, llm_price, kind="spend", reason="LLM tạo kịch bản", ref_type="pipeline", ref_id=job.job_id):
                db.rollback()
                raise ValueError("Không đủ credit để tạo kịch bản (LLM)")
            db.commit()
    return plan


def _run_single_clip_mode(job: PipelineJob) -> dict:
    """Mode Text→Video / Ảnh→Video: không storyboard, không keyframe — 1 clip duy nhất.

    LLM mở rộng ý tưởng thành prompt cinematic → Veo (t2v / i2v) → 1 clip;
    trừ credit LLM (nếu thành công) + 1 video request.
    """
    mode = job.mode
    video_id = job.selections.get("video_i2v", "") or ""
    llm_id = job.selections.get("llm", "") or ""
    if not video_id:
        raise ValueError("Chưa chọn model video")
    if mode == "image_to_video":
        img = resolve(job.character_image_url) if job.character_image_url else None
        if img is None:
            raise ValueError("Chế độ Ảnh → Video cần ảnh nhân vật (upload 1 ảnh trước khi bắt đầu)")

    # LLM mở rộng prompt — lỗi thì dùng thẳng ý tưởng gốc (không fail job)
    model = get_model(video_id)
    if not model or model.step != "video_i2v":
        raise ValueError(f"Model {video_id} không phải model video")
    from . import provider as _provider
    with SessionLocal() as db:
        creds = adminmodels.creds(db, llm_id) or {}
        llm_key = f"m.{llm_id}"
        llm_price = pricing.price(db, llm_key) if llm_key in pricing.catalog() else 0.0
        vcreds = adminmodels.creds(db, video_id) or {}
    duration = job.duration
    try:
        vsteps = _provider.clip_steps_for_model(
            (vcreds.get("base_url") or "").rstrip("/"), vcreds.get("api_key"),
            vcreds.get("model_name") or video_id)
    except Exception:
        vsteps = None
    if vsteps:
        duration = min(vsteps, key=lambda s: (abs(s - duration), s))
    else:
        duration = max(2, min(duration, 8))
    try:
        expanded = vp.expand_single_prompt(job.idea, llm_id, creds=creds,
                                           language=job.language)
    except Exception:
        expanded = job.idea
    if llm_price > 0:
        with SessionLocal() as db:
            if not credits.charge(db, job.user_id, llm_price, kind="spend", reason="LLM mở rộng prompt", ref_type="pipeline", ref_id=job.job_id):
                db.rollback()
                raise ValueError("Không đủ credit để mở rộng prompt (LLM)")
            db.commit()

    model_price_key = pricing.video_pricing_key(video_id)
    with SessionLocal() as db:
        model_price = pricing.price(db, model_price_key) if model_price_key in pricing.catalog() else 0.0
    kf = {
        "stt": 1, "thời_lượng_giây": duration,
        "loại_shot": "WS", "góc_máy": "mặc định", "chuyển_động_camera": "tĩnh",
        "hành_động": job.idea, "biểu_cảm": "bình thường", "thoại": "", "nhân_vật_nói": "",
        "giai_đoạn": "", "identity_lock": "",
        "image_prompt": "", "video_prompt": expanded,
        "tỉ_lệ_khung_hình": job.aspect_ratio,
        "image_url": (job.character_image_url or "") if mode == "image_to_video" else "",
        "audio_url": "", "video_url": "", "status": "queued",
    }
    job.update(status="rendering", progress=50, step=f"Đang tạo video ({video_id})...")
    with SessionLocal() as db:
        _gen_scene_video(job, kf, db, ci=0, total_scenes=1,
                         video_model_id=video_id, model_price=model_price, per_scene_sec=duration)
    if not kf.get("video_url"):
        raise ValueError(kf.get("error") or "Không tạo được clip video")
    saved_template_id = (job.result or {}).get("saved_template_id")
    job.result = {
        "plan": {"mode": mode, "model_used": video_id, "idea": job.idea,
                 "expanded_prompt": expanded, "single_clip": True,
                 "tổng_thời_lượng": duration, "các_cảnh": [kf]},
        "keyframes": [kf],
        "clip_count": 1,
    }
    if saved_template_id:
        job.result["saved_template_id"] = saved_template_id
    with SessionLocal() as db:
        try:
            save_pipeline_template(job, db)
        except Exception as e:  # không để lỗi lưu làm hỏng pipeline đã xong
            import logging
            logging.warning("[pipeline] auto-save single-clip failed: %s", _safe_str(e))
    job.update(status="done", progress=100,
               step="Hoàn tất! Đã tạo 1 clip video (chế độ " +
                    ("Ảnh → Video" if mode == "image_to_video" else "Text → Video") + ")",
               result=job.result)
    _sync_template_progress(job)
    return job.result


def _run_keyframing(job: PipelineJob, plan: dict, db) -> list[dict]:
    job.update(status="keyframing", progress=35, step="Đang chuẩn bị ảnh từng cảnh...")
    img_id = job.selections.get("image_generate") or ""
    creds = adminmodels.creds(db, img_id) if img_id else None
    if not creds:
        raise ValueError("Chưa cấu hình model ảnh để giữ nhân vật đồng nhất")
    reference_path = resolve(job.character_image_url) if job.character_image_url else None
    if job.character_image_url and reference_path is None:
        raise ValueError("Không tìm thấy ảnh nhân vật tham chiếu đã upload")
    outfit_path = None
    if getattr(job, "mode", "standard") == "review_outfit":
        if not job.outfit_image_url:
            raise ValueError("Chế độ review sản phẩm cần ảnh bộ đồ/sản phẩm để review")
        outfit_path = resolve(job.outfit_image_url)
        if outfit_path is None:
            raise ValueError("Không tìm thấy ảnh bộ đồ/sản phẩm đã upload")
        if reference_path is None:
            raise ValueError("Chế độ review sản phẩm cần ảnh nhân vật tham chiếu")
    price_key = f"m.{img_id}"
    # Preserve the original quantity semantics; refund the whole charge block on failure.
    image_price = pricing.price(db, price_key) if price_key in pricing.catalog() else 0.0
    image_cost = round(len(plan["các_cảnh"]) * image_price, 2)
    if image_cost > 0:
        if not credits.charge(db, job.user_id, image_cost, kind="spend", reason=f"Gen ảnh (x{len(plan['các_cảnh'])} cảnh)", ref_type="pipeline", ref_id=job.job_id):
            db.rollback()
            raise ValueError(f"Không đủ credit để tạo ảnh (cần {image_cost} credit)")
        db.commit()
    try:
        return _generate_keyframes(job, plan, creds, reference_path, outfit_path)
    except Exception:
        if image_cost > 0:
            db.rollback()
            credits.add_credits(db, job.user_id, image_cost, kind="refund", reason="Hoàn credit gen ảnh (lỗi)", ref_type="pipeline", ref_id=job.job_id)
            db.commit()
        raise


def _composite_reference(paths: list[Path], dest: Path) -> Path:
    """Ghép các ảnh tham chiếu cạnh nhau (khi gateway không nhận nhiều ảnh)."""
    import subprocess
    import tempfile
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="ref_composite_"))
    try:
        norm = []
        for i, p in enumerate(paths):
            n = tmp / f"n{i}{p.suffix or '.png'}"
            res = subprocess.run(
                ["ffmpeg", "-y", "-i", str(p),
                 "-vf", "scale=768:1024:force_original_aspect_ratio=decrease,"
                        "pad=768:1024:(ow-iw)/2:(oh-ih)/2,setsar=1",
                 str(n)], capture_output=True, text=True, timeout=120)
            if res.returncode != 0:
                raise RuntimeError(f"FFmpeg chuẩn hóa ảnh tham chiếu lỗi: {res.stderr[-300:]}")
            norm.append(n)
        fc = "".join(f"[{i}:v]" for i in range(len(norm))) + f"hstack=inputs={len(norm)}"
        res = subprocess.run(
            ["ffmpeg", "-y", *sum([["-i", str(n)] for n in norm], []),
             "-filter_complex", fc, "-frames:v", "1", str(dest)],
            capture_output=True, text=True, timeout=120)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg ghép ảnh tham chiếu lỗi: {res.stderr[-300:]}")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    return dest


_COMPOSITE_NOTE = (
    "The reference image is a side-by-side composite: the LEFT panel shows the person, "
    "the RIGHT panel shows the garment/product to put on them. Keep the person's face and "
    "identity from the left panel and dress them in the exact garment from the right panel. "
    "Output a single normal photo, never a split image."
)


def _generate_keyframes(job: PipelineJob, plan: dict, creds: dict, reference_path,
                        outfit_path=None) -> list[dict]:
    scenes = plan["các_cảnh"]
    character_bible = plan.get("character_bible", {})
    style_bible = plan.get("style_bible", {})
    characters = plan.get("nhân_vật", []) or []
    outfit_bible = plan.get("outfit_bible", {}) or {}
    review_mode = getattr(job, "mode", "standard") == "review_outfit"
    identity_lock = vp.identity_lock(character_bible, characters,
                                     allow_outfit_change=review_mode)
    keyframes = []
    composite: Path | None = None
    user_outputs_dir(job.user_id)
    for stt, scene in enumerate(scenes, start=1):
        if job.is_cancelled():
            raise ValueError("Đã dừng bước tạo ảnh bởi người dùng")
        phase = (scene.get("giai_đoạn") or "") if review_mode else ""
        # Every visible-person frame is conditioned on both user references: character identity + exact reviewed item.
        # The final product-only insert uses only the product image to avoid hybrid/invented imagery.
        refs: list[Path] = []
        if review_mode:
            if phase == "chi_tiet_san_pham":
                if outfit_path:
                    refs = [outfit_path]
            else:
                if reference_path:
                    refs.append(reference_path)
                if outfit_path:
                    refs.append(outfit_path)
        elif reference_path:
            refs = [reference_path]
        prompt = vp.gen_keyframe_prompt(
            scene, character_bible, style_bible,
            url_for(reference_path) if reference_path else None, characters=characters,
            location_bible=plan.get("location_bible", {}),
            phase=phase, outfit_bible=outfit_bible,
            has_outfit_reference=bool(outfit_path),
        )
        kf = {
            "stt": stt,
=======
    """Bước 1: Tạo storyboard bằng VLM local (Qwen2-VL-7B-Instruct)."""
    job.update(status="planning", progress=10, step="Đang tạo kịch bản...")
    from .localpipeline.vlm import run_vlm, VLMError
    from .localpipeline.config import PipelineConfig
    import os
    config = PipelineConfig()
    config.vlm_model_id = job.selections.get("vlm_model_id", "Qwen/Qwen2-VL-7B-Instruct")
    try:
        result = run_vlm(str(job.character_image_url) if job.character_image_url else None,
                        user_instruction=job.idea, config=config)
        return result
    except VLMError as e:
        raise ValueError(f"VLM lỗi: {e}")
    except Exception as e:
        raise ValueError(f"Lỗi chạy VLM: {e}")


def _run_keyframing(job: PipelineJob, plan: dict) -> list[dict]:
    """Bước 2: Tạo prompt ảnh cho từng cảnh (keyframe prompts).

    Lưu ý: Model ảnh (image_generate) hiện chỉ dùng để sinh prompt chi tiết.
    Việc gọi API sinh ảnh thực sự phụ thuộc nhà cung cấp bên ngoài (Qwen-Image,
    FLUX, v.v.) chưa kết nối vào hệ thống này. Nếu cần, admin có thể kết nối
    adapter tương ứng.
    """
    job.update(status="keyframing", progress=35, step="Đang chuẩn bị ảnh từng cảnh...")
    scenes = plan["các_cảnh"]
    character_bible = plan.get("character_bible", {})
    style_bible = plan.get("style_bible", {})

    keyframes = []
    for scene in scenes:
        prompt = vp.gen_keyframe_prompt(
            scene, character_bible, style_bible,
            job.character_image_url,
        )
        keyframes.append({
            "stt": scene["stt"],
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
            "thời_lượng_giây": scene["thời_lượng_giây"],
            "loại_shot": scene["loại_shot"],
            "góc_máy": scene["góc_máy"],
            "hành_động": scene["hành_động"],
            "biểu_cảm": scene["biểu_cảm"],
            "thoại": scene["thoại"],
<<<<<<< HEAD
            "nhân_vật_nói": scene.get("nhân_vật_nói", ""),
            "giai_đoạn": phase,
            "identity_lock": identity_lock,
            "image_prompt": prompt,
            "source_image_prompt": prompt,
            "video_prompt": str(scene.get("video_prompt", "")),
            "product_reference_locked": bool(review_mode and phase),
            "product_reference_url": url_for(outfit_path) if review_mode and outfit_path else "",
            "character_reference_url": url_for(reference_path) if review_mode and reference_path else "",
            "tỉ_lệ_khung_hình": scene["tỉ_lệ_khung_hình"],
            "image_url": "",
            "audio_url": "",
            "video_url": "",
            "status": "pending",
        }
        dest = user_outputs_dir(job.user_id) / f"keyframe_{job.job_id}_{stt}.png"
        try:
            try:
                vilao_image.gen_image(
                    prompt, dest,
                    base_url=creds["base_url"], api_key=creds["api_key"],
                    model=creds["model_name"] or job.selections["image_generate"],
                    ratio=scene.get("tỉ_lệ_khung_hình") or job.aspect_ratio,
                    reference=refs[0] if len(refs) == 1 else None,
                    references=refs if len(refs) > 1 else None,
                )
            except vilao_image.MultiReferenceUnsupported:
                # Gateway không nhận nhiều ảnh -> ghép nhân vật + bộ đồ thành 1 ảnh.
                if len(refs) > 1 and reference_path and outfit_path:
                    if composite is None:
                        composite = _composite_reference(
                            [reference_path, outfit_path],
                            user_outputs_dir(job.user_id) / f"ref_composite_{job.job_id}.png")
                    vilao_image.gen_image(
                        f"{prompt} {_COMPOSITE_NOTE}", dest,
                        base_url=creds["base_url"], api_key=creds["api_key"],
                        model=creds["model_name"] or job.selections["image_generate"],
                        ratio=scene.get("tỉ_lệ_khung_hình") or job.aspect_ratio,
                        reference=composite,
                    )
                else:
                    raise
        except vilao_image.ReferenceImageUnsupported as e:
            raise ValueError(
                "Model ảnh không hỗ trợ /images/edits để giữ nhân vật đồng nhất. "
                "Đã dừng pipeline; credit bước ảnh được hoàn lại."
            ) from e
        except Exception as e:
            detail = _safe_str(e)
            if "INSUFFICIENT_BALANCE" in detail:
                raise ValueError(
                    "Tài khoản vilao.ai không đủ số dư để gen ảnh. Vui lòng nạp tiền rồi chạy lại pipeline."
                ) from e
            raise ValueError(f"Không tạo được ảnh nhân vật cảnh {stt}: {detail}") from e
        kf["image_url"] = url_for(dest)
        if reference_path is None:
            reference_path = dest
        kf["character_reference_url"] = url_for(reference_path)
        if outfit_path is not None:
            kf["outfit_reference_url"] = url_for(outfit_path)
        # TTS: tạo audio cho lời thoại từng cảnh (chỉ khi bật)
        kf["audio_url"] = ""
        dialogue = (scene.get("thoại") or "").strip()
        if dialogue and job.use_tts and getattr(job, "voice", "") != "native":
            audio_dest = user_outputs_dir(job.user_id) / f"audio_{job.job_id}_{stt}.mp3"
            try:
                from . import tts as tts_mod
                import time
                # Chọn giọng: nếu user để "auto" -> theo giới tính nhân vật đang nói.
                gender = tts_mod.gender_of_character(
                    (scene.get("nhân_vật_nói") or "").strip(), characters)
                voice = tts_mod.resolve_voice(job.voice, gender, language=job.language)
                emotion = scene.get("biểu_cảm") or ""
                rate, pitch, volume = tts_mod.emotion_params(emotion)
                time.sleep(1)  # tránh rate limit edge-tts
                tts_mod.gen_tts(dialogue, audio_dest, voice=voice, rate=rate, pitch=pitch, volume=volume)
                kf["audio_url"] = url_for(audio_dest)
                kf["audio_voice"] = voice
                kf["audio_emotion"] = emotion or "bình thường"
            except Exception as e:  # noqa: BLE001
                kf["audio_error"] = _safe_str(e)
        keyframes.append(kf)
    if job.is_cancelled():
        raise ValueError("Đã dừng bước tạo ảnh bởi người dùng")
    return keyframes


def _mux_tts_voiceover(video_path: Path, audio_path: Path, duration: int) -> None:
    """Replace generated audio with the requested TTS voiceover, keeping video frames unchanged."""
    import subprocess
    if not video_path.is_file() or not audio_path.is_file():
        raise ValueError("Không tìm thấy clip hoặc audio TTS để ghép")
    tmp = video_path.with_name(video_path.stem + ".voiceover.tmp.mp4")
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-nostdin", "-loglevel", "error", "-i", str(video_path), "-i", str(audio_path),
             "-map", "0:v:0", "-map", "1:a:0", "-t", str(max(1, int(duration))),
             "-c:v", "copy", "-c:a", "aac", "-ar", "44100", "-ac", "2", "-shortest", str(tmp)],
            capture_output=True, text=True, timeout=180)
        if result.returncode or not tmp.is_file() or tmp.stat().st_size == 0:
            raise RuntimeError((result.stderr or "ffmpeg không tạo được file voiceover")[-500:])
        tmp.replace(video_path)
    finally:
        tmp.unlink(missing_ok=True)


def _scene_video_prompt(job, kf) -> str:
    """Use the exact finalized image-generation prompt for I2V when available."""
    # source_image_prompt is captured before image creation and passed verbatim to
    # the video provider. Do not regenerate/translate/expand it between modalities.
    scene_prompt = (kf.get("source_image_prompt") or kf.get("image_prompt") or
                    kf.get("video_prompt") or job.idea)
    phase = kf.get("giai_đoạn", "") or ""
    is_product = phase == "chi_tiet_san_pham"
    if is_product:
        # Product-only insert: reference-driven, no human/audio generation; CTA is mixed as voiceover separately.
        scene_prompt = (
            "Product-only macro close-up of the exact item shown in the provided product reference image. "
            "No person, mannequin, hands, alternate product, added branding, labels or invented features. "
            "Preserve the exact visible color, silhouette, neckline, straps/sleeves, seams, pattern and material appearance. "
            "No speech generated; CTA, if any, is external voiceover only. "
            "Slow stable camera movement over the item. " + scene_prompt
        )
    else:
        lock = kf.get("identity_lock", "")
        if lock:
            scene_prompt = f"{lock}. {scene_prompt}"
        if phase == "bien_hinh":
            scene_prompt = (
                f"{scene_prompt} REFERENCE-LOCKED PRODUCT REVEAL: use the exact garment already visible in this scene's keyframe. "
                "Do not morph, replace, recolor, add/remove details or transform it during the video. "
                "Use a simple camera move or light reveal only; preserve the same person and garment throughout."
            )
        elif phase == "review":
            scene_prompt = (
                f"{scene_prompt} PRODUCT CONTINUITY LOCK: use the exact user-supplied product as shown in the keyframe, "
                "with identical visible design, color, silhouette and details for every frame. No substitution, redesign or spontaneous wardrobe change. "
                "Keep the same character identity as the character reference."
            )
        elif phase == "hook":
            scene_prompt = (
                f"{scene_prompt} PRODUCT + IDENTITY LOCK: start already wearing the exact user product from the keyframe. "
                "Preserve exact face, hair, skin, body and garment design. No original/different outfit and no wardrobe change."
            )
        if kf.get("product_reference_locked"):
            scene_prompt += " The exact product image uploaded by the user is authoritative. Keep that exact garment visible in every character frame; never substitute another garment, even if generated text conflicts."
        dialogue = (kf.get("thoại") or "").strip()
        emotion = (kf.get("biểu_cảm") or kf.get("audio_emotion") or "").strip()
        try:
            from . import tts as _tts
            emotion_cue = _tts.emotion_cue_en(emotion)
        except Exception:
            emotion_cue = "calm, natural"
        tts_mode = job.use_tts and getattr(job, "voice", "") != "native"
        if tts_mode:
            # External TTS replaces generated audio; ask for silent phoneme-timed mouth articulation, not closed lips.
            safe_dialogue = dialogue.replace('"', "'")
            lang_instr = "English" if job.language == "en" else "Vietnamese"
            scene_prompt = (f"{scene_prompt} SILENT LIP-SYNC PERFORMANCE in {lang_instr}: visibly articulate this exact line "
                            f"with mouth movements timed to its syllables: '{safe_dialogue}'. "
                            "Generate absolutely no speech audio, music or vocalization; the matching external voiceover is muxed afterward. "
                            f"Act with this emotion: {emotion_cue}.")
        elif dialogue:
            # Model video (Veo) tự sinh audio — phải nói ĐÚNG câu thoại trong kịch bản,
            # nếu không nó sẽ bịa lời khác (vd nói salad trong khi cảnh là bún chả).
            lang_instr = ("The dialogue must be spoken in English."
                          if job.language == "en" else
                          "Lời thoại phải nói bằng tiếng Việt.")
            safe_dialogue = dialogue.replace('"', "'")
            scene_prompt = (f"DIALOGUE LANGUAGE: {lang_instr} {scene_prompt} "
                            f"The character says this exact line: \"{safe_dialogue}\" "
                            f"(lip-sync exactly to this line, no other words; "
                            f"deliver the line with this emotion: {emotion_cue}).")
        scene_prompt += " No dialogue: the character does not speak, mouth stays closed, no speech audio."

    # Khách tự edit video, tuyệt đối không có subtitles/captions/on-screen text trong frame.
    return (f"{scene_prompt} No subtitles, captions, on-screen text, watermarks or graphics in frame. "
            "The user adds subtitles later in their editor.")


def _gen_scene_video(job, kf, db, *, ci, total_scenes, video_model_id, model_price,
                     per_scene_sec, scene_no=None) -> None:
    """Gen 1 clip video cho cảnh kf; cập nhật kf tại chỗ. Trừ credit khi thành công.

    Dùng cho cả pipeline lần đầu và retry cảnh lỗi.
    """
    scene_no = scene_no if scene_no is not None else kf.get("stt", ci + 1)
    scene_dur = max(1, int(kf.get("thời_lượng_giây", per_scene_sec) or per_scene_sec))
    scene_progress = 60 + int(((ci + 0.5) / max(total_scenes, 1)) * 25)
    job.update(progress=scene_progress, step=f"Đang render cảnh {scene_no}/{total_scenes} ({scene_dur}s)...")
    scene_prompt = _scene_video_prompt(job, kf)

    phase = kf.get("giai_đoạn", "") or ""
    is_product = phase == "chi_tiet_san_pham"
    review_mode = getattr(job, "mode", "") == "review_outfit"
    if is_product:
        scene_prompt += " No speech generated in this product-only scene; narration/CTA is external voiceover only."
        if review_mode and kf.get("product_reference_locked"):
            scene_prompt += " PRODUCT REFERENCE OVERRIDES ALL TEXT: maintain the exact garment/product from the uploaded product image unchanged in every frame. Keep the same identity from the character image."
        elif kf.get("product_reference_locked"):
            scene_prompt += " Exact product continuity is mandatory: same user-supplied item and design for every frame."
    elif review_mode and kf.get("product_reference_locked"):
        scene_prompt += " PRODUCT REFERENCE OVERRIDES ALL TEXT: preserve the exact uploaded garment/product, not a generic equivalent, and the same character identity in every frame."
    review_mode = getattr(job, "mode", "") == "review_outfit"
    if is_product:
        fallback_frame_url = getattr(job, "outfit_image_url", None)
    else:
        fallback_frame_url = job.character_image_url
    first_frame_url = kf.get("image_url") or fallback_frame_url
    if not first_frame_url:
        first_frame_url = kf.get("character_reference_url")
    first_frame = resolve(first_frame_url) if first_frame_url else None
    review_mode = getattr(job, "mode", "") == "review_outfit"
    if first_frame is None:
        raise ValueError(
            f"Không tìm thấy ảnh keyframe tham chiếu cho cảnh {scene_no}; "
            "dừng trước khi gọi model video để không tạo video không bám ảnh. "
            "Hãy tạo lại ảnh cảnh rồi thử lại."
        )
    dest = user_outputs_dir(job.user_id) / f"pipe_{job.job_id}_scene_{ci}.mp4"
    try:
        if video_model_id.startswith("minimax-h3"):
            resolution = "2K" if video_model_id.endswith("2k") else "768P"
            ratio = job.aspect_ratio if job.aspect_ratio in minimax.RATIOS else "9:16"
            minimax.generate(
                prompt=scene_prompt,
                dest=dest,
                first_frame=first_frame,
                duration=scene_dur,
                ratio=ratio,
                resolution=resolution,
            )
        else:
            from . import adminmodels
            creds = adminmodels.creds(db, video_model_id)   # key nằm trong .env (MODEL_<ID>_API_KEY)
            if creds and creds.get("base_url"):
                ratio = job.aspect_ratio if job.aspect_ratio in minimax.RATIOS else "9:16"
                minimax.generate(
                    prompt=scene_prompt,
                    dest=dest,
                    first_frame=first_frame,
                    duration=scene_dur,
                    ratio=ratio,
                    resolution="768P",
                    base_url=creds["base_url"],
                    api_key=creds["api_key"],
                    model=creds["model_name"] or video_model_id,
                )
            else:
                raise ValueError(f"Model {video_model_id} chưa được kết nối vào pipeline tự động")

        if dest.exists() and dest.stat().st_size > 0:
            if getattr(job, "use_tts", False) and getattr(job, "voice", "native") != "native":
                audio_path = resolve(kf.get("audio_url"), job.user_id) if kf.get("audio_url") else None
                if audio_path is None:
                    if kf.get("thoại"):
                        raise ValueError("Đã bật TTS nhưng không tạo được audio cho cảnh này; dừng để tránh trả clip sai giọng/âm thanh.")
                else:
                    _mux_tts_voiceover(dest, audio_path, scene_dur)
            vurl = url_for(dest)
            scene_cost = round(model_price, 2)   # 1 clip = 1 request (vilao tính theo request) — không nhân theo giây
        if scene_cost > 0:
            from app import credits
            if not credits.charge(db, job.user_id, scene_cost, kind="spend", reason=f"Gen video cảnh {scene_no}/{total_scenes}", ref_type="pipeline", ref_id=job.job_id):
                dest.unlink(missing_ok=True)
                raise ValueError(f"Không đủ credit để render tiếp (cần {scene_cost} credit cho cảnh {scene_no})")
            db.commit()
        kf["video_url"] = vurl
        kf["status"] = "done"
        try:
            save_pipeline_template(job, db)
        except Exception:
            import logging
            logging.warning("[pipeline] save after scene failed")
    except Exception as e:  # noqa: BLE001
        err = _safe_str(e)
        no_balance = "INSUFFICIENT_BALANCE" in err
        if no_balance:
            err = "Tài khoản vilao.ai không đủ số dư để gen video. Vui lòng nạp tiền tại vilao.ai rồi chạy lại."
        kf["video_url"] = ""
        kf["error"] = err
        kf["status"] = "failed"
        if no_balance:
            raise ValueError(err) from e


def _run_rendering(job: PipelineJob, keyframes: list[dict], db) -> list[dict]:
    """Bước 3: Gen video. Gom các cảnh liền kề vào cùng 1 request khi tổng thời lượng
    không vượt max_clip_seconds của model — giảm số request lên gateway (tiết kiệm tiền)."""
    job.update(status="rendering", progress=60, step="Đang tạo video...")
=======
            "image_prompt": prompt,
            "tỉ_lệ_khung_hình": scene["tỉ_lệ_khung_hình"],
            "video_url": "",
            "status": "pending",
        })
    return keyframes


def _run_rendering(job: PipelineJob, keyframes: list[dict], db) -> list[dict]:
    """Bước 3: Gen video từng cảnh bằng model video đã chọn (MiniMax-H3)."""
    job.update(status="rendering", progress=60, step="Đang tạo video từng cảnh...")
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
    video_model_id = job.selections["video_i2v"]
    model = get_model(video_model_id)
    if not model or model.step not in ("video_i2v", "video_t2v"):
        raise ValueError(f"Model {video_model_id} không phải model video")

    # Check pricing for this model
<<<<<<< HEAD
    model_price_key = pricing.video_pricing_key(video_model_id)
=======
    model_price_key = f"m.{video_model_id}"
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
    model_price = pricing.price(db, model_price_key) if model_price_key in pricing.catalog() else 0.0

    total_seconds = job.duration
    per_scene_sec = max(1, total_seconds // max(len(keyframes), 1))

<<<<<<< HEAD
    # KHÔNG trừ credit trước khi gen — chỉ trừ từng chunk gen thành công (xem vòng lặp bên dưới).
    # Trước đây trừ trước toàn bộ: nếu gateway từ chối (vd thiếu số dư) thì mất credit oan.
    job.update(progress=65, step=f"Tạo {len(keyframes)} video riêng cho từng cảnh...")

    for ci, kf in enumerate(keyframes):
        if job.is_cancelled():
            return keyframes
        scene_no = kf.get("stt", ci + 1)
        _gen_scene_video(job, kf, db, ci=ci, total_scenes=len(keyframes),
                         video_model_id=video_model_id,
                         model_price=model_price, per_scene_sec=per_scene_sec,
                         scene_no=scene_no)

    return keyframes


def retry_failed_scenes(job_id: str) -> dict | None:
    """Gen lại đúng các cảnh chưa có clip (sau khi pipeline đã kết thúc).

    Trừ credit chỉ cho cảnh thành công. Cập nhật dự án đã lưu trong "Template của tôi"
    (nếu có) để cảnh mới xuất hiện ở đó. Trả về thống kê."""
    job = get_job(job_id)
    if job is None:
        return None
    result = job.result or {}
    keyframes = result.get("keyframes") or []
    failed = [kf for kf in keyframes if not kf.get("video_url")]
    if not failed:
        ok = sum(1 for k in keyframes if k.get("video_url"))
        return {"retried": 0, "succeeded": ok, "total": len(keyframes)}
    video_model_id = job.selections["video_i2v"]
    model = get_model(video_model_id)
    if not model or model.step not in ("video_i2v", "video_t2v"):
        raise ValueError(f"Model {video_model_id} không phải model video")
    model_price_key = pricing.video_pricing_key(video_model_id)
    with SessionLocal() as db:
        model_price = pricing.price(db, model_price_key) if model_price_key in pricing.catalog() else 0.0
        job.update(status="rendering", progress=60, step=f"Đang tạo lại {len(failed)} cảnh lỗi...")
        per_scene_sec = max(1, int(job.duration) // max(len(keyframes), 1))
        for ci, kf in enumerate(keyframes):
            if kf.get("video_url") or job.is_cancelled():
                continue
            _gen_scene_video(job, kf, db, ci=ci, total_scenes=len(keyframes),
                             video_model_id=video_model_id,
                             model_price=model_price, per_scene_sec=per_scene_sec)
        result = job.result or {}
        result["keyframes"] = keyframes
        saved_id = result.get("saved_template_id")
        if saved_id:
            from .models import SharedVideoLibrary
            t = db.get(SharedVideoLibrary, saved_id)
            if t:
                sc = dict(t.template_schema or {})
                sc["keyframes"] = keyframes
                t.template_schema = sc
                tf = next((k.get("image_url") for k in keyframes if k.get("image_url")), t.thumbnail_url)
                if tf:
                    t.thumbnail_url = tf
                db.commit()
        ok = sum(1 for k in keyframes if k.get("video_url"))
        total = len(keyframes)
        if job.is_cancelled():
            job.update(status="cancelled", step="Đã dừng bởi người dùng", result=result)
        else:
            job.update(status="done", step=f"Hoàn tất tạo lại — {ok}/{total} cảnh có clip",
                       progress=100, result=result)
        return {"retried": len(failed), "succeeded": ok, "total": total}


# ---------------------------------------------------------------------------
# Auto-save thành phẩm vào "Template của tôi" (private)
# ---------------------------------------------------------------------------

def _schema_source_feature(job) -> str:
    sel = job.selections or {}
    return str(sel.get("from_tool") or getattr(job, "mode", "standard") or "pipeline")


def _fill_template_schema(t, job, result):
    keyframes = result.get("keyframes") or []
    first_frame = next((kf.get("image_url") for kf in keyframes if kf.get("image_url")), "")
    if job.cancelled:
        stage = "cancelled"
    elif job.status == "failed":
        stage = "failed"
    elif job.status == "done":
        stage = "done"
    elif job.status in ("queued", "planning", "keyframing", "rendering", "editing"):
        stage = job.status
    else:
        stage = ("keyframed" if keyframes and result.get("clip_count") is None
                 else ("done" if result.get("clip_count") is not None else "plan"))
    t.template_schema = {"pipeline": True, "job_id": job.job_id,
                         "clip_only": True,
                         "images_only": bool(result.get("images_only")),
                         "idea": job.idea, "duration": job.duration,
                         "aspect_ratio": job.aspect_ratio, "language": job.language,
                         "voice": job.voice, "use_tts": job.use_tts,
                         "mode": getattr(job, "mode", "standard"),
                         "source_feature": _schema_source_feature(job),
                         "outfit_image_url": getattr(job, "outfit_image_url", "") or "",
                         "hook_seconds": getattr(job, "hook_seconds", 3),
                         "character_image_url": job.character_image_url or "",
                         "selections": job.selections,
                         "plan": result.get("plan", {}) or {},
                         "keyframes": keyframes,
                         "stage": stage,
                         "progress": int(getattr(job, "progress", 0) or 0),
                         "status": getattr(job, "status", "queued"),
                         "step": getattr(job, "step", "") or "",
                         "error": getattr(job, "error", "") or ""}
    if first_frame:
        t.thumbnail_url = first_frame


_TEMPLATE_LOCKS: dict[str, threading.Lock] = {}
_TEMPLATE_LOCKS_GUARD = threading.Lock()


def save_pipeline_template(job: PipelineJob, db) -> dict | None:
    """Serialize stage-triggered template writes so one job keeps exactly one project."""
    lock = threading.Lock()
    with _TEMPLATE_LOCKS_GUARD:
        existing = _TEMPLATE_LOCKS.setdefault(job.job_id, lock)
    with existing:
        return _save_pipeline_template(job, db)


def _save_pipeline_template(job: PipelineJob, db) -> dict | None:
    """Upsert the single private project entry associated with this pipeline job."""
    result = job.result or {}
    from .models import SharedVideoLibrary
    existing_id = result.get("saved_template_id")
    if existing_id:
        t = db.get(SharedVideoLibrary, existing_id)
        if t and t.creator_id == job.user_id:
            try:
                _fill_template_schema(t, job, result)
                db.commit()
                result["saved_template_id"] = t.id
                job.result = result
            except Exception:
                db.rollback()
            return {"id": t.id, "title": t.title, "base_video_url": t.base_video_url}
        result.pop("saved_template_id", None)
    # Concurrent stage callbacks may race to create the first project; serialize per job.
    idea = (job.idea or "").strip()
    title = idea.replace("\n", " ")[:80].strip() or f"Pipeline {job.job_id}"
    first_frame = next(((kf.get("image_url")) for kf in (result.get("keyframes") or []) if kf.get("image_url")), "")
    t = SharedVideoLibrary(
        title=title,
        category="full",
        base_video_url="",
        thumbnail_url=first_frame,
        template_schema={},
        status="private",
        creator_id=job.user_id,
    )
    _fill_template_schema(t, job, result)
    db.add(t)
    db.commit()
    db.refresh(t)
    result["saved_template_id"] = t.id
    job.update(result=result)
    return {"id": t.id, "title": t.title, "base_video_url": t.base_video_url}
=======
    # Charge for video rendering
    video_cost = round(total_seconds * model_price, 2)
    from app import credits
    if video_cost > 0:
        fresh = db.get(__import__("app.models", fromlist=["User"]).User, job.user_id)
        if not credits.charge(db, job.user_id, video_cost):
            raise ValueError(f"Không đủ credit để render video (cần {video_cost} credit)")
        db.commit()

    updated = []
    for i, kf in enumerate(keyframes):
        step_progress = 60 + int((i / max(len(keyframes), 1)) * 25)
        job.update(progress=step_progress, step=f"Đang render cảnh {i + 1}/{len(keyframes)}...")

        prompt = kf["image_prompt"]
        dur = min(kf["thời_lượng_giây"], model.max_clip_seconds or 10)

        # First frame: dùng ảnh nhân vật nếu có (giữ nhất quán nhân vật)
        first_frame = job.character_image_url

        try:
            if video_model_id.startswith("minimax-h3"):
                # Gọi MiniMax-H3 trực tiếp (blocking, chạy trong luồng nền)
                dest = settings.outputs_dir / f"pipe_{job.job_id}_scene_{kf['stt']}.mp4"
                minimax.generate(
                    prompt=prompt,
                    dest=dest,
                    first_frame=resolve(first_frame) if first_frame else None,
                    duration=dur,
                    ratio=job.aspect_ratio,
                    resolution="768P",
                )
                kf["video_url"] = url_for(dest)
            elif video_model_id == "hunyuan-video":
                # HunyuanVideo (local CLI)
                from .local_video_adapter import generate_hunyuan_video, LocalVideoError
                result = generate_hunyuan_video(
                    prompt=prompt,
                    duration=dur,
                    resolution="720P",
                )
                kf["video_url"] = result["output_video_url"]
            elif video_model_id == "hunyuan-video-i2v":
                # HunyuanVideo-I2V (image-to-video, local CLI)
                from .local_video_adapter import generate_hunyuan_i2v, LocalVideoError
                result = generate_hunyuan_i2v(
                    prompt=prompt,
                    first_frame_image_url=first_frame,
                    duration=dur,
                    resolution="720P",
                )
                kf["video_url"] = result["output_video_url"]
            elif video_model_id == "wan2.1":
                # Wan2.1 (local CLI)
                from .local_video_adapter import generate_wan21_video, LocalVideoError
                result = generate_wan21_video(
                    prompt=prompt,
                    duration=dur,
                    resolution="720P",
                )
                kf["video_url"] = result["output_video_url"]
            else:
                # Fallback: chưa hỗ trợ pipeline tự động
                kf["video_url"] = ""
                kf["error"] = f"Model {video_model_id} chưa được kết nối vào pipeline tự động"
        except Exception as e:
            kf["video_url"] = ""
            kf["error"] = _safe_str(e)

        kf["status"] = "done" if kf.get("video_url") else "failed"
        updated.append(kf)

    return updated


def _run_editing(job: PipelineJob, keyframes: list[dict]) -> str:
    """Bước 4: Dựng thành phẩm từ các clip (FFmpeg concat)."""
    job.update(status="editing", progress=90, step="Đang dựng thành phẩm cuối...")
    video_urls = [kf["video_url"] for kf in keyframes if kf.get("video_url")]
    if not video_urls:
        # Collect error messages from failed clips
        errors = [_safe_str(kf.get("error", "Loi khong ro")) for kf in keyframes if not kf.get("video_url")]
        error_detail = "; ".join(errors[:3]) if errors else "Khong ro nguyen nhan"
        raise ValueError("Khong co clip nao de duoc thanh pham. Chi tiet: " + error_detail)

    from app.media import resolve
    clips = []
    for url in video_urls:
        p = resolve(url)
        if p and p.exists():
            clips.append(p)

    if not clips:
        raise ValueError("Không tìm thấy file clip cục bộ để dựng")

    import subprocess
    import tempfile
    from pathlib import Path

    settings.outputs_dir.mkdir(parents=True, exist_ok=True)
    out = settings.outputs_dir / f"pipeline_{job.user_id}_{secrets.token_hex(6)}.mp4"

    concat_file = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            concat_file = Path(f.name)
            for clip in clips:
                f.write(f"file '{clip.resolve().as_posix()}'\n")

        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
               "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
               "-c:a", "aac", "-shortest", str(out)]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg lỗi: {res.stderr[-500:]}")
    finally:
        if concat_file:
            concat_file.unlink(missing_ok=True)

    return url_for(out)
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa


# ---------------------------------------------------------------------------
# Full pipeline runner (runs in background thread)
# ---------------------------------------------------------------------------

def _run_full_pipeline(job: PipelineJob):
    try:
<<<<<<< HEAD
        if job.is_cancelled():
            job.update(status="cancelled", step="Đã dừng bởi người dùng")
            if getattr(job, "usage_id", None):
                with SessionLocal() as db:
                    from .featurebilling import finish
                    finish(db, job.usage_id, success=False)
            return
        # Lưu item ngay khi job bắt đầu chạy — người dùng xem tiến độ trong "Template của tôi".
        with SessionLocal() as db:
            try:
                save_pipeline_template(job, db)
            except Exception:
                import logging
                logging.warning("[pipeline] initial save failed")
        # Single-clip modes: Text→Video / Ảnh→Video (không storyboard)
        if getattr(job, "mode", "standard") in ("text_to_video", "image_to_video"):
            _run_single_clip_mode(job)
            with SessionLocal() as db:
                try:
                    save_pipeline_template(job, db)
                except Exception:
                    pass
                if getattr(job, "usage_id", None):
                    from .featurebilling import finish
                    finish(db, job.usage_id, success=True)
            _sync_template_progress(job)
            return
        # Step 1: Planning
        job.update(status="planning", progress=10, step="Đang tạo kịch bản...")
        plan = _run_planning(job)
        if job.is_cancelled():
            job.update(status="cancelled", step="Đã dừng bởi người dùng")
            if getattr(job, "usage_id", None):
                with SessionLocal() as db:
                    from .featurebilling import finish
                    finish(db, job.usage_id, success=False)
            return
        current_result = job.result or {}
        current_result.update({"plan": plan, "keyframes": []})
        job.update(result=current_result)
        with SessionLocal() as db:
            try:
                save_pipeline_template(job, db)
            except Exception:
                import logging
                logging.warning("[pipeline] save after planning failed")

        # Step 2: Keyframing
        with SessionLocal() as db:
            keyframes = _run_keyframing(job, plan, db)
        if job.is_cancelled():
            job.update(status="cancelled", step="Đã dừng bởi người dùng", result={"plan": plan, "keyframes": keyframes})
            _sync_template_progress(job)
            if getattr(job, "usage_id", None):
                with SessionLocal() as db:
                    from .featurebilling import finish
                    finish(db, job.usage_id, success=False)
            return
        job.result["keyframes"] = keyframes
        job.update(result=job.result, progress=50)
        with SessionLocal() as db:
            try:
                save_pipeline_template(job, db)
            except Exception:
                import logging
                logging.warning("[pipeline] save after keyframing failed")

        # Step 3: Rendering (bỏ qua hoàn toàn nếu chế độ chỉ gen ảnh)
        images_only = getattr(job, "mode", "standard") == "images_only"
        if images_only:
            job.update(status="keyframing", progress=85,
                       step="Ảnh phân cảnh đã xong — chế độ chỉ gen ảnh, không gen video")
        else:
            with SessionLocal() as db:
                keyframes = _run_rendering(job, keyframes, db)
            if job.is_cancelled():
                job.update(status="cancelled", step="Đã dừng bởi người dùng", result={"plan": plan, "keyframes": keyframes})
                _sync_template_progress(job)
                if getattr(job, "usage_id", None):
                    with SessionLocal() as db:
                        from .featurebilling import finish
                        finish(db, job.usage_id, success=False)
                return
            job.result["keyframes"] = keyframes
            job.update(result=job.result, progress=85)
            with SessionLocal() as db:
                try:
                    save_pipeline_template(job, db)
                except Exception:
                    import logging
                    logging.warning("[pipeline] save after rendering failed")

        # Bước 4: KHÔNG dựng video final — tool chỉ tạo clip phôi, khách tự edit.
        clips = [kf for kf in keyframes if kf.get("video_url")]
        if images_only:
            images_ok = sum(1 for kf in keyframes if kf.get("image_url"))
            if images_ok == 0:
                raise ValueError("Không tạo được ảnh phân cảnh nào — kiểm tra model ảnh và số dư credit rồi chạy lại.")
            job.result["images_only"] = True
            job.result["clip_count"] = 0
            done_step = f"Hoàn tất! Đã tạo {images_ok}/{len(keyframes)} ảnh phân cảnh (chế độ chỉ gen ảnh)"
        else:
            if not clips:
                raise ValueError(
                    "Không tạo được clip video nào — các cảnh gen video đều lỗi. "
                    "Kiểm tra lại model video, API key hoặc số dư credit rồi chạy lại.")
            job.result["clip_count"] = len(clips)
            done_step = f"Hoàn tất! Đã tạo {len(clips)}/{len(keyframes)} clip phôi — tự lưu vào Template của tôi"
        # Tự động lưu dự án raw (clip + storyboard + ảnh) vào "Template của tôi".
        with SessionLocal() as db:
            try:
                save_pipeline_template(job, db)
            except Exception as e:  # không để lỗi lưu làm hỏng pipeline đã chạy xong
                import logging
                logging.warning("[pipeline] auto-save template failed: %s", _safe_str(e))
        if getattr(job, "usage_id", None):
            with SessionLocal() as db:
                try:
                    from .featurebilling import finish
                    finish(db, job.usage_id, success=True)
                except Exception as billing_error:
                    logger.exception("[pipeline] settle feature reservation failed: %s", billing_error)
        job.update(status="done", progress=100, step=done_step, result=job.result)
        _sync_template_progress(job)

    except Exception as e:  # noqa: BLE001
        if job.is_cancelled():
            job.update(status="cancelled", step="Đã dừng bởi người dùng")
            _sync_template_progress(job)
            if getattr(job, "usage_id", None):
                with SessionLocal() as db:
                    from .featurebilling import finish
                    finish(db, job.usage_id, success=False)
            return
        safe_err = _safe_str(e)
        job.update(status="failed", error=safe_err, step="Loi: " + safe_err[:200])
        _sync_template_progress(job)
        with SessionLocal() as db:
            if getattr(job, "usage_id", None):
                try:
                    from .featurebilling import finish
                    finish(db, job.usage_id, success=False)
                except Exception as billing_error:
                    logger.exception("[pipeline] release feature reservation failed: %s", billing_error)
            try:
                save_pipeline_template(job, db)
            except Exception:
                logger.warning("[pipeline] save on failure failed")

=======
        # Step 1: Planning
        plan = _run_planning(job)
        job.update(result={"plan": plan, "keyframes": [], "video_urls": [], "final_url": ""})

        # Step 2: Keyframing
        keyframes = _run_keyframing(job, plan)
        job.result["keyframes"] = keyframes
        job.update(result=job.result, progress=50)

        # Step 3: Rendering
        with SessionLocal() as db:
            keyframes = _run_rendering(job, keyframes, db)
        job.result["keyframes"] = keyframes
        job.update(result=job.result, progress=85)

        # Step 4: Editing
        final_url = _run_editing(job, keyframes)
        job.result["final_url"] = final_url
        job.update(status="done", progress=100, step="Hoàn tất!", result=job.result)

    except Exception as e:  # noqa: BLE001
        safe_err = _safe_str(e)
        job.update(status="failed", error=safe_err, step="Loi: " + safe_err[:200])
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
def start_pipeline(job_id: str):
    """Chạy pipeline trong luồng nền."""
    job = get_job(job_id)
    if not job:
        return
    thread = threading.Thread(target=_run_full_pipeline, args=(job,), daemon=True)
    thread.start()
<<<<<<< HEAD
=======


# ---------------------------------------------------------------------------
# Convenience: list available models per step for UI
# ---------------------------------------------------------------------------

def available_steps() -> dict:
    from .modelregistry import STEPS
    out = {}
    for s in ("llm", "image_generate", "video_i2v"):
        ms = models_for_step(s)
        if ms:
            out[s] = {
                "label": STEPS.get(s, s),
                "models": [m.to_dict() for m in ms],
            }
    return out
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa

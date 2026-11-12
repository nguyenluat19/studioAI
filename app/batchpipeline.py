"""Gen video review hàng loạt: 1 nhân vật + nhiều ảnh sản phẩm.

Mỗi sản phẩm chạy đúng pipeline review_outfit (hook -> biến hình -> review -> chi tiết),
MỘT sản phẩm tại một thời điểm, các sản phẩm còn lại xếp hàng chờ.
Sản phẩm nào xong được tự động lưu vào "Template của tôi" của người dùng
(pipeline đã auto-save server-side). Mỗi sản phẩm chỉ được làm 1 lần.
"""
import secrets
import threading
from datetime import datetime, timezone

from . import autopipeline


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


MAX_PRODUCTS = 20


class BatchItem:
    def __init__(self, stt: int, title: str, outfit_url: str):
        self.stt = stt
        self.title = title
        self.outfit_image_url = outfit_url
        self.status = "queued"  # queued | running | done | failed | cancelled
        self.job_id = ""
        self.progress = 0
        self.step = "Trong hàng chờ"
        self.error = ""
        self.saved_template_id = None
        self.plan = None
        self.keyframes = []
        self.started_at = ""
        self.finished_at = ""

    def to_dict(self) -> dict:
        d = {
            "stt": self.stt,
            "title": self.title,
            "product_image_url": self.outfit_image_url,
            "status": self.status,
            "job_id": self.job_id,
            "progress": self.progress,
            "step": self.step,
            "error": self.error,
            "saved_template_id": self.saved_template_id,
            "plan": self.plan,
            "keyframes": self.keyframes,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }
        if self.status == "running" and self.job_id:
            job = autopipeline.get_job(self.job_id)
            if job is not None:
                d["progress"] = job.progress
                d["step"] = job.step
                d["error"] = job.error
                if job.status in ("cancelled", "failed"):
                    d["status"] = job.status
        return d


class BatchJob:
    def __init__(self, batch_id: str, user_id: int, selections: dict, idea: str,
                 duration: int, aspect_ratio: str, character_image_url: str,
                 product_urls: list[str], product_titles: list[str],
                 voice: str = "native", use_tts: bool = False,
                 language: str = "vi", hook_seconds: int = 3, usage_ids: list[int] | None = None):
        self.batch_id = batch_id
        self.user_id = user_id
        self.selections = selections
        self.idea = idea
        self.duration = duration
        self.aspect_ratio = aspect_ratio
        self.character_image_url = character_image_url
        self.voice = voice
        self.use_tts = use_tts
        self.language = language
        self.hook_seconds = hook_seconds
        self.usage_ids = list(usage_ids or [])
        self.items = [BatchItem(i + 1, (product_titles[i] if i < len(product_titles) else "")
                                or f"Sản phẩm {i + 1}", url)
                      for i, url in enumerate(product_urls)]
        self.status = "queued"  # queued | running | done | cancelled
        self.cancelled = False
        self.created_at = _now()
        self.updated_at = _now()
        self._lock = threading.Lock()

    def cancel(self) -> None:
        with self._lock:
            self.cancelled = True
            for item in self.items:
                if item.status == "running" and item.job_id:
                    job = autopipeline.get_job(item.job_id)
                    if job is not None:
                        job.cancel()
                elif item.status == "queued":
                    item.status = "cancelled"
                    item.step = "Đã hủy (batch dừng)"
            self.status = "cancelled"
            self.updated_at = _now()

    def is_cancelled(self) -> bool:
        with self._lock:
            return self.cancelled

    def to_dict(self) -> dict:
        with self._lock:
            items = [i.to_dict() for i in self.items]
            counts = {"done": 0, "failed": 0, "queued": 0, "running": 0, "cancelled": 0}
            for it in items:
                counts[it["status"]] = counts.get(it["status"], 0) + 1
            return {
                "batch_id": self.batch_id,
                "status": self.status,
                "total": len(items),
                "counts": counts,
                "items": items,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
            }


BATCHES: dict[str, BatchJob] = {}
BATCHES_LOCK = threading.Lock()


def create_batch(user_id: int, selections: dict, idea: str, duration: int,
                 aspect_ratio: str, character_image_url: str,
                 product_urls: list[str], product_titles: list[str] | None = None,
                 voice: str = "native", use_tts: bool = False,
                 language: str = "vi", hook_seconds: int = 3, usage_ids: list[int] | None = None) -> str:
    if not 1 <= len(product_urls) <= MAX_PRODUCTS:
        raise ValueError(f"Số sản phẩm phải từ 1 đến {MAX_PRODUCTS}")
    if usage_ids is not None and len(usage_ids) != len(product_urls):
        raise ValueError("Số reservation không khớp số sản phẩm")
    batch_id = "batch_" + secrets.token_hex(8)
    batch = BatchJob(batch_id, user_id, selections, idea, duration, aspect_ratio,
                     character_image_url, product_urls, product_titles or [],
                     voice=voice, use_tts=use_tts, language=language,
                     hook_seconds=hook_seconds, usage_ids=usage_ids)
    with BATCHES_LOCK:
        BATCHES[batch_id] = batch
    return batch_id


def get_batch(batch_id: str) -> BatchJob | None:
    with BATCHES_LOCK:
        return BATCHES.get(batch_id)


def _item_idea(batch: BatchJob, item: BatchItem) -> str:
    base = (batch.idea or "").strip()
    suffix = f" — sản phẩm: {item.title}"
    return (base + suffix)[:3000]


def _run_batch(batch: BatchJob, items: list | None = None):
    try:
        if not batch.is_cancelled():
            batch.status = "running"
            batch.updated_at = _now()
        target = items if items is not None else list(batch.items)
        for item in target:
            if batch.is_cancelled():
                if item.status in ("queued", "running"):
                    item.status = "cancelled"
                    item.step = "Đã hủy (batch dừng)"
                continue
            item.status = "running"
            item.step = "Đang khởi tạo pipeline..."
            item.started_at = _now()
            batch.updated_at = _now()
            try:
                job_id = autopipeline.create_job(
                    user_id=batch.user_id,
                    selections=batch.selections,
                    idea=_item_idea(batch, item),
                    duration=batch.duration,
                    aspect_ratio=batch.aspect_ratio,
                    character_image_url=batch.character_image_url,
                    voice=batch.voice,
                    use_tts=batch.use_tts,
                    language=batch.language,
                    mode="review_outfit",
                    outfit_image_url=item.outfit_image_url,
                    hook_seconds=batch.hook_seconds,
                    usage_id=batch.usage_ids[item.stt - 1] if item.stt - 1 < len(batch.usage_ids) else None,
                )
                item.job_id = job_id
                job = autopipeline.get_job(job_id)
                autopipeline._run_full_pipeline(job)  # chạy đồng bộ: 1 sản phẩm/lần
                d = job.to_dict()
                result = d.get("result") or {}
                item.progress = 100
                item.finished_at = _now()
                if d["status"] == "done":
                    item.status = "done"
                    item.step = "Hoàn tất — đã tự động lưu vào Template của tôi"
                    item.saved_template_id = result.get("saved_template_id")
                    item.plan = result.get("plan")
                    item.keyframes = result.get("keyframes") or []
                elif d["status"] == "cancelled":
                    item.status = "cancelled"
                    item.step = "Đã hủy bởi người dùng"
                else:
                    item.status = "failed"
                    item.step = "Lỗi"
                    item.error = d.get("error") or "Pipeline thất bại"
            except Exception as e:  # noqa: BLE001
                item.status = "failed"
                item.step = "Lỗi"
                item.error = str(e)[:500]
                item.finished_at = _now()
            batch.updated_at = _now()
        if not batch.is_cancelled():
            batch.status = "done"
            batch.updated_at = _now()
        from .featurebilling import finish
        from .db import SessionLocal
        for i, usage_id in enumerate(batch.usage_ids):
            item = batch.items[i] if i < len(batch.items) else None
            succeeded = bool(item and item.status == "done")
            with SessionLocal() as db:
                finish(db, usage_id, success=succeeded)
    except Exception as e:  # noqa: BLE001
        batch.status = "failed"
        batch.updated_at = _now()
        for item in batch.items:
            if item.status in ("queued", "running"):
                item.status = "failed"
                item.error = str(e)[:500]
                item.finished_at = _now()
    finally:
        from .featurebilling import finish
        from .db import SessionLocal
        for i, usage_id in enumerate(batch.usage_ids):
            item = batch.items[i] if i < len(batch.items) else None
            succeeded = bool(item and item.status == "done")
            with SessionLocal() as db:
                finish(db, usage_id, success=succeeded)

def retry_batch_items(batch_id: str, stt_ids: list[int] | None = None) -> dict:
    """Chạy lại CHỈ các sản phẩm bị lỗi (hoặc các stt trong stt_ids). Không đụng item đã xong."""
    batch = get_batch(batch_id)
    if batch is None:
        raise ValueError("Không tìm thấy batch")
    if batch.status == "running":
        raise ValueError("Batch đang chạy, hãy chờ hoặc dừng trước khi thử lại")
    wanted = [it for it in batch.items if it.status == "failed"]
    if stt_ids is not None:
        ids = set(stt_ids)
        wanted = [it for it in wanted if it.stt in ids]
    if not wanted:
        raise ValueError("Không có sản phẩm lỗi để thử lại")
    for it in wanted:
        it.status = "queued"
        it.step = "Chờ thử lại"
        it.error = ""
        it.progress = 0
        it.started_at = None
        it.finished_at = None
        it.job_id = None
        it.saved_template_id = None
    batch.status = "running"
    batch.updated_at = _now()
    thread = threading.Thread(target=_run_batch, args=(batch, wanted), daemon=True)
    thread.start()
    return {"status": "queued", "retrying": len(wanted)}


def start_batch(batch_id: str):
    batch = get_batch(batch_id)
    if not batch:
        return
    thread = threading.Thread(target=_run_batch, args=(batch,), daemon=True)
    thread.start()

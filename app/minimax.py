"""MiniMax-H3 video generation client (async task API: create -> poll -> download).

Request shape follows the xah.io v2 public gateway: POST {base}/v2/video_generation with
{model, content:[{type:text|image_url,...}], duration, ratio}. The query endpoint is
/v2/query/video_generation/{task_id}. Run scripts/check_minimax.py once with your key
to confirm against the live API.
"""
import base64
import io
import json
import logging
import mimetypes
import subprocess
import time
from pathlib import Path

import httpx

try:
    from PIL import Image as _PIL_Image
    _PILLOW_AVAILABLE = True
except ImportError:
    _PILLOW_AVAILABLE = False

from .config import settings

logger = logging.getLogger(__name__)

RATIOS = ("9:16", "16:9", "1:1", "4:3", "3:4", "21:9")
RESOLUTIONS = ("768P", "2K")
MIN_SECONDS, MAX_SECONDS = 4, 15
MIN_IMAGE_SIDE = 256   # MiniMax rejects images smaller than this on either side
OK_STATES = {"succeeded", "success", "completed", "done", "finished"}
FAIL_STATES = {"failed", "fail", "cancelled", "canceled", "error", "expired"}
QUERY_FALLBACKS = (
    "/v2/query/video_generation/{task_id}",   # xah.io public gateway (primary)
    "/v2/video_generation/{task_id}",          # minimax.io direct
    "/v2/query/video_generation?task_id={task_id}",
    "/v1/query/video_generation?task_id={task_id}",
)

# Giao thức OpenAI-style (/v1/videos): dùng cho các gateway không có endpoint
# MiniMax (vd api.vilao.ai). Nhận diện tự động: gọi tạo task kiểu MiniMax trước,
# nếu gateway trả 404/405 (không có route) thì chuyển sang OpenAI-style.
OPENAI_OK_STATES = {"completed", "succeeded", "success", "done", "finished"}
OPENAI_FAIL_STATES = {"failed", "fail", "cancelled", "canceled", "error", "expired"}
_openai_bases: set[str] = set()


class VideoError(RuntimeError):
    pass


class VideoRouteMissing(VideoError):
    """Gateway không có endpoint kiểu MiniMax — thử giao thức OpenAI-style."""


def configured() -> bool:
    return bool(settings.minimax_api_key)


def _headers(api_key: str | None = None) -> dict:
    return {"Authorization": f"Bearer {api_key or settings.minimax_api_key}",
            "Content-Type": "application/json"}


def _dig(d, *paths):
    """First non-empty value found along any of the dotted paths."""
    for path in paths:
        cur = d
        for key in path.split("."):
            cur = cur.get(key) if isinstance(cur, dict) else None
            if cur is None:
                break
        if cur not in (None, "", []):
            return cur
    return None


def _ensure_min_size(image_bytes: bytes, mime: str) -> tuple[bytes, str]:
    """Resize image so both sides are >= MIN_IMAGE_SIDE px. Returns (bytes, mime).
    Falls back to the original if Pillow is unavailable or the image is already large enough.
    """
    if not _PILLOW_AVAILABLE:
        return image_bytes, mime
    try:
        img = _PIL_Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        if w >= MIN_IMAGE_SIDE and h >= MIN_IMAGE_SIDE:
            return image_bytes, mime
        # Scale up so the smaller side reaches MIN_IMAGE_SIDE, preserving aspect ratio.
        scale = MIN_IMAGE_SIDE / min(w, h)
        new_w, new_h = max(MIN_IMAGE_SIDE, int(w * scale)), max(MIN_IMAGE_SIDE, int(h * scale))
        img = img.resize((new_w, new_h), _PIL_Image.LANCZOS)
        buf = io.BytesIO()
        fmt = img.format or "PNG"
        img.save(buf, format=fmt)
        return buf.getvalue(), f"image/{fmt.lower()}"
    except Exception:
        return image_bytes, mime


def build_payload(prompt: str, duration: int, ratio: str, resolution: str,
                  first_frame: Path | None = None, model: str | None = None) -> dict:
    content: list[dict] = [{"type": "text", "text": prompt}]
    if first_frame is not None:
        raw = first_frame.read_bytes()
        mime = mimetypes.guess_type(first_frame.name)[0] or "image/png"
        raw, mime = _ensure_min_size(raw, mime)
        b64 = base64.b64encode(raw).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"},
                        "role": "first_frame"})
    body = {"model": model or settings.minimax_model, "content": content, "resolution": resolution,
            "duration": duration, "ratio": ratio}
    if settings.minimax_extra:
        try:
            body.update(json.loads(settings.minimax_extra))
        except ValueError as e:
            raise VideoError(f"MINIMAX_EXTRA_PARAMS không phải JSON hợp lệ: {e}") from e
    return body


def _check_base_resp(data: dict) -> None:
    br = data.get("base_resp") or {}
    if br.get("status_code") not in (None, 0):
        raise VideoError(f"MiniMax từ chối: {br.get('status_msg') or br}")
    err = data.get("error")
    if err:
        raise VideoError(f"MiniMax lỗi: {err}")


def create_task(client: httpx.Client, payload: dict, base_url: str | None = None,
                api_key: str | None = None) -> str:
    base = (base_url or settings.minimax_base_url).rstrip("/")
    last = None
    for attempt in range(3):
        try:
            r = client.post(base + settings.minimax_create_path, json=payload, headers=_headers(api_key))
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.RemoteProtocolError):
            last = None
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code in (404, 405):
            raise VideoRouteMissing(f"Gateway không có endpoint {base}{settings.minimax_create_path} (HTTP {r.status_code})")
        if r.status_code in (429, 502, 503, 504):
            last = r
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code >= 400:
            raise VideoError(f"MiniMax tạo task lỗi HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        _check_base_resp(data)
        tid = _dig(data, "task_id", "id", "data.task_id", "task.id", "task.task_id")
        if not tid:
            raise VideoError(f"MiniMax không trả task_id: {str(data)[:300]}")
        return str(tid)
    raise VideoError(f"MiniMax tạo task lỗi HTTP {last.status_code if last else '?'}: {(last.text if last else 'connection refused')[:300]}")


_query_template: dict[str, str] = {}   # per-base remembers the first query path that worked


def query_task(client: httpx.Client, task_id: str, base_url: str | None = None,
               api_key: str | None = None) -> tuple[str, str | None, dict]:
    """-> (state: 'ok'|'failed'|'pending', video_url|None, raw)"""
    base = (base_url or settings.minimax_base_url).rstrip("/")
    cached = _query_template.get(base)
    candidates = ([cached] if cached else []) + [settings.minimax_query_path, *QUERY_FALLBACKS]
    last = None
    for tmpl in candidates:
        r = client.get(base + tmpl.format(task_id=task_id), headers=_headers(api_key))
        if r.status_code in (404, 405):
            last = r
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            # Lỗi tạm thời phía gateway/upstream — để vòng poll thử lại thay vì đánh hỏng cảnh.
            return "pending", None, {"status": "retrying", "http_status": r.status_code,
                                     "detail": r.text[:300]}
        if r.status_code >= 400:
            raise VideoError(f"MiniMax tra cứu lỗi HTTP {r.status_code}: {r.text[:300]}")
        _query_template[base] = tmpl
        data = r.json()
        _check_base_resp(data)
        status = str(_dig(data, "status", "task.status", "data.status") or "").lower()
        url = _dig(data, "content.url", "task.content.url", "data.content.url", "video_url", "url")
        if not url and status in OK_STATES:
            fid = _dig(data, "file_id", "task.file_id", "data.file_id")
            if fid:
                url = _file_url(client, fid, base_url=base_url, api_key=api_key)
        if status in FAIL_STATES:
            return "failed", None, data
        return ("ok" if (status in OK_STATES and url) else "pending"), url, data
    raise VideoError(f"MiniMax: không tìm thấy endpoint tra cứu task (HTTP {last.status_code if last else '?'}); "
                     "chạy scripts/check_minimax.py và đặt MINIMAX_QUERY_PATH")


def _file_url(client: httpx.Client, file_id: str, base_url: str | None = None,
              api_key: str | None = None) -> str | None:
    base = (base_url or settings.minimax_base_url).rstrip("/")
    r = client.get(f"{base}/v1/files/retrieve", params={"file_id": file_id},
                   headers=_headers(api_key))
    return _dig(r.json(), "file.download_url", "download_url") if r.status_code < 400 else None


# ── Giao thức OpenAI-style video (POST {base}/videos, GET {base}/videos/{id}) ──

def _openai_seconds(client: httpx.Client, base: str, api_key: str | None,
                    model: str | None, duration: int) -> int:
    """Gateway kiểu Veo chỉ nhận các mốc seconds cố định (vd 4/6/8) — bám về mốc gần nhất nếu tra được."""
    try:
        r = client.get(f"{base}/models", headers=_headers(api_key), timeout=30)
        if r.status_code == 200:
            bare = (model or "").split("/")[-1]
            for m in r.json().get("data", []):
                if m.get("id") == model or m.get("model_id") == model or m.get("id") == bare:
                    vals = [int(s) for s in (m.get("model_options") or {}).get("seconds") or []
                            if str(s).isdigit()]
                    if vals:
                        return min(vals, key=lambda v: abs(v - duration))
    except Exception as e:
        logger.warning("[minimax] model_options lookup failed for %s: %s", model, e)
    # Không tra được model_options -> mặc định mốc nhỏ nhất hợp lý (4s) thay vì nguyên duration
    # (veo chỉ chấp nhận 4/6/8; trả nguyên duration có thể bị từ chối 400).
    return min(duration, 4)


def _openai_create(client: httpx.Client, *, base: str, api_key: str | None, model: str | None,
                   prompt: str, duration: int, ratio: str, first_frame: Path | None) -> str:
    size = ratio if ratio in ("16:9", "9:16") else "auto"
    secs = _openai_seconds(client, base, api_key, model, duration)
    body: dict = {"model": model or settings.minimax_model, "prompt": prompt,
                  "seconds": str(secs), "size": size}
    if first_frame is not None:
        raw = first_frame.read_bytes()
        mime = mimetypes.guess_type(first_frame.name)[0] or "image/png"
        raw, mime = _ensure_min_size(raw, mime)
        # Gửi ảnh dạng base64 trong JSON (vilao chấp nhận trường input_image).
        # Không dùng multipart vì gateway từ chối 400.
        body["input_image"] = f"data:{mime};base64,{base64.b64encode(raw).decode()}"
    last = None
    for attempt in range(4):
        try:
            r = client.post(base + "/videos", headers=_headers(api_key), timeout=180,
                            json=body)
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.RemoteProtocolError):
            last = None
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code in (401, 403):
            raise VideoError(f"Gateway video từ chối HTTP {r.status_code}: {r.text[:200]}")
        if r.status_code not in (429, 502, 503, 504):
            data = r.json()
            tid = _dig(data, "id", "task_id", "data.id")
            if not tid:
                raise VideoError(f"Gateway video không trả task id: {str(data)[:300]}")
            return str(tid)
        last = r
        time.sleep(5 * (attempt + 1))
    raise VideoError(f"Gateway video tạo task lỗi HTTP {last.status_code if last else '?'}: {(last.text if last else 'connection refused')[:300]}")


def _openai_query(client: httpx.Client, task_id: str, *, base: str, api_key: str | None,
                  model: str | None) -> tuple[str, str | None, dict]:
    """-> (state: 'ok'|'failed'|'pending', video_url|None, raw)"""
    params = {"model": model} if model else None
    for attempt in range(3):
        try:
            r = client.get(f"{base}/videos/{task_id}", params=params, headers=_headers(api_key))
            break
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError):
            time.sleep(5 * (attempt + 1))
            if attempt == 2:
                raise VideoError("Gateway video không phản hồi khi truy vấn task")
            continue
    if r.status_code in (429, 500, 502, 503, 504):
        # Gateway/upstream tạm thời quá tải (vd SERVICE_UNAVAILABLE) — không đánh hỏng cảnh,
        # coi như đang xử lý để vòng poll bên ngoài thử lại (bị chặn bởi minimax_max_wait).
        return "pending", None, {"status": "retrying", "http_status": r.status_code,
                                 "detail": r.text[:300]}
    if r.status_code >= 400:
        raise VideoError(f"Gateway video truy vấn lỗi HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    status = str(data.get("status") or "").lower()
    # video_url trỏ sang CDN (tuansuapi.store) có thể yêu cầu auth khác — dùng endpoint
    # nội dung của chính gateway đã xác thực được (đã verify với vilao.ai).
    url = f"{base}/videos/{task_id}/content" + (f"?model={model}" if model else "")
    if status in OPENAI_FAIL_STATES:
        return "failed", None, data
    return ("ok" if status in OPENAI_OK_STATES else "pending"), url, data


def has_video_stream(path: Path) -> bool:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=codec_type", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return "video" in out.stdout


def generate(prompt: str, dest: Path, *, duration: int = 5, ratio: str = "9:16", resolution: str = "768P",
             first_frame: Path | None = None, on_progress=lambda: None,
             base_url: str | None = None, api_key: str | None = None, model: str | None = None) -> Path:
    """Blocks (polling) until the video is saved to `dest`; raises VideoError on any failure."""
    if base_url and not api_key:
        raise VideoError("Model chưa có API key riêng; vui lòng nhập API key trong Quản lý Model")
    if not api_key and not settings.minimax_api_key:
        raise VideoError("API key video chưa được cấu hình")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.Client(timeout=60) as client:
            base = (base_url or settings.minimax_base_url).rstrip("/")
            tid = None
            openai_proto = base in _openai_bases
            if not openai_proto:
                try:
                    tid = create_task(client, build_payload(prompt, duration, ratio, resolution, first_frame,
                                                            model=model),
                                      base_url=base_url, api_key=api_key)
                except VideoRouteMissing:
                    _openai_bases.add(base)
                    openai_proto = True
            if openai_proto:
                if tid is None:
                    tid = _openai_create(client, base=base, api_key=api_key, model=model,
                                         prompt=prompt, duration=duration, ratio=ratio,
                                         first_frame=first_frame)
                poll = lambda: _openai_query(client, tid, base=base, api_key=api_key, model=model)
            else:
                poll = lambda: query_task(client, tid, base_url=base_url, api_key=api_key)
            deadline = time.monotonic() + settings.minimax_max_wait
            while True:
                state, url, raw = poll()
                on_progress()   # heartbeat so the reaper knows we are alive
                if state == "ok":
                    break
                if state == "failed":
                    raise VideoError(f"Tạo video thất bại: {str(raw)[:300]}")
                if time.monotonic() > deadline:
                    raise VideoError(f"Video quá thời gian chờ ({int(settings.minimax_max_wait)}s) cho task {tid}")
                time.sleep(settings.minimax_poll)
            headers = _headers(api_key)
            last = None
            for attempt in range(4):
                try:
                    with client.stream("GET", url, headers=headers, timeout=300, follow_redirects=True) as resp:
                        if resp.status_code in (401, 403):
                            raise VideoError(f"Tải video lỗi HTTP {resp.status_code}")
                        if resp.status_code in (429, 502, 503, 504):
                            last = resp.status_code
                            time.sleep(5 * (attempt + 1))
                            continue
                        if resp.status_code >= 400:
                            raise VideoError(f"Tải video lỗi HTTP {resp.status_code}")
                        total = 0
                        with dest.open("wb") as f:
                            for chunk in resp.iter_bytes(1 << 20):
                                f.write(chunk)
                                total += len(chunk)
                        expected = resp.headers.get("content-length")
                    # Kiểm tra file nguyên vẹn trước khi chấp nhận — file bị cắt
                    # (truncated) vẫn qua được kiểm tra stream cũ nên dẫn tới final thiếu cảnh.
                    if expected and total != int(expected):
                        dest.unlink(missing_ok=True)
                        last = f"incomplete download {total}/{expected}"
                        time.sleep(5 * (attempt + 1))
                        continue
                    # ffmpeg (không phải ffprobe) mới hỗ trợ -xerror: giải mã toàn file,
                    # lỗi nào cũng coi là tải hỏng.
                    check = subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(dest),
                                            "-f", "null", "-"], capture_output=True, timeout=300)
                    if check.returncode != 0:
                        dest.unlink(missing_ok=True)
                        last = "corrupt download"
                        time.sleep(5 * (attempt + 1))
                        continue
                    break
                except (httpx.ReadTimeout, httpx.ConnectError, httpx.RemoteProtocolError):
                    last = "timeout"
                    time.sleep(5 * (attempt + 1))
                    continue
            else:
                raise VideoError(f"Tải video thất bại sau nhiều lần thử (cuối cùng: {last})")
    except httpx.HTTPError as e:
        raise VideoError(f"Lỗi mạng khi gọi gateway video: {e}") from e
    if not dest.exists() or dest.stat().st_size < 1000 or not has_video_stream(dest):
        dest.unlink(missing_ok=True)
        raise VideoError("File tải về từ MiniMax không phải video hợp lệ")
    return dest

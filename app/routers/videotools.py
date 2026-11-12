"""Video tools: download from social media, transcribe & translate, add subtitles & blur."""
import logging
import os
import re
import secrets
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import ai
from ..activity import log_activity
from ..config import settings
from ..db import get_db
from ..deps import current_user
from ..llm import resolve_llm as _resolve_llm
from ..media import resolve, url_for, user_outputs_dir
from ..models import User

router = APIRouter(prefix="/api/video", tags=["videotools"])
logger = logging.getLogger(__name__)

# Theo dõi tiến độ tải theo job_id (dùng cho progress bar trên UI). Key: job_id, value: {percent, status}
DOWNLOAD_PROGRESS: dict[str, dict] = {}


def _udir(user):
    """Outputs folder riêng của user."""
    return user_outputs_dir(user.id)


def _prune_progress() -> None:
    now = time.time()
    stale = [k for k, v in DOWNLOAD_PROGRESS.items() if now - v.get("updated_at", now) > 3600]
    for k in stale:
        DOWNLOAD_PROGRESS.pop(k, None)


def _dl_progress(job_id: str, total_items: int = 1):
    """Trả về progress_hook của yt-dlp ghi tiến độ vào DOWNLOAD_PROGRESS (theo byte)."""
    state = {"completed": 0, "current": 0, "total": max(1, int(total_items))}

    def hook(d):
        prev = DOWNLOAD_PROGRESS.get(job_id, {})
        uid = prev.get("user_id")

        def _set(percent, status):
            DOWNLOAD_PROGRESS[job_id] = {"percent": int(percent), "status": status, "user_id": uid, "updated_at": time.time()}

        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            speed = d.get("speed")
            eta = d.get("eta")
            cur = int(done / total * 100) if total > 0 else state["current"]
            state["current"] = max(state["current"], cur)
            pct = int((state["completed"] + state["current"] / 100) / state["total"] * 100)
            DOWNLOAD_PROGRESS[job_id] = {"percent": min(99, max(0, pct)), "status": "downloading",
                                         "user_id": uid, "updated_at": time.time(),
                                         "eta": (int(eta) if isinstance(eta, (int, float)) else None),
                                         "speed": (float(speed) if isinstance(speed, (int, float)) else None),
                                         "total_bytes": (int(total) if total else None),
                                         "downloaded_bytes": (int(done) if done else None)}
        elif d.get("status") == "finished":
            state["completed"] += 1
            state["current"] = 0
            pct = int(state["completed"] / state["total"] * 100)
            _set(min(99, pct), "downloading" if state["completed"] < state["total"] else "finished")

    return hook


def _bump_progress(job_id: str, user_id: int, completed: int, total: int) -> None:
    """Báo tiến độ theo số item xong (dùng cho nhánh không đi qua yt-dlp hook,vd TikWM)."""
    if not job_id:
        return
    DOWNLOAD_PROGRESS[job_id] = {"percent": min(99, int(completed / max(1, total) * 100)),
                                 "status": "downloading", "user_id": user_id, "updated_at": time.time()}


def _set_progress_status(job_id: str, user_id: int, percent: int, status: str) -> None:
    if not job_id:
        return
    DOWNLOAD_PROGRESS[job_id] = {"percent": int(percent), "status": status, "user_id": user_id, "updated_at": time.time()}


class DownloadIn(BaseModel):
    url: str = Field(min_length=5)
    job_id: str = ""   # optional: bật thanh tiến độ trên UI qua /download-progress/{job_id}


class TranscribeIn(BaseModel):
    video_url: str
    target_lang: str = "vi"   # mã ngôn ngữ đích ("en", "vi", …); "same" = giữ ngôn ngữ gốc phát hiện
    subtitle_mode: str = "auto"   # auto | original | translated | bilingual
    quality: str = "accurate"     # fast (small) | accurate (medium) | best (large-v3)
    use_llm: bool = True          # dùng model chat admin để sửa thoại + dịch theo ngữ cảnh
    llm_model: str = ""           # model LLM cụ thể; rỗng = tự chọn model rẻ nhất đang bật


class ProcessIn(BaseModel):
    video_url: str
    srt_content: str | None = None
    sub_position: str = "bottom"  # bottom | top | middle
    sub_font_size: int = 18
    sub_color: str = "&H00FFFFFF"  # White with black outline in ASS hex
    blur_region: dict[str, Any] | None = None  # {x, y, width, height} in pixels or percent
    tts_voice: str = ""            # voice TTS để lồng tiếng (rỗng = không lồng tiếng)
    src_volume: float = 0.0        # 0.0 = tắt âm gốc khi lồng tiếng; 1.0 = giữ nguyên
    tts_emotion: str = ""          # cảm xúc giọng đọc (vui ve|phan khich|tinh|...); rỗng = bình thường
    keep_original_audio: bool = False  # nếu true, giữ âm gốc nguyên; mặc định tắt khi lồng tiếng




# Ngôn ngữ đích hỗ trợ dịch qua HF Inference API (Helsinki-NLP/opus-mt-<src>-<tgt>).
TRANSLATE_LANG_CHOICES = [
    ("vi", "Tiếng Việt"),
    ("en", "English"),
    ("zh", "中文 (Chinese)"),
    ("ja", "日本語 (Japanese)"),
    ("ko", "한국어 (Korean)"),
    ("fr", "Français"),
    ("es", "Español"),
    ("de", "Deutsch"),
    ("ru", "Русский"),
    ("pt", "Português"),
    ("th", "ไทย"),
    ("id", "Bahasa Indonesia"),
]
_OPUS_LANGS = {c: c for c, _ in TRANSLATE_LANG_CHOICES}


def opus_model_for(src: str, tgt: str):
    """Helsinki-NLP/opus-mt-<src>-<tgt>; None nếu cặp không hợp lệ / không có dịch."""
    if not src or not tgt or src == tgt:
        return None
    if src not in _OPUS_LANGS or tgt not in _OPUS_LANGS:
        return None
    return f"Helsinki-NLP/opus-mt-{src}-{tgt}"


def _translate_hf(texts: list[str], src_lang: str, tgt_lang: str, hf_key: str) -> list[str] | None:
    """Dịch qua HF Inference API (Helsinki-NLP/opus-mt-*). Cần prepaid credits (402 nếu chưa nạp)."""
    if not hf_key:
        return None
    model = opus_model_for(src_lang, tgt_lang)
    if not model:
        return None
    try:
        import httpx
        url = f"https://router.huggingface.co/hf-inference/models/{model}"
        with httpx.Client(timeout=90) as client:
            resp = client.post(url, headers={"Authorization": f"Bearer {hf_key.strip()}"},
                               json={"inputs": texts})
        if resp.status_code != 200:
            logger.warning("HF opus-mt %s->%s failed: %s %s", src_lang, tgt_lang, resp.status_code, resp.text[:200])
            return None
        res = resp.json()
        if isinstance(res, list) and len(res) == len(texts):
            return [str(item.get("translation_text", "")).strip() for item in res]
    except Exception as e:
        logger.warning("HF translate failed: %s", e)
    return None


def _translate_google(texts: list[str], src_lang: str, tgt_lang: str) -> list[str] | None:
    """Fallback dịch MIỄN PHÍ qua endpoint công khai của Google Translate (client=gtx).

    Không cần key; dịch theo từng câu. Trả None nếu không khả dụng (mạng/429/giới hạn).
    """
    if src_lang == tgt_lang:
        return list(texts)
    try:
        import httpx, urllib.parse, json
        out = []
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            for i, t in enumerate(texts):
                t = t.strip()
                if not t:
                    out.append("")
                    continue
                params = {"client": "at", "sl": src_lang or "auto",
                          "tl": tgt_lang, "dt": "t", "q": t}
                try:
                    resp = client.get("https://translate.googleapis.com/translate_a/single",
                                      params=params,
                                      headers={"User-Agent": "GoogleTranslate/6.8.1 (Linux; U; Android 10; en_US; SM-G970F Build/QP1A.190711.020)"})
                    if resp.status_code == 429:   # thử lại với client=mobile (ít bị chặn hơn)
                        resp = client.get("https://translate.googleapis.com/translate_a/single",
                                          params={**params, "client": "mobile"},
                                          headers={"User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 Chrome/130.0.0.0 Mobile Safari/537.36"})
                    if resp.status_code != 200:
                        logger.warning("Google translate HTTP %s for line %d", resp.status_code, i)
                        return None
                    data = resp.json()
                    translated = "".join(part[0] for part in data[0] if part and part[0])
                    out.append(translated.strip())
                except Exception as e:
                    logger.warning("Google translate line %d failed: %s", i, e)
                    return None
        return out
    except Exception as e:
        logger.warning("Google translate failed: %s", e)
        return None


def _parse_srt(text: str) -> list[tuple[float, float, str]]:
    """Parse SRT thành [(start_sec, end_sec, text)]. Bỏ qua block hỏng."""
    out = []
    for block in re.split(r"\n\s*\n", (text or "").strip()):
        lines = [l for l in block.splitlines() if l.strip()]
        if len(lines) < 3:
            continue
        m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", lines[1])
        if not m:
            continue
        h0, m0, s0, ms0, h1, m1, s1, ms1 = (int(x) for x in m.groups())
        start = h0 * 3600 + m0 * 60 + s0 + ms0 / 1000
        end = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000
        body = "\n".join(lines[2:]).strip()
        out.append((start, end, body))
    return out


def _format_srt_time(seconds: float) -> str:
    millis = int((seconds % 1) * 1000)
    secs = int(seconds) % 60
    mins = (int(seconds) // 60) % 60
    hours = int(seconds) // 3600
    return f"{hours:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def _format_ass_time(seconds: float) -> str:
    cs = int((seconds % 1) * 100)
    s = int(seconds) % 60
    m = int(seconds) // 60 % 60
    h = int(seconds) // 3600
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _srt_to_ass(srt_text: str, out_path: Path, *, fsize: int, position: str, width: int, height: int) -> Path:
    """SRT → ASS với PlayResX/Y = kích thước video thật — font render đúng cỡ ở mọi độ phân giải."""
    align = {"bottom": 2, "top": 6, "middle": 10}.get(position, 2)
    # font size scale theo chiều cao video (tham chiếu 720px) để hiển thị đồng đều mọi độ phân giải
    scaled = max(10, int(round(fsize * height / 720)))
    style = (f"Default,Arial,{scaled},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
             f"-1,0,0,0,100,100,0,0,1,2.5,1.2,{align},40,40,30,1")
    parts = [
        "[Script Info]\n",
        "ScriptType: v4.00+\n",
        f"PlayResX: {width}\n",
        f"PlayResY: {height}\n",
        "ScaledBorderAndShadow: yes\n\n",
        "[V4+ Styles]\n",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n",
        f"Style: {style}\n\n",
        "[Events]\n",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n",
    ]
    events = []
    for t0, t1, txt in _parse_srt(srt_text):
        txt = txt.replace("{", "(").replace("}", ")").replace("\\", "")
        txt = txt.replace("\r\n", "\n").replace("\n", r"\N")
        events.append(f"Dialogue: 0,{_format_ass_time(t0)},{_format_ass_time(t1)},Default,,0000,0000,0000,,{txt}")
    parts.append("\n".join(events) + "\n")
    out_path.write_text("".join(parts), encoding="utf-8")
    return out_path


@router.get("/hf-status")
def get_hf_status(user: User = Depends(current_user)):
    """User không được xem key — chỉ trả về việc đã cấu hình hay chưa (key chỉ nằm trong .env)."""
    has_key = bool(settings.huggingface_api_key and settings.huggingface_api_key.strip())
    return {
        "configured": has_key,
    }


@router.post("/transcribe")
def transcribe_video(body: TranscribeIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Transcribe video audio locally (faster-whisper, auto language detect) and translate to target_lang."""
    local_path = resolve(body.video_url, user.id)
    if not local_path or not local_path.exists():
        raise HTTPException(404, "Không tìm thấy file video đã nạp — hãy chọn lại video nguồn")
    from .. import subtitles as _subs

    # Thời lượng container (để phát hiện file bị cắt/hỏng — audio decode ra ít hơn thực tế)
    container_seconds = None
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=noprint_wrappers=1:nokey=1", str(local_path)],
                           capture_output=True, text=True, timeout=30)
        container_seconds = float(r.stdout.strip()) if r.stdout.strip() else None
    except Exception:
        container_seconds = None

    # 1. Extract audio to 16kHz mono wav
    wav_path = _udir(user) / f"audio_{secrets.token_hex(8)}.wav"
    try:
        cmd = ["ffmpeg", "-y", "-i", str(local_path), "-vn", "-ar", "16000", "-ac", "1", str(wav_path)]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=600)
    except Exception as e:
        if wav_path.exists():
            wav_path.unlink()
        raise HTTPException(500, f"Lỗi trích xuất âm thanh: {e}")

    segments = []
    detected_lang = "unknown"
    engine_used = "faster-whisper (Local CPU)"
    asr_info: dict = {}
    try:
        import numpy as np
        # Decode audio qua ffmpeg sang raw PCM s16le 16k mono – không phụ thuộc PyAV
        # (av>=15 bỏ tham số metadata_errors mà faster-whisper 1.x vẫn dùng → TypeError).
        pcm = subprocess.run(
            ["ffmpeg", "-y", "-i", str(wav_path), "-f", "s16le", "-ar", "16000", "-ac", "1", "pipe:1"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=1800).stdout
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        pcm_seconds = len(audio) / 16000.0
        # transcribe_audio: model theo `quality` (mặc định medium), VAD mềm hơn, và
        # vá các khoảng lặng mà VAD cắt mất để không rơi thoại (xem app/subtitles.py).
        segments, asr_info = _subs.transcribe_audio(
            audio, quality=body.quality, vad=settings.whisper_vad,
            model_override=settings.whisper_model)
        detected_lang = asr_info.get("language", "unknown") or "unknown"
        engine_used = f"faster-whisper {asr_info.get('model', '')} (Local CPU)"
        recovered = int(asr_info.get("recovered") or 0)
        if recovered:
            engine_used += f" + vá {recovered} đoạn thoại bị VAD bỏ sót"
    except Exception as e:
        if wav_path.exists():
            wav_path.unlink(missing_ok=True)
        raise HTTPException(500, f"Lỗi nhận dạng giọng nói: {e}")
    finally:
        if wav_path.exists():
            wav_path.unlink(missing_ok=True)

    available = [{"code": c, "name": n} for c, n in TRANSLATE_LANG_CHOICES]
    tgt = (body.target_lang or "").strip().lower()
    translate_status = None
    if tgt in ("", "same"):
        translate_status = "original"
    elif not segments:
        translate_status = "empty"

    if not segments:
        return {"language": detected_lang, "engine_used": engine_used, "segments": [], "srt": "",
                "target_lang": tgt or detected_lang, "translate_status": translate_status,
                "available_target_langs": available, "audio_warning": None,
                "asr_model": asr_info.get("model", ""), "asr_recovered_cues": int(asr_info.get("recovered") or 0),
                "llm_used": "", "llm_model": ""}

    # 1.5. Sửa lỗi nhận dạng bằng model LLM của admin (nếu có) — sửa chính tả, thêm dấu câu,
    #      chuẩn hoá tên riêng. Không đổi mốc thời gian, không bỏ câu nào.
    # LLM cho sửa lời và dịch là hai lượt gọi độc lập.
    llm_info = _resolve_llm(db, body.llm_model) if body.use_llm else None
    llm_calls = 0
    subtitle_usage = None
    if llm_info and llm_info.get("price", 0) > 0:
        from .. import featurebilling
        try:
            subtitle_usage = featurebilling.reserve(db, user.id, "subtitle_transcribe",
                                                    model_id=llm_info["id"], units=2,
                                                    model_cost=float(llm_info["price"]))
        except HTTPException as exc:
            if exc.status_code == 402:
                llm_info = None
            else:
                raise
    llm_used = ""
    if llm_info:
        try:
            refined = _subs.refine_transcript(segments, llm_info["id"], llm_info["creds"])
            if refined:
                segments = refined
                llm_used = "refine"
                if llm_info.get("price", 0) > 0:
                    llm_calls += 1
                engine_used += f" + LLM sửa thoại ({llm_info['name']})"
        except Exception as e:
            logger.warning("[subtitle] refine failed: %s", e)

    # 2. Dịch sang ngôn ngữ đích nếu khác ngôn ngữ gốc.
    if tgt not in ("", "same") and translate_status is None:
        if tgt == detected_lang:
            translate_status = "same_language"
        else:
            texts = [s["text"] for s in segments]
            trans = None
            if llm_info:
                try:
                    trans = _subs.translate_segments(segments, detected_lang, tgt,
                                                    llm_info["id"], llm_info["creds"])
                except Exception as e:
                    logger.warning("[subtitle] llm translate failed: %s", e)
                    trans = None
            if trans:
                if llm_info:
                    engine_used += f" + LLM dịch ({llm_info['name']})"
                    translate_status = "ok_llm"
                    llm_used = f"{llm_used}+translate" if llm_used else "translate"
                    if llm_info.get("price", 0) > 0:
                        llm_calls += 1
                else:
                    engine_used += " + GoogleTranslate"
                    translate_status = "ok_google"
            if trans is None:
                trans = _translate_google(texts, detected_lang, tgt)
                if trans:
                    engine_used += " + GoogleTranslate"
                    translate_status = "ok_google"
            if trans is None:
                translate_status = "failed"
            else:
                for seg, txt in zip(segments, trans):
                    seg["translated"] = txt or seg["text"]
    if subtitle_usage is not None:
        from .. import featurebilling
        featurebilling.finish(db, subtitle_usage.id, success=llm_calls > 0,
                              actual_charge=round(float(llm_info["price"]) * llm_calls, 2))
        if llm_calls == 0:
            llm_info = None
            llm_used = ""

    # Build 3 dạng SRT: gốc / dịch / song ngữ (gốc trên, dịch dưới).
    # Xuống dòng theo ngân sách ký tự để phụ đề không tràn khung (đặc biệt video dọc 9:16).
    def _build_srt(lines_by_seg: list[str], max_lines: int = 2) -> str:
        out = []
        for i, (s, txt) in enumerate(zip(segments, lines_by_seg)):
            if not txt.strip():
                txt = s["text"]
            txt = _subs.wrap_subtitle(txt, max_lines=max_lines)
            out.append(f"{i+1}")
            out.append(f"{_format_srt_time(s['start'])} --> {_format_srt_time(s['end'])}")
            out.append(txt)
            out.append("")
        return "\n".join(out)

    srt_original = _build_srt([s["text"] for s in segments])
    has_translation = translate_status in ("ok", "ok_google", "ok_llm")
    srt_translated = _build_srt([s.get("translated", "") for s in segments]) if has_translation else ""
    # Song ngữ: mỗi ngôn ngữ 1 dòng để tổng vẫn ≤ 2 dòng/cue.
    srt_bilingual = _build_srt(
        [f"{_subs.wrap_subtitle(s['text'], max_lines=1)}\n"
         f"{_subs.wrap_subtitle(s.get('translated', ''), max_lines=1)}".strip()
         if has_translation else s["text"] for s in segments])

    mode = (body.subtitle_mode or "auto").strip().lower()
    if mode == "original":
        srt_content = srt_original
    elif mode == "translated":
        srt_content = srt_translated or srt_original
    elif mode == "bilingual":
        srt_content = srt_bilingual
    else:  # auto: ưu tiên dịch, không thì gốc
        srt_content = srt_translated if has_translation else srt_original

    # Cảnh báo khi decode audio ít hơn thời lượng container — file có thể bị cắt/hỏng
    audio_warning = None
    if container_seconds and container_seconds > 2 and container_seconds - pcm_seconds > 2:
        audio_warning = (f"Audio chỉ đọc được ~{pcm_seconds:.0f}s/{container_seconds:.0f}s video — "
                         "file có thể bị cắt/hỏng; thử tải lại từ nguồn gốc")

    log_activity(db, user.id, "video_transcribe", details={"video_url": body.video_url, "segments_count": len(segments),
                                                         "engine": engine_used, "target_lang": tgt or detected_lang,
                                                         "translate_status": translate_status,
                                                         "subtitle_mode": mode,
                                                         "audio_warning": audio_warning})

    return {
        "language": detected_lang,
        "engine_used": engine_used,
        "segments": segments,
        "srt": srt_content,
        "srt_original": srt_original,
        "srt_translated": srt_translated,
        "srt_bilingual": srt_bilingual,
        "subtitle_mode": mode,
        "target_lang": tgt or detected_lang,
        "translate_status": translate_status,
        "available_target_langs": available,
        "audio_warning": audio_warning,
        "asr_model": asr_info.get("model", ""),
        "asr_recovered_cues": int(asr_info.get("recovered") or 0),
        "llm_used": llm_used,
        "llm_model": llm_info["name"] if llm_info else "",
    }


def _abs_tikwm(url: str) -> str:
    return "https://www.tikwm.com" + url if url.startswith("/") else url


def _tikwm_query(url: str) -> dict | None:
    """Gọi TikWM API, trả về data nếu code==0, ngược lại None."""
    import httpx
    with httpx.Client(timeout=45, follow_redirects=True) as client:
        resp = client.post("https://www.tikwm.com/api/", data={"url": url})
        if resp.status_code != 200:
            return None
        body = resp.json()
        if body.get("code") != 0:
            return None
        return body.get("data") or None


def _download_tiktok_tikwm(url: str, dest_path: Path, job_id: str = "") -> dict | None:
    """Download TikTok/Douyin video không watermark, hoặc post ảnh (slides) qua TikWM.

    - Post video: lưu file mp4 vào dest_path, trả dict có `kind="video"`.
    - Post ảnh: tải từng ảnh vào outputs/<stem>_<i>.<ext>, trả dict có `kind="images"` + `images` (đường /media/...).
    - job_id: nếu có, ghi tiến độ từng byte vào DOWNLOAD_PROGRESS để UI poll được.
    """
    uid = None
    if job_id:
        prev = DOWNLOAD_PROGRESS.get(job_id, {})
        uid = prev.get("user_id")
    try:
        data = _tikwm_query(url)
        if not data:
            return None
        import httpx
        title = data.get("title") or ("TikTok Video" if data.get("play") else "TikTok Image")
        cover = data.get("cover") or data.get("origin_cover") or data.get("ai_dynamic_cover") or ""
        if isinstance(data.get("images"), list) and data["images"]:
            saved = []
            total = len(data["images"])
            with httpx.Client(timeout=60, follow_redirects=True) as client:
                for i, img_url in enumerate(data["images"]):
                    img_url = _abs_tikwm(str(img_url))
                    ext = Path(img_url.split("?", 1)[0]).suffix.lower()
                    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
                        ext = ".jpg"
                    img_path = dest_path.with_name(f"{dest_path.stem}_{i}{ext}")
                    try:
                        r = client.get(img_url)
                        r.raise_for_status()
                        img_path.write_bytes(r.content)
                        saved.append(url_for(img_path))
                        _bump_progress(job_id, uid, i + 1, total)
                    except Exception as e:
                        logger.warning("TikWM image %s failed: %s", img_url, e)
            if not saved:
                return None
            return {"kind": "images", "title": title, "duration": 0, "thumbnail": cover, "images": saved}

        stream_url = data.get("play") or data.get("wmplay")
        if not stream_url:
            return None
        with httpx.Client(timeout=180, follow_redirects=True) as client:
            with client.stream("GET", _abs_tikwm(str(stream_url))) as v_res:
                v_res.raise_for_status()
                total = int(v_res.headers.get("content-length") or 0)
                done = 0
                last_t, last_done = time.time(), 0
                speed = None
                with dest_path.open("wb") as f:
                    for chunk in v_res.iter_bytes(1024 * 256):
                        f.write(chunk)
                        done += len(chunk)
                        now = time.time()
                        dt = now - last_t
                        if dt >= 0.5:
                            speed = (done - last_done) / dt
                            last_t, last_done = now, done
                        if job_id and total > 0:
                            eta = int((total - done) / speed) if speed and speed > 0 else None
                            DOWNLOAD_PROGRESS[job_id] = {"percent": min(98, int(done / total * 97)),
                                                         "status": "downloading", "user_id": uid,
                                                         "updated_at": time.time(), "eta": eta,
                                                         "speed": (float(speed) if speed else None),
                                                         "total_bytes": total, "downloaded_bytes": done}
        return {"kind": "video", "title": title, "duration": data.get("duration") or 0,
                "thumbnail": cover}
    except Exception as e:
        logger.warning("TikTok download failed: %s", e)
    return None


@router.post("/download")
def download_social_video(body: DownloadIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Download video from YouTube, TikTok, Facebook, Reels, etc. with multi-engine fallback."""
    _udir(user).mkdir(parents=True, exist_ok=True)
    out_id = f"dl_{user.id}_{secrets.token_hex(6)}"
    dest_path = _udir(user) / f"{out_id}.mp4"

    url_str = body.url.strip()
    job_id = (body.job_id or "").strip()
    if job_id:
        _prune_progress()
        DOWNLOAD_PROGRESS[job_id] = {"percent": 0, "status": "checking", "user_id": user.id, "updated_at": time.time()}

    # 1. Specialized TikTok & Douyin direct bypass
    if "tiktok.com" in url_str.lower() or "douyin.com" in url_str.lower():
        tik_info = _download_tiktok_tikwm(url_str, dest_path, job_id=job_id)
        if tik_info and tik_info.get("kind") == "images":
            log_activity(db, user.id, "video_download", details={"url": url_str, "title": tik_info["title"],
                                                                 "images": tik_info["images"], "source": "tikwm"})
            _set_progress_status(job_id, user.id, 100, "done")
            return {"images": tik_info["images"], "title": tik_info["title"], "duration": 0,
                    "thumbnail": tik_info["thumbnail"], "media_type": "images"}
        if tik_info and tik_info.get("kind") == "video" and dest_path.exists() and dest_path.stat().st_size > 1000:
            video_url = url_for(dest_path)
            log_activity(db, user.id, "video_download", details={"url": url_str, "title": tik_info["title"], "video_url": video_url, "source": "tikwm"})
            _set_progress_status(job_id, user.id, 100, "done")
            return {
                "video_url": video_url,
                "title": tik_info["title"],
                "duration": tik_info["duration"],
                "thumbnail": tik_info["thumbnail"],
                "media_type": "video",
            }

    # 2. Universal yt-dlp with updated engine & browser headers
    try:
        import yt_dlp
    except ImportError:
        raise HTTPException(500, "yt-dlp chưa được cài đặt")

    out_tmpl = str(_udir(user) / f"{out_id}.%(ext)s")

    ydl_opts = {
        "outtmpl": out_tmpl,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
            "Sec-Fetch-Mode": "navigate",
        },
        "max_filesize": 200 * 1024 * 1024,  # 200MB
        "retries": 3,
        "fragment_retries": 3,
    }
    # Kiểm tra dung lượng TRƯỚC khi tải — vượt giới hạn thì báo "Không hỗ trợ" ngay (không tải lỗi giữa chừng)
    cap_mb = settings.download_max_mb
    meta_opts = {k: v for k, v in ydl_opts.items() if k not in ("outtmpl", "merge_output_format", "retries", "fragment_retries")}
    meta_opts["noplaylist"] = True
    too_big = _size_error(url_str, meta_opts, cap_mb)
    if too_big:
        _set_progress_status(job_id, user.id, 0, "rejected")
        raise HTTPException(422, too_big)
    if job_id:
        DOWNLOAD_PROGRESS[job_id].update({"status": "downloading", "updated_at": time.time()})
    if job_id:
        ydl_opts["progress_hooks"] = [_dl_progress(job_id, 1)]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url_str, download=True)
            filename = ydl.prepare_filename(info)
            final_path = Path(filename).with_suffix(".mp4")
            if not final_path.exists():
                matches = list(_udir(user).glob(f"{out_id}.*"))
                if matches:
                    final_path = matches[0]
                else:
                    raise HTTPException(502, "Không tìm thấy file video sau khi tải")

            _set_progress_status(job_id, user.id, 99, "transcoding")
            final_path = _ensure_web_mp4(final_path)
            video_url = url_for(final_path)
            title = info.get("title") or "Video tải về"
            duration = info.get("duration") or 0
            thumb = info.get("thumbnail") or ""

            log_activity(db, user.id, "video_download", details={"url": url_str, "title": title, "video_url": video_url, "source": "yt-dlp"})
            _set_progress_status(job_id, user.id, 100, "done")

            return {
                "video_url": video_url,
                "title": title,
                "duration": duration,
                "thumbnail": thumb,
                "media_type": "video",
            }
    except Exception as e:
        _set_progress_status(job_id, user.id, 0, "failed")
        raise HTTPException(502, f"Không thể tải video từ link này: {e}")


# ==================== PLAYLIST / CHANNEL RESOLVE ====================

class ResolveIn(BaseModel):
    url: str = Field(min_length=5)


class ResolvedItem(BaseModel):
    id: str
    title: str
    url: str
    thumbnail: str = ""
    duration: int = 0
    like_count: int = 0
    comment_count: int = 0
    view_count: int = 0
    available_qualities: list[str] = []


class ResolveOut(BaseModel):
    items: list[ResolvedItem]
    total: int
    is_playlist: bool


class BatchDownloadItem(BaseModel):
    url: str
    title: str = ""
    quality: str = "720"   # best | 1080 | 720 | 480 | audio


class BatchDownloadIn(BaseModel):
    items: list[BatchDownloadItem] = Field(default_factory=list)
    job_id: str = ""


def _format_selector(quality: str) -> str:
    """Chuyển chất lượng người dùng chọn thành format string của yt-dlp."""
    q = (quality or "720").strip().lower()
    if q == "best":
        return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
    if q == "audio":
        return "bestaudio[ext=m4a]/bestaudio/bestaudio"
    # 1080 / 720 / 480 -> height <= n
    num = "".join(ch for ch in q if ch.isdigit())
    if not num:
        num = "720"
    return (
        f"bestvideo[height<={num}][ext=mp4]+bestaudio[ext=m4a]/"
        f"best[height<={num}][ext=mp4]/best[height<={num}]/best"
    )


def _probe_dimensions(path: Path) -> tuple[int, int] | None:
    """Kích thước video (width, height) qua ffprobe; None nếu không đọc được."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        parts = r.stdout.strip().split(",")
        if len(parts) == 2:
            return int(parts[0]), int(parts[1])
    except Exception as e:
        logger.warning("ffprobe dimensions failed for %s: %s", path, e)
    return None


def _probe_codecs(path: Path) -> tuple[str, str]:
    """Trả về (video_codec, audio_codec) của file; '' nếu không có stream."""
    try:
        v = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        vc = (v.stdout.strip().splitlines() or [""])[0].strip()
        a = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        ac = (a.stdout.strip().splitlines() or [""])[0].strip()
        return vc, ac
    except Exception as e:
        logger.warning("ffprobe codecs failed for %s: %s", path, e)
        return "", ""


def _ensure_web_mp4(path: Path) -> Path:
    """Đảm bảo file mp4 có H.264 video + AAC audio để trình duyệt phát được (xem trước).
    Nếu codec không tương thích, transcode bằng ffmpeg. Trả về path gốc (đã ghi đè)."""
    vc, ac = _probe_codecs(path)
    if vc in ("h264", "avc1") and ac in ("aac", ""):
        return path
    tmp = path.with_name(path.stem + ".web.mp4")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(path), "-c:v", "libx264", "-preset", "fast",
             "-crf", "23", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
             str(tmp)],
            capture_output=True, text=True, timeout=900, check=True,
        )
        if tmp.exists() and tmp.stat().st_size > 0:
            os.replace(tmp, path)
    except Exception as e:
        logger.warning("Web mp4 transcode failed for %s: %s", path, e)
        try:
            tmp.unlink(missing_ok=True)
        except Exception as e2:
            logger.warning("Cannot remove temp file %s: %s", tmp, e2)
    return path


def _selected_size(info: dict) -> int | None:
    """Ước lượng dung lượng file sẽ tải; None nếu không biết.

    Ưu tiên filesize thật từ metadata; FB/DASH không có → ước lượng từ bitrate (tbr) × duration.
    """
    duration = info.get("duration") or 0

    def f_size(f: dict):
        s = f.get("filesize") or f.get("filesize_approx")
        if s:
            return int(s)
        tbr = f.get("tbr")
        if tbr and duration:
            return int(float(tbr) * 1000 * float(duration) / 8)
        return None

    rf = info.get("requested_formats") or []
    sizes = [f_size(f) for f in rf] if rf else [f_size(info)]
    sizes = [s for s in sizes if s]
    return sum(sizes) if sizes else None


def _metadata_or_none(url_str: str, ydl_opts: dict):
    """Metadata nhanh (không tải file). Lỗi mạng → None → vẫn cho tải (size check là best-effort)."""
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url_str, download=False)
    except Exception as e:
        logger.warning("[download] metadata check failed for %s: %s", url_str, e)
        return None


def _size_error(url_str: str, ydl_opts: dict, cap_mb: int) -> str | None:
    """Nếu dung lượng ước lượng VƯỢT cap_mb → trả message lỗi; không xác định được → None."""
    info = _metadata_or_none(url_str, ydl_opts)
    if info is None:
        return None
    size = _selected_size(info)
    if size is None:
        return None
    mb = size / (1024 * 1024)
    if mb > cap_mb:
        return f"Không hỗ trợ: video ~{mb:.0f}MB vượt giới hạn {cap_mb}MB (tăng DOWNLOAD_MAX_MB nếu muốn tải)"
    return None


def _extract_flat_entries(info: dict) -> list[dict]:
    """Lấy danh sách entries từ info của yt-dlp (playlist/channel hoặc video đơn)."""
    entries: list[dict] = []
    if info.get("_type") == "playlist" and info.get("entries"):
        for e in info["entries"]:
            if not e:
                continue
            entries.append({
                "id": e.get("id") or "",
                "title": e.get("title") or "",
                "url": e.get("url") or e.get("webpage_url") or "",
                "thumbnail": e.get("thumbnail") or "",
                "duration": int(e.get("duration") or 0),
                "like_count": int(e.get("like_count") or 0),
                "comment_count": int(e.get("comment_count") or 0),
                "view_count": int(e.get("view_count") or 0),
                "available_qualities": ["best", "1080", "720", "480", "audio"],
            })
    else:
        entries.append({
            "id": info.get("id") or "",
            "title": info.get("title") or "",
            "url": info.get("webpage_url") or info.get("url") or "",
            "thumbnail": info.get("thumbnail") or "",
            "duration": int(info.get("duration") or 0),
            "like_count": int(info.get("like_count") or 0),
            "comment_count": int(info.get("comment_count") or 0),
            "view_count": int(info.get("view_count") or 0),
            "available_qualities": ["best", "1080", "720", "480", "audio"],
        })
    return entries


@router.post("/resolve", response_model=ResolveOut)
def resolve_social_url(body: ResolveIn, user: User = Depends(current_user)):
    """Phân tích link mạng xã hội: video đơn trả 1 mục, kênh/trang/playlist trả toàn bộ danh sách.
    Chỉ lấy metadata (không tải file), để người dùng chọn muốn tải cái nào."""
    try:
        import yt_dlp
    except ImportError:
        raise HTTPException(500, "yt-dlp chưa được cài đặt")

    url_str = body.url.strip()
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,  # không tải, chỉ liệt kê metadata nhanh
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
        },
    }

    last_err = None
    for attempt in range(5):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url_str, download=False)
            last_err = None
            break
        except Exception as e:
            last_err = e
            time.sleep(2)
    if last_err is not None:
        raise HTTPException(502, f"Không phân tích được link này: {last_err}")

    entries = _extract_flat_entries(info)
    # Link video đơn (FB Reel, IG post...): extract_flat bỏ trống title/thumbnail/duration —
    # lấy metadata đầy đủ để UI hiển thị đúng (title, thumbnail dọc/ngang, thời lượng).
    if len(entries) == 1 and not entries[0].get("title"):
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True,
                                   "http_headers": ydl_opts["http_headers"]}) as ydl:
                full = ydl.extract_info(url_str, download=False)
            if full:
                entries[0] = {**entries[0],
                              "title": full.get("title") or entries[0].get("title") or "",
                              "url": full.get("webpage_url") or entries[0].get("url") or "",
                              "thumbnail": full.get("thumbnail") or entries[0].get("thumbnail") or "",
                              "duration": int(full.get("duration") or entries[0].get("duration") or 0),
                              "like_count": int(full.get("like_count") or 0) or entries[0].get("like_count") or 0,
                              "comment_count": int(full.get("comment_count") or 0) or entries[0].get("comment_count") or 0,
                              "view_count": int(full.get("view_count") or 0) or entries[0].get("view_count") or 0}
        except Exception as e:
            logger.warning("[resolve] full metadata fallback failed for %s: %s", url_str, e)
    items = [ResolvedItem(**e) for e in entries]
    return ResolveOut(items=items, total=len(items), is_playlist=info.get("_type") == "playlist")


@router.post("/batch-download")
def batch_download_social(body: BatchDownloadIn, user: User = Depends(current_user),
                          db: Session = Depends(get_db)):
    """Tải nhiều video/ảnh cùng lúc theo chất lượng người dùng chọn. Trả về danh sách file_url."""
    if not body.items:
        raise HTTPException(422, "Danh sách tải trống")

    results: list[dict] = []
    _udir(user).mkdir(parents=True, exist_ok=True)

    job_id = (body.job_id or "").strip()
    hook = None
    if job_id:
        _prune_progress()
        DOWNLOAD_PROGRESS[job_id] = {"percent": 0, "status": "starting", "user_id": user.id, "updated_at": time.time()}
        hook = _dl_progress(job_id, len(body.items))
    completed_count = {"n": 0}
    total_items = len(body.items)

    try:
        import yt_dlp
    except ImportError:
        raise HTTPException(500, "yt-dlp chưa được cài đặt")

    for item in body.items:
        url_str = (item.url or "").strip()
        if not url_str:
            continue
        out_id = f"batch_{user.id}_{secrets.token_hex(6)}"
        out_tmpl = str(_udir(user) / f"{out_id}.%(ext)s")
        dest_path = _udir(user) / f"{out_id}.mp4"

        # TikTok & Douyin: ưu tiên TikWM (không watermark + post ảnh), fallback yt-dlp
        if "tiktok.com" in url_str.lower() or "douyin.com" in url_str.lower():
            tik = _download_tiktok_tikwm(url_str, dest_path, job_id=job_id)
            if tik and tik.get("kind") == "images":
                results.append({"url": url_str, "title": tik["title"] or item.title, "status": "done",
                                "images": tik["images"], "thumbnail": tik["thumbnail"],
                                "duration": 0, "quality": item.quality, "media_type": "images"})
                completed_count["n"] += 1
                _bump_progress(job_id, user.id, completed_count["n"], total_items)
                continue
            if tik and tik.get("kind") == "video" and dest_path.exists() and dest_path.stat().st_size > 1000:
                video_url = url_for(dest_path)
                results.append({"url": url_str, "title": tik["title"] or item.title, "status": "done",
                                "video_url": video_url, "thumbnail": tik["thumbnail"],
                                "duration": tik["duration"], "quality": item.quality, "media_type": "video"})
                completed_count["n"] += 1
                _bump_progress(job_id, user.id, completed_count["n"], total_items)
                continue

        cap_mb = settings.download_max_mb
        meta_opts = {"quiet": True, "no_warnings": True, "noplaylist": True,
                     "format": _format_selector(item.quality),
                     "http_headers": {
                         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
                         "Accept-Language": "en-US,en;q=0.9,vi;q=0.8"}}
        too_big = _size_error(url_str, meta_opts, cap_mb)
        if too_big:
            results.append({"url": url_str, "title": item.title, "status": "failed", "error": too_big})
            completed_count["n"] += 1
            _bump_progress(job_id, user.id, completed_count["n"], total_items)
            continue

        ydl_opts = {
            "outtmpl": out_tmpl,
            "format": _format_selector(item.quality),
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
            },
            "max_filesize": 500 * 1024 * 1024,  # 500MB cho batch
            "retries": 3,
            "fragment_retries": 3,
        }
        if job_id and hook is not None:
            ydl_opts["progress_hooks"] = [hook]

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url_str, download=True)
            filename = ydl.prepare_filename(info)
            final_path = Path(filename)
            if not final_path.exists():
                # tìm file khớp out_id
                matches = list(_udir(user).glob(f"{out_id}.*"))
                final_path = matches[0] if matches else None
            if not final_path or not final_path.exists():
                results.append({"url": url_str, "title": item.title, "status": "failed",
                                "error": "Không tìm thấy file sau khi tải"})
                continue

            final_path = _ensure_web_mp4(final_path)
            video_url = url_for(final_path)
            log_activity(db, user.id, "video_batch_download", details={
                "url": url_str, "title": item.title, "quality": item.quality,
                "video_url": video_url, "source": "yt-dlp",
            })
            results.append({
                "url": url_str,
                "title": info.get("title") or item.title or "Video tải về",
                "status": "done",
                "video_url": video_url,
                "duration": info.get("duration") or 0,
                "thumbnail": info.get("thumbnail") or "",
                "quality": item.quality,
                "media_type": "video",
            })
            completed_count["n"] += 1
            _bump_progress(job_id, user.id, completed_count["n"], total_items)
        except Exception as e:
            results.append({"url": url_str, "title": item.title, "status": "failed",
                            "error": str(e)[:300]})

    if job_id:
        DOWNLOAD_PROGRESS[job_id] = {"percent": 100, "status": "done", "user_id": user.id,
                                     "updated_at": time.time()}
    return {"results": results, "total": len(results),
            "success": sum(1 for r in results if r["status"] == "done")}


@router.get("/preview")
def preview_video(url: str, user: User = Depends(current_user)):
    """Tải video về server tạm thời, chuyển sang H.264/AAC để xem trước trên tool (local /media URL)."""
    try:
        import yt_dlp
    except ImportError:
        raise HTTPException(500, "yt-dlp chưa được cài đặt")
    url_str = (url or "").strip()
    if not url_str:
        raise HTTPException(400, "Thiếu url")
    _udir(user).mkdir(parents=True, exist_ok=True)
    out_id = f"preview_{user.id}_{secrets.token_hex(6)}"
    out_tmpl = str(_udir(user) / f"{out_id}.%(ext)s")
    # TikTok & Douyin: xem trước qua TikWM (yt-dlp hay bị chặn)
    if "tiktok.com" in url_str.lower() or "douyin.com" in url_str.lower():
        tik = _download_tiktok_tikwm(url_str, _udir(user) / f"{out_id}.mp4")
        if tik and tik.get("kind") == "video":
            final_path = _udir(user) / f"{out_id}.mp4"
            if final_path.exists() and final_path.stat().st_size > 1000:
                final_path = _ensure_web_mp4(final_path)
                return {"video_url": url_for(final_path), "title": tik["title"],
                        "duration": tik["duration"], "thumbnail": tik["thumbnail"]}
    ydl_opts = {
        "outtmpl": out_tmpl,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
        },
        "max_filesize": 300 * 1024 * 1024,  # 300MB cho preview
        "retries": 3,
        "fragment_retries": 3,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url_str, download=True)
        filename = ydl.prepare_filename(info)
        final_path = Path(filename)
        if not final_path.exists():
            matches = list(_udir(user).glob(f"{out_id}.*"))
            final_path = matches[0] if matches else None
        if not final_path or not final_path.exists():
            raise HTTPException(502, "Không tải được video để xem trước")
        final_path = _ensure_web_mp4(final_path)
        video_url = url_for(final_path)
        return {
            "video_url": video_url,
            "title": info.get("title") or "Video xem trước",
            "duration": info.get("duration") or 0,
            "thumbnail": info.get("thumbnail") or "",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Không lấy được link xem trước: {e}")


@router.get("/download-progress/{job_id}")
def download_progress(job_id: str, user: User = Depends(current_user)):
    """Trả về tiến độ tải theo job_id (dùng cho progress bar)."""
    data = DOWNLOAD_PROGRESS.get(job_id, {"percent": 0, "status": "unknown"})
    if data.get("user_id") is not None and data.get("user_id") != user.id:
        raise HTTPException(403, "Không có quyền xem tiến độ này")
    return {"job_id": job_id, "percent": data.get("percent", 0), "status": data.get("status", "unknown"),
            "eta": data.get("eta"), "speed": data.get("speed"),
            "total_bytes": data.get("total_bytes"), "downloaded_bytes": data.get("downloaded_bytes")}




def _has_audio(path: Path) -> bool:
    """True nếu video có ít nhất 1 audio stream."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0",
                            "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        return bool(r.stdout.strip())
    except Exception:
        return False


def _render_dub(srt_text: str, tts_voice: str, work_dir: Path, emotion_key: str = ""):
    """Tạo file MP3 TTS cho từng câu thoại SRT. Trả về [(delay_ms, voice_index, path)]."""
    segs = _parse_srt(srt_text)
    if not segs:
        raise HTTPException(422, "SRT không hợp lệ — không thể lồng tiếng")
    try:
        from .. import tts as tts_mod
    except Exception as e:
        raise HTTPException(500, f"Không tải được module TTS: {e}")
    # Cảm xúc đọc cho edge-tts (rate/pitch/volume) — áp dụng chung cho mọi câu nếu user chọn
    rate = pitch = volume = None
    emotion_key = (emotion_key or "").strip().lower()
    if emotion_key:
        try:
            rate, pitch, volume = tts_mod.emotion_params(emotion_key)
        except Exception as e:
            logger.warning("[dub] emotion params error for %s: %s", emotion_key, e)
    work_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for idx, (t0, _end, txt) in enumerate(segs):
        txt = (txt or "").strip()
        # Song ngữ (gốc + dịch): lồng tiếng chỉ đọc DÒNG CUỐI (bản dịch)
        if "\n" in txt:
            txt = txt.splitlines()[-1].strip()
        if not txt:
            continue
        dest = work_dir / f"seg_{idx:04d}.mp3"
        try:
            tts_mod.gen_tts(txt, dest, voice=tts_voice, timeout=120,
                            rate=rate, pitch=pitch, volume=volume)
        except Exception as e:
            logger.warning("Dub TTS segment %d failed: %s", idx, e)
            continue
        if dest.exists() and dest.stat().st_size > 100:
            files.append((int(max(0.0, t0) * 1000), idx, dest))
    if not files:
        raise HTTPException(500, "Không tạo được giọng lồng tiếng — TTS thất bại cho mọi câu thoại (thử lại hoặc đổi engine/voice khác)")
    return files


@router.post("/process")
def process_sub_and_blur(body: ProcessIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Burn subtitles and/or apply blur area onto video with FFmpeg."""
    src = resolve(body.video_url, user.id)
    if not src or not src.exists():
        raise HTTPException(404, "Không tìm thấy video gốc")

    out_file = _udir(user) / f"proc_{user.id}_{secrets.token_hex(8)}.mp4"
    srt_file = _udir(user) / f"sub_{secrets.token_hex(8)}.srt"
    work_dir = _udir(user) / f"dub_{secrets.token_hex(6)}"
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        fc_parts = []

        # 1. Blur filter (or pass-through null)
        if body.blur_region:
            bx = int(body.blur_region.get("x", 0))
            by = int(body.blur_region.get("y", 0))
            bw = int(body.blur_region.get("width", 100))
            bh = int(body.blur_region.get("height", 60))
            if bw <= 0 or bh <= 0:
                raise HTTPException(422, f"Vùng làm mờ không hợp lệ: width={bw}, height={bh} (phải > 0)")
            bx, by = max(0, bx), max(0, by)
            fc_parts.append("[0:v]split[vmain][vcrop]")
            fc_parts.append(f"[vcrop]crop={bw}:{bh}:{bx}:{by},boxblur=15:5[vblur]")
            fc_parts.append(f"[vmain][vblur]overlay={bx}:{by}[v1]")
            vcur = "v1"
        else:
            fc_parts.append("[0:v]null[v1]")
            vcur = "v1"

        # 2. Subtitle filter (or pass-through)
        if body.srt_content and body.srt_content.strip():
            dims = _probe_dimensions(src) or (1920, 1080)
            ass_path = srt_file.with_suffix(".ass")
            _srt_to_ass(body.srt_content, ass_path,
                        fsize=(body.sub_font_size or 18),
                        position=body.sub_position,
                        width=dims[0], height=dims[1])

            # Dùng tên file tương đối + cwd — tránh toàn bộ vấn đề escape đường dẫn Windows (C\:/)
            sub_filter = f"ass={ass_path.name}"
            fc_parts.append(f"[{vcur}]{sub_filter}[vout]")
        else:
            fc_parts.append(f"[{vcur}]null[vout]")

        tts_files = []
        dubbed = False
        src_has_audio = _has_audio(src)

        if (body.tts_voice or "").strip():
            if not (body.srt_content and body.srt_content.strip()):
                raise HTTPException(422, "Lồng tiếng TTS cần nội dung phụ đề (SRT)")
            tts_voice = (body.tts_voice or "").strip()
            if tts_voice == "auto":   # chọn giọng mặc định khi user chọn "Tự động"
                tts_voice = "vi-VN-HoaiMyNeural"
            tts_files = _render_dub(body.srt_content, tts_voice, work_dir, emotion_key=(body.tts_emotion or ""))
            for j, (d_ms, _idx, fpath) in enumerate(tts_files):
                fc_parts.append(f"[{j+1}:a]aresample=44100,adelay={d_ms}|{d_ms}[aa{j}]")
            mix_in = "".join(f"[aa{j}]" for j in range(len(tts_files)))
            fc_parts.append(f"{mix_in}amix=inputs={len(tts_files)}:normalize=0[dub]")
            src_vol = max(0.0, min(1.0, float(body.src_volume) if body.src_volume is not None else 1.0)) if body.keep_original_audio else 0.0
            if src_has_audio:
                fc_parts.append(f"[0:a]volume={src_vol}[orig]")
                fc_parts.append(f"[orig][dub]amix=inputs=2:normalize=0[aout]")
            else:
                fc_parts.append(f"[dub]anull[aout]")
            dubbed = True
        elif src_has_audio:
            fc_parts.append("[0:a]anull[aout]")

        cmd = ["ffmpeg", "-y", "-i", str(src)]
        for _d_ms, _idx, fpath in tts_files:
            cmd.extend(["-i", str(fpath)])
        cmd.extend(["-filter_complex", ";".join(fc_parts),
                    "-map", "[vout]", "-c:v", "libx264", "-preset", "fast", "-crf", "22"])
        if src_has_audio or tts_files:
            cmd.extend(["-map", "[aout]", "-c:a", "aac", "-b:a", "128k"])
        cmd.append(str(out_file))

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600,
                            cwd=_udir(user))
        if res.returncode != 0:
            err = res.stderr.decode("utf-8", errors="ignore")
            raise HTTPException(500, f"FFmpeg lỗi: {err[-500:]}")

        output_url = url_for(out_file)
        log_activity(db, user.id, "video_process", details={"output_url": output_url, "has_sub": bool(body.srt_content), "has_blur": bool(body.blur_region), "dubbed": dubbed, "tts_voice": body.tts_voice or None})

        return {
            "output_video_url": output_url,
            "success": True,
            "dubbed": dubbed,
        }
    finally:
        if srt_file.exists():
            srt_file.unlink(missing_ok=True)
        ass_file = srt_file.with_suffix(".ass")
        if ass_file.exists():
            ass_file.unlink(missing_ok=True)
        shutil.rmtree(work_dir, ignore_errors=True)

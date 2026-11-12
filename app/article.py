"""Bài viết (link) → video 60 giây.

Luồng: tải nội dung bài viết → LLM viết lời dẫn theo cảnh (hook → thân bài → CTA)
→ ảnh minh hoạ từng cảnh (model ảnh admin đang bật) → TTS lời dẫn (edge-tts)
→ ffmpeg dựng clip Ken Burns + ghép + chèn phụ đề → 1 video hoàn chỉnh.

Không dùng model video → chi phí thấp (1 lượt LLM + N ảnh), phù hợp nội dung tin tức,
tài chính, sức khoẻ, giáo dục… (nhóm "bài viết → video" của đối thủ).
"""
from __future__ import annotations

import html as html_mod
import json
import logging
import re
import secrets
import subprocess
import threading
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import httpx

from . import adminmodels, ai, credits, pricing
from .db import SessionLocal
from .media import url_for, user_outputs_dir
from . import tts as tts_mod
from . import vilao_image
from . import minimax

logger = logging.getLogger(__name__)

_MAX_ARTICLE_CHARS = 24_000
_MAX_SCENES = 12
_MIN_SCENE_SECONDS = 3
_MAX_SCENE_SECONDS = 15


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Lấy nội dung bài viết
# ---------------------------------------------------------------------------
class _TextExtractor(HTMLParser):
    """Bóc text từ HTML, bỏ script/style/nav/footer và các khối điều hướng."""

    _SKIP = {"script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg", "iframe"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []
        self.title = ""
        self._in_title = False
        self._in_h1 = False
        self.h1 = ""

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "h1" and not self.h1:
            self._in_h1 = True
        elif tag in ("p", "br", "div", "li", "h2", "h3", "h4", "tr"):
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._skip_depth:
            return
        if self._in_h1:
            self.h1 += data
        text = data.strip()
        if text:
            self._parts.append(text + "\n")

    def text(self) -> str:
        raw = "".join(self._parts)
        raw = re.sub(r"[ \t ]+", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        lines = [ln.strip() for ln in raw.splitlines()]
        return "\n".join(ln for ln in lines if len(ln) > 1).strip()


def _clean_title(raw: str, fallback: str = "") -> str:
    t = html_mod.unescape(re.sub(r"\s+", " ", raw or "")).strip()
    return (t or fallback)[:200]


def fetch_article(url: str) -> dict:
    """Tải trang và trả {"title", "text", "url"}. Ném ValueError khi không lấy được nội dung."""
    url = (url or "").strip()
    if not re.match(r"^https?://", url, re.I):
        raise ValueError("Link bài viết phải bắt đầu bằng http:// hoặc https://")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                             "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
               "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.7"}
    try:
        with httpx.Client(timeout=25, follow_redirects=True, headers=headers) as client:
            r = client.get(url)
    except httpx.HTTPError as e:
        raise ValueError(f"Không tải được bài viết: {e}") from e
    if r.status_code >= 400:
        raise ValueError(f"Trang trả về HTTP {r.status_code} — không đọc được nội dung")
    ctype = (r.headers.get("content-type") or "").lower()
    if ctype and "html" not in ctype and "text" not in ctype:
        raise ValueError("Link này không phải trang bài viết (không phải HTML)")

    parser = _TextExtractor()
    try:
        parser.feed(r.text)
    except Exception as e:  # HTML hỏng vẫn dùng phần đã bóc được
        logger.warning("[article] parse lỗi %s: %s", url, e)
    text = parser.text()
    if len(text) < 400:
        raise ValueError("Không tìm thấy đủ nội dung bài viết (trang có thể chặn hoặc chỉ có JavaScript) — "
                         "bạn có thể dán trực tiếp nội dung bài viết vào ô bên dưới.")
    title = _clean_title(parser.title or parser.h1 or url)
    return {"title": title, "text": text[:_MAX_ARTICLE_CHARS], "url": url}


# ---------------------------------------------------------------------------
# Viết lời dẫn bằng LLM
# ---------------------------------------------------------------------------
_SCHEMA = """{
  "title": "tiêu đề video ngắn gọn",
  "summary": "1 câu tóm tắt nội dung",
  "scenes": [
    {
      "stt": 1,
      "thời_lượng_giây": 8,
      "thoại": "lời dẫn đọc thành tiếng cho cảnh này",
      "hành_động": "mô tả hình ảnh đang diễn ra",
      "biểu_cảm": "<một tag cảm xúc>",
      "image_prompt": "detailed English prompt for the image model"
    }
  ]
}"""

_EMOTIONS = ("vui vẻ | hào hứng | phấn khích | lạc quan | tự tin | nghiêm túc | bình thường | bình thản | "
             "ngọt ngào | cảm động | cảm thông | buồn bã | thất vọng | tức giận | sợ hãi | ngạc nhiên | sốc | "
             "thì thầm | thông thái | cao hứng")


def build_script(title: str, text: str, *, model_llm: str, creds: dict | None,
                 duration: int, language: str) -> dict:
    """LLM viết lời dẫn theo cảnh từ nội dung bài viết."""
    lang = "en" if str(language).lower().startswith("en") else "vi"
    spoken = "tiếng Việt" if lang == "vi" else "English"
    scene_target = max(3, min(_MAX_SCENES, round(duration / 8)))
    sys_prompt = (
        "You turn a written article into a short narrated video script. "
        "Return pure JSON only (no markdown, no explanation).\n"
        f"Mandatory JSON schema:\n{_SCHEMA}\n"
        "Rules:\n"
        f"- Exactly {scene_target} scenes and the total of thời_lượng_giây equals {duration} seconds "
        f"(each scene {_MIN_SCENE_SECONDS}-{_MAX_SCENE_SECONDS} seconds).\n"
        "- Scene 1 is a HOOK: a surprising fact or question that stops the scroll in the first 3 seconds.\n"
        "- Middle scenes explain the article's key points in order, one idea per scene.\n"
        "- The final scene is a short conclusion + call to action (follow/save/share).\n"
        f'- "thoại" is the narration actually spoken out loud, in {spoken}, natural spoken language '
        f"(about 20-30 words per scene, no emojis, no hashtags, no on-screen text).\n"
        "- Never invent facts, numbers or quotes that are not in the article. If data is missing, stay general.\n"
        f"- biểu_cảm MUST be exactly one of: {_EMOTIONS}.\n"
        '- "image_prompt" is a detailed ENGLISH prompt for an image model: specific subject, composition, '
        "lighting, mood, photorealistic, no text/captions/watermarks in the image.\n"
        "- Every scene must be visually different from the previous one.\n"
    )
    user_msg = f"Article title: {title}\n\nArticle content:\n{text[:12000]}\n"
    last_error = ""
    for _ in range(2):
        try:
            msg = ai.chat((creds or {}).get("model_name") or model_llm, [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_msg},
            ], json_mode=True, timeout=120,
                base_url=(creds or {}).get("base_url"),
                api_key=(creds or {}).get("api_key"))
            raw = (msg.get("content") or "").strip()
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if not m:
                raise ValueError("LLM không trả về JSON hợp lệ")
            data = json.loads(m.group(0))
            scenes_in = data.get("scenes") or data.get("các_cảnh") or []
            if not scenes_in:
                raise ValueError("Kịch bản không có cảnh nào")
            break
        except Exception as e:  # noqa: BLE001
            last_error = str(e)
            scenes_in = []
    if not scenes_in:
        raise ValueError(f"Không tạo được kịch bản từ bài viết: {last_error}")

    scenes = []
    for i, s in enumerate(scenes_in[:_MAX_SCENES]):
        try:
            dur = int(s.get("thời_lượng_giây") or 0)
        except (TypeError, ValueError):
            dur = 0
        dur = max(_MIN_SCENE_SECONDS, min(dur or 8, _MAX_SCENE_SECONDS))
        line = str(s.get("thoại") or "").strip()
        if not line:
            continue
        scenes.append({
            "stt": len(scenes) + 1,
            "thời_lượng_giây": dur,
            "thoại": line,
            "hành_động": str(s.get("hành_động") or "").strip(),
            "biểu_cảm": str(s.get("biểu_cảm") or "thông thái").strip(),
            "image_prompt": str(s.get("image_prompt") or "").strip(),
        })
    if not scenes:
        raise ValueError("Kịch bản không có lời dẫn nào để đọc")
    return {
        "title": _clean_title(str(data.get("title") or title)),
        "summary": str(data.get("summary") or "").strip(),
        "scenes": scenes,
    }


# ---------------------------------------------------------------------------
# Job store (in-memory) + render
# ---------------------------------------------------------------------------
def _video_price(model_video: str, db) -> float:
    """Giá 1 request video (Veo/omni-flash… tính theo clip, không theo giây)."""
    if not model_video:
        return 0.0
    key = pricing.video_pricing_key(model_video)
    return pricing.price(db, key) if key in pricing.catalog() else 0.0


def _loop_clip_with_audio(src_video: Path, audio: Path, dest: Path,
                          size: tuple[int, int], seconds: float, workdir: Path) -> None:
    """Lặp clip video cho đúng thời lượng giọng đọc, ghép audio (lời đọc) vào."""
    w, h = size
    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},format=yuv420p"
    _ffmpeg(["-stream_loop", "-1", "-i", str(src_video), "-i", str(audio),
             "-t", f"{seconds:.2f}", "-vf", vf,
             "-map", "0:v:0", "-map", "1:a:0",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
             "-c:a", "aac", "-b:a", "128k", "-shortest", str(dest)], cwd=workdir)


class ArticleJob:
    def __init__(self, job_id: str, user_id: int, payload: dict, usage_id: int | None = None):
        self.job_id = job_id
        self.user_id = user_id
        self.payload = payload
        self.usage_id = usage_id
        self.status = "queued"       # queued | running | done | failed
        self.progress = 0
        self.step = "Đang chờ xử lý..."
        self.error = ""
        self.result: dict | None = None
        self.created_at = _now()
        self._lock = threading.Lock()

    def update(self, *, status: str | None = None, progress: int | None = None,
               step: str | None = None, error: str | None = None,
               result: dict | None = None) -> None:
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

    def to_dict(self) -> dict:
        with self._lock:
            return {"job_id": self.job_id, "status": self.status, "progress": self.progress,
                    "step": self.step, "error": self.error, "result": self.result,
                    "created_at": self.created_at}


JOBS: dict[str, ArticleJob] = {}
_JOBS_LOCK = threading.Lock()


def create_job(user_id: int, payload: dict, usage_id: int | None = None) -> str:
    job_id = "art_" + secrets.token_hex(8)
    job = ArticleJob(job_id, user_id, payload, usage_id=usage_id)
    with _JOBS_LOCK:
        JOBS[job_id] = job
    # giữ bộ nhớ gọn: chỉ giữ 50 job gần nhất
    if len(JOBS) > 50:
        for old in list(JOBS)[:-50]:
            JOBS.pop(old, None)
    return job_id


def get_job(job_id: str) -> ArticleJob | None:
    with _JOBS_LOCK:
        return JOBS.get(job_id)


def start_job(job_id: str) -> None:
    threading.Thread(target=_run, args=(job_id,), daemon=True).start()


def _ffprobe_duration(path: Path) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=60)
        return float((r.stdout or "0").strip() or 0)
    except Exception:
        return 0.0


def _ffmpeg(args: list[str], cwd: Path, timeout: int = 240) -> None:
    try:
        res = subprocess.run(["ffmpeg", "-y", *args], cwd=str(cwd),
                             capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"ffmpeg chạy quá {timeout}s và bị dừng (file hỏng hoặc mã hoá lỗi)") from e
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg lỗi: {(res.stderr or '')[-400:]}")


def _probe_image(path: Path) -> bool:
    """Ảnh có giải mã được bằng ffmpeg không (ảnh hỏng sẽ làm ffmpeg treo vô hạn)."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
                           capture_output=True, text=True, timeout=30)
        return r.returncode == 0 and "," in (r.stdout or "")
    except Exception:
        return False


def _srt_ts(seconds: float) -> str:
    ms = int(round(max(0.0, seconds) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _build_srt(cues: list[tuple[float, float, str]]) -> str:
    from .subtitles import wrap_subtitle
    out = []
    for i, (t0, t1, text) in enumerate(cues, start=1):
        out.append(f"{i}\n{_srt_ts(t0)} --> {_srt_ts(t1)}\n{wrap_subtitle(text)}\n")
    return "\n".join(out)


def _scene_clip(image: Path, audio: Path, dest: Path, size: tuple[int, int], seconds: float,
                workdir: Path) -> None:
    """Clip Ken Burns (zoom chậm) từ 1 ảnh + giọng đọc, đúng thời lượng audio."""
    w, h = size
    frames = max(30, int(round(seconds * 30)))
    zoom = (f"zoompan=z='min(zoom+0.0012,1.12)':d={frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps=30")
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},{zoom},"
          "format=yuv420p")
    try:
        _ffmpeg(["-loop", "1", "-i", str(image), "-i", str(audio),
                 "-t", f"{seconds:.2f}", "-vf", vf,
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                 "-c:a", "aac", "-b:a", "128k", "-shortest", str(dest)], cwd=workdir)
    except Exception as e:
        # zoompan có thể lỗi trên ffmpeg cũ -> fallback ảnh tĩnh
        logger.warning("[article] zoompan lỗi, dùng ảnh tĩnh: %s", e)
        _ffmpeg(["-loop", "1", "-i", str(image), "-i", str(audio),
                 "-t", f"{seconds:.2f}",
                 "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},format=yuv420p",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                 "-c:a", "aac", "-b:a", "128k", "-shortest", str(dest)], cwd=workdir)


def _render(job: ArticleJob) -> None:
    p = job.payload
    user_id = job.user_id
    out_dir = user_outputs_dir(user_id)
    llm_id = p["model_llm"]
    img_id = p["model_image"]
    duration = int(p["duration"])
    language = p.get("language") or "vi"
    ratio = p.get("ratio") or "9:16"
    voice = p.get("voice") or "auto"
    if voice == "native":      # "native" = model tự nói -> ở đây luôn có lời đọc TTS
        voice = "auto"
    video_mode = str(p.get("video_mode") or "slide").strip().lower()
    model_video = str(p.get("model_video") or "").strip()
    size = (1080, 1920) if ratio == "9:16" else ((1920, 1080) if ratio == "16:9" else (1080, 1080))

    job.update(status="running", progress=8, step="Đang lấy nội dung bài viết...")
    if p.get("article"):
        article = p["article"]
    elif (p.get("text") or "").strip():
        body = (p["text"] or "").strip()
        article = {"title": body.split("\n")[0][:160], "text": body, "url": ""}
    else:
        article = fetch_article(p["url"])
    job.update(progress=16, step="Đang viết lời dẫn...")

    with SessionLocal() as db:
        llm_creds = adminmodels.creds(db, llm_id) or {}
        llm_key = f"m.{llm_id}"
        llm_price = pricing.price(db, llm_key) if llm_key in pricing.catalog() else 0.0
        img_creds = adminmodels.creds(db, img_id) or {}
        img_key = f"m.{img_id}"
        img_price = pricing.price(db, img_key) if img_key in pricing.catalog() else 0.0
        vid_creds = (adminmodels.creds(db, model_video) or {}) if model_video else {}
        vid_price = _video_price(model_video, db)

    script = build_script(article["title"], article["text"], model_llm=llm_id,
                          creds=llm_creds, duration=duration, language=language)
    if llm_price > 0:
        with SessionLocal() as db:
            if not credits.charge(db, user_id, llm_price, kind="spend",
                                  reason="LLM viết kịch bản từ bài viết", ref_type="article",
                                  ref_id=job.job_id):
                db.rollback()
                raise ValueError("Không đủ credit để viết kịch bản (LLM)")
            db.commit()

    scenes = script["scenes"]
    job.update(progress=28, step=f"Đang tạo {len(scenes)} ảnh minh hoạ...")
    clips: list[Path] = []
    cues: list[tuple[float, float, str]] = []
    t_cursor = 0.0
    for i, scene in enumerate(scenes, start=1):
        base = (28 if video_mode != "video" else 20)
        job.update(progress=base + int(45 * (i - 1) / max(len(scenes), 1)),
                   step=f"Ảnh + giọng đọc cảnh {i}/{len(scenes)}..."
                   if video_mode != "video" else f"Cảnh {i}/{len(scenes)}...")
        img_dest = out_dir / f"article_{job.job_id}_{i}.png"
        try:
            vilao_image.gen_image(scene["image_prompt"] or scene["thoại"], img_dest,
                                  base_url=img_creds.get("base_url"),
                                  api_key=img_creds.get("api_key"),
                                  model=img_creds.get("model_name") or img_id,
                                  ratio=ratio)
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"Không tạo được ảnh cảnh {i}: {e}") from e
        if not _probe_image(img_dest):
            raise ValueError(f"Ảnh cảnh {i} không đọc được (file hỏng từ model ảnh) — thử lại")
        if img_price > 0:
            with SessionLocal() as db:
                if not credits.charge(db, user_id, img_price, kind="spend",
                                      reason=f"Ảnh bài viết cảnh {i}", ref_type="article",
                                      ref_id=job.job_id):
                    db.rollback()
                    raise ValueError("Không đủ credit để tạo ảnh")
                db.commit()

        audio_dest = out_dir / f"article_{job.job_id}_{i}.mp3"
        rate, pitch, volume = tts_mod.emotion_params(scene.get("biểu_cảm"))
        tts_mod.gen_tts(scene["thoại"], audio_dest,
                        voice=tts_mod.resolve_voice(voice, None, language=language),
                        rate=rate, pitch=pitch, volume=volume)
        seconds = _ffprobe_duration(audio_dest) or float(scene["thời_lượng_giây"])
        clip = out_dir / f"article_{job.job_id}_{i}.mp4"
        if video_mode == "video":
            # Dùng model video thật (Veo/omni-flash…): ảnh keyframe làm first_frame,
            # lặp/cắt cho khớp thời lượng giọng đọc rồi ghép audio TTS.
            if not model_video:
                raise ValueError("Chưa chọn model video cho chế độ dựng bằng model")
            raw_video = out_dir / f"article_{job.job_id}_{i}_raw.mp4"
            dur = max(4, min(int(round(seconds)), 8))
            job.update(progress=60 + int(25 * (i - 0.5) / max(len(scenes), 1)),
                       step=f"Đang render cảnh {i}/{len(scenes)} bằng model video...")
            scene_prompt = (f"{scene['image_prompt']}. Cinematic shot, smooth camera movement, "
                            f"photorealistic, high quality. No text, no captions, no watermark.")
            try:
                minimax.generate(scene_prompt, raw_video, duration=dur, ratio=ratio,
                                 resolution="768P", first_frame=img_dest,
                                 base_url=vid_creds.get("base_url") or None,
                                 api_key=vid_creds.get("api_key"),
                                 model=vid_creds.get("model_name") or model_video)
            except Exception as e:  # noqa: BLE001
                raise ValueError(f"Model video lỗi ở cảnh {i}: {e}") from e
            if vid_price > 0:
                with SessionLocal() as db2:
                    if not credits.charge(db2, user_id, vid_price, kind="spend",
                                          reason=f"Gen video cảnh {i}", ref_type="article",
                                          ref_id=job.job_id):
                        db2.rollback()
                        raise ValueError("Không đủ credit để render tiếp (model video)")
                    db2.commit()
            _loop_clip_with_audio(raw_video, audio_dest, clip, size, seconds, out_dir)
            raw_video.unlink(missing_ok=True)
        else:
            _scene_clip(img_dest, audio_dest, clip, size, seconds, out_dir)
        clips.append(clip)
        cues.append((t_cursor, t_cursor + seconds, scene["thoại"]))
        t_cursor += seconds
        img_dest.unlink(missing_ok=True)
        audio_dest.unlink(missing_ok=True)

    job.update(progress=76, step="Đang ghép video và chèn phụ đề...")
    srt_path = out_dir / f"article_{job.job_id}.srt"
    srt_path.write_text(_build_srt(cues), encoding="utf-8")

    concat_list = out_dir / f"article_{job.job_id}_concat.txt"
    concat_list.write_text("".join(f"file '{c.name}'\n" for c in clips), encoding="utf-8")
    merged = out_dir / f"article_{job.job_id}_merged.mp4"
    _ffmpeg(["-f", "concat", "-safe", "0", "-i", concat_list.name,
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
             "-c:a", "aac", "-b:a", "128k", str(merged)], cwd=out_dir)

    ass_path = srt_path.with_suffix(".ass")
    try:
        from .routers.videotools import _srt_to_ass
        _srt_to_ass(srt_path.read_text(encoding="utf-8"), ass_path, fsize=20,
                    position="bottom", width=size[0], height=size[1])
        final = out_dir / f"article_{job.job_id}.mp4"
        _ffmpeg(["-i", merged.name, "-vf", f"ass={ass_path.name}",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                 "-c:a", "copy", final.name], cwd=out_dir)
    except Exception as e:  # phụ đề lỗi không làm mất video
        logger.warning("[article] chèn phụ đề lỗi: %s", e)
        final = merged

    for c in clips:
        c.unlink(missing_ok=True)
    concat_list.unlink(missing_ok=True)
    if merged != final:
        merged.unlink(missing_ok=True)

    result = {
        "video_url": url_for(final),
        "srt_url": url_for(srt_path),
        "title": script["title"],
        "summary": script.get("summary", ""),
        "source_url": article.get("url", ""),
        "num_scenes": len(cues),
        "duration": round(t_cursor, 1),
        "scenes": scenes,
    }
    if job.usage_id:
        from .featurebilling import finish
        with SessionLocal() as db:
            finish(db, job.usage_id, success=True)
    job.update(status="done", progress=100, step="Hoàn tất", result=result)


def _run(job_id: str) -> None:
    job = get_job(job_id)
    if job is None:
        return
    try:
        _render(job)
    except Exception as e:  # noqa: BLE001
        logger.warning("[article] job %s lỗi: %s", job_id, e)
        if job.usage_id:
            from .featurebilling import finish
            with SessionLocal() as db:
                finish(db, job.usage_id, success=False)
        job.update(status="failed", progress=100, step="Lỗi", error=str(e)[:800])


def estimated_cost(model_llm: str, model_image: str, num_scenes: int, db,
                   model_video: str = "", video_mode: str = "slide") -> dict:
    """Ước tính credit: 1 lượt LLM + N ảnh (+ N request model video khi dựng bằng model thật).
    TTS và ghép dựng video (ffmpeg) miễn phí."""
    llm_key = f"m.{model_llm}"
    img_key = f"m.{model_image}"
    llm_price = pricing.price(db, llm_key) if llm_key in pricing.catalog() else 0.0
    img_price = pricing.price(db, img_key) if img_key in pricing.catalog() else 0.0
    vid_price = 0.0
    if video_mode == "video" and model_video:
        v_key = pricing.video_pricing_key(model_video)
        vid_price = pricing.price(db, v_key) if v_key in pricing.catalog() else 0.0
    total = round(llm_price + img_price * max(0, num_scenes)
                  + vid_price * (num_scenes if video_mode == "video" else 0), 2)
    return {"llm_credit": llm_price, "image_credit": img_price, "num_scenes": num_scenes,
            "video_credit": vid_price, "video_mode": video_mode, "tong_credit": total}

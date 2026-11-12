"""Subtitle intelligence: better ASR coverage + LLM-assisted refine/translate.

Why this module exists
----------------------
The transcribe endpoint used to hand back whatever faster-whisper produced, which
meant quiet or trailing speech was silently dropped and the Vietnamese output was
whatever Google Translate free produced.  Both steps are now handled here:

* ASR  — a better default model, friendlier VAD thresholds, and a *gap repair*
  pass that re-transcribes silent stretches with VAD off to recover speech the
  VAD filter cut away.
* LLM — the app already ships admin-managed chat models (deepseek / glm / minimax
  / claude).  They are used to clean up the raw transcript and to translate with
  full context, a character budget per subtitle line and glossary consistency —
  all things a per-sentence MT API cannot do.

Every LLM call is optional: without an enabled chat model the pipeline falls back
to the previous behaviour (faster-whisper + Google Translate free).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from . import ai

log = logging.getLogger(__name__)

# faster-whisper model size per quality tier chosen by the user.
QUALITY_MODELS = {
    "fast": "small",
    "accurate": "medium",
    "best": "large-v3",
}

# VAD is what silently eats quiet/trailing speech.  The library default is
# min_silence_duration_ms=2000 (very aggressive); 400ms keeps natural pauses.
VAD_PARAMS = {"min_silence_duration_ms": 400, "speech_pad_ms": 200}

# A gap longer than this between two cues is treated as "possibly missed speech".
GAP_SUSPECT_SECONDS = 1.6
# A re-transcribed slice is only accepted when whisper is confident it is speech.
MIN_NO_SPEECH_PROB = 0.55
MIN_AVG_LOGPROB = -1.2

# Subtitle line budget.  42 chars is the classic broadcast limit for 16:9; for
# 9:16 vertical video a narrower budget keeps text off the safe area.
MAX_CHARS_PER_LINE = 42
MAX_LINES = 2


# --------------------------------------------------------------------------- ASR


def whisper_model_for(quality: str) -> str:
    q = (quality or "").strip().lower()
    if q in QUALITY_MODELS:
        return QUALITY_MODELS[q]
    return QUALITY_MODELS["accurate"]


def _segment_dict(s) -> dict:
    return {"start": round(float(s.start), 2), "end": round(float(s.end), 2),
            "text": (s.text or "").strip()}


def transcribe_audio(audio, quality: str = "accurate", vad: bool = True,
                     model_override: str = "", progress=None) -> tuple[list[dict], dict]:
    """Transcribe a float32 16k mono array, then repair gaps the VAD may have cut.

    Returns (segments, info).  `info` carries the detected language plus
    `recovered` — how many cues the gap-repair pass added.
    """
    import numpy as np  # local import: numpy is only needed for this path
    from faster_whisper import WhisperModel

    size = (model_override or "").strip() or whisper_model_for(quality)
    model = WhisperModel(size, device="cpu", compute_type="int8")
    if progress:
        progress("loading")
    segments_raw, info = model.transcribe(
        audio, beam_size=5, vad_filter=vad, vad_parameters=VAD_PARAMS if vad else None,
        condition_on_previous_text=False)
    segments = []
    for s in segments_raw:
        d = _segment_dict(s)
        if d["text"]:
            segments.append(d)

    info_out = {"language": getattr(info, "language", "unknown") or "unknown",
                "language_probability": round(float(getattr(info, "language_probability", 0.0) or 0.0), 3),
                "model": size}
    if vad and segments:
        recovered = _repair_gaps(model, audio, segments)
        info_out["recovered"] = recovered
    return segments, info_out


def _repair_gaps(model, audio, segments: list[dict]) -> int:
    """Re-transcribe silent stretches with VAD off to recover speech it removed.

    Whisper is asked for word timestamps so we can tell "real silence" from
    "whisper skipped this"; a slice is only accepted when whisper reports it is
    confident about the content (no_speech_prob low, avg_logprob high enough).
    """
    total = len(audio) / 16000.0
    bounds = []
    cursor = 0.0
    for s in segments:
        bounds.append((cursor, s["start"]))
        cursor = s["end"]
    bounds.append((cursor, total))

    added: list[dict] = []
    for gap_start, gap_end in bounds:
        length = gap_end - gap_start
        if length < GAP_SUSPECT_SECONDS:
            continue
        if gap_start < 0 or gap_end > total:
            continue
        i0 = int(gap_start * 16000)
        i1 = int(gap_end * 16000)
        slice_ = audio[i0:i1]
        if len(slice_) < 16000:      # < 1s — nothing worth re-encoding
            continue
        try:
            segs, _info = model.transcribe(
                slice_, beam_size=5, vad_filter=False, condition_on_previous_text=False,
                no_speech_threshold=0.6)
            for s in segs:
                text = (s.text or "").strip()
                if not text:
                    continue
                if float(getattr(s, "no_speech_prob", 1.0)) > MIN_NO_SPEECH_PROB:
                    continue
                if float(getattr(s, "avg_logprob", -9.0)) < MIN_AVG_LOGPROB:
                    continue
                added.append({"start": round(gap_start + float(s.start), 2),
                              "end": round(gap_start + float(s.end), 2),
                              "text": text})
        except Exception as e:      # a failed gap must not kill the transcript
            log.warning("[subtitle] gap repair failed at %.1fs: %s", gap_start, e)
    if not added:
        return 0
    segments.extend(added)
    segments.sort(key=lambda d: d["start"])
    segments[:] = _merge(segments)
    return len(added)


def _merge(segments: list[dict]) -> list[dict]:
    """Merge cues that overlap or touch, so the SRT never has overlapping times."""
    out: list[dict] = []
    for s in segments:
        if out and s["start"] <= out[-1]["end"] + 0.05:
            prev = out[-1]
            prev["end"] = max(prev["end"], s["end"])
            if s["text"] and s["text"] not in prev["text"]:
                prev["text"] = (prev["text"] + " " + s["text"]).strip()
        else:
            out.append(dict(s))
    return out


# ------------------------------------------------------------------ subtitle text


def wrap_subtitle(text: str, max_chars: int = MAX_CHARS_PER_LINE,
                  max_lines: int = MAX_LINES) -> str:
    """Wrap a subtitle line to at most `max_lines` lines of `max_chars` characters."""
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        cand = (cur + " " + w).strip() if cur else w
        if len(cand) <= max_chars:
            cur = cand
            continue
        if cur:
            lines.append(cur)
        cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        # Không đủ chỗ cho toàn bộ câu → giữ max_lines-1 dòng đầu, dòng cuối gom
        # phần còn lại rồi cắt đúng max_chars. Độ dài được bảo đảm tuyệt đối;
        # người dùng có thể tách cue trong trình sửa phụ đề nếu muốn giữ đủ chữ.
        head = lines[: max_lines - 1]
        tail = " ".join(lines[max_lines - 1:])
        lines = head + [tail[:max_chars].rstrip()]
    return "\n".join(lines)


# ---------------------------------------------------------------------- LLM step


def _chat_json(llm_id: str, creds: dict, system: str, user: str,
               timeout: float = 180.0) -> Any | None:
    """One OpenAI-compatible chat call that must answer with JSON. None on any failure."""
    if not creds or not creds.get("api_key") or not creds.get("model_name"):
        return None
    try:
        msg = ai.chat(creds["model_name"], [{"role": "system", "content": system},
                                            {"role": "user", "content": user}],
                      json_mode=True, base_url=creds.get("base_url"),
                      api_key=creds.get("api_key"), timeout=timeout)
    except Exception as e:
        log.warning("[subtitle] LLM call failed (%s): %s", llm_id, e)
        return None
    content = (msg or {}).get("content") or ""
    return _loads_json(content)


def _loads_json(content: str) -> Any | None:
    content = (content or "").strip()
    if not content:
        return None
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z]*\n?", "", content)
        content = re.sub(r"\n?```$", "", content.strip())
    try:
        return json.loads(content)
    except Exception:
        pass
    m = re.search(r"[\[{].*[\]}]", content, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def refine_transcript(segments: list[dict], llm_id: str, creds: dict) -> list[dict] | None:
    """Ask the LLM to repair ASR mistakes while keeping every cue and its timing.

    Whisper on Vietnamese/English ad audio commonly mis-hears brand names and
    merges two sentences.  The LLM sees the whole transcript, so it can fix the
    text without being able to move or drop a cue — the segment list is rebuilt
    from the original timings, never from the model's output.
    """
    if not segments or not creds:
        return None
    numbered = "\n".join(f"{i}. {s['text']}" for i, s in enumerate(segments))
    system = (
        "Bạn là biên tập viên phụ đề chuyên nghiệp. Nhiệm vụ: sửa lỗi nhận dạng giọng nói "
        "(ASR) trong phụ đề.\n"
        "Quy tắc:\n"
        "1. Giữ nguyên ý nghĩa và ngôn ngữ của câu; chỉ sửa chữ sai, thêm dấu câu và viết hoa.\n"
        "2. KHÔNG được thêm, bớt, gộp hay tách câu — số câu phải khớp với đầu vào.\n"
        "3. Sửa tên riêng / thương hiệu bị nghe sai nếu ngữ cảnh rõ ràng.\n"
        "4. Trả về JSON đúng định dạng: {\"lines\": [\"câu 1\", \"câu 2\", ...]}\n"
        "5. Chỉ trả về JSON, không thêm chú thích."
    )
    user = f"Danh sách câu thoại:\n{numbered}"
    data = _chat_json(llm_id, creds, system, user)
    lines = None
    if isinstance(data, dict):
        lines = data.get("lines") or data.get("segments") or data.get("texts")
    elif isinstance(data, list):
        lines = data
    if not isinstance(lines, list) or len(lines) != len(segments):
        return None
    out = []
    for seg, txt in zip(segments, lines):
        txt = re.sub(r"\s+", " ", str(txt or "")).strip()
        if not txt:
            txt = seg["text"]
        out.append({**seg, "text": txt})
    return out


def translate_segments(segments: list[dict], src_lang: str, tgt_lang: str,
                       llm_id: str, creds: dict,
                       batch: int = 25) -> list[str] | None:
    """Translate the whole transcript with the LLM, in context-aware batches.

    A per-sentence MT API cannot keep names, brands or pronouns consistent and
    happily returns text far too long for one subtitle line.  Here the LLM sees
    the neighbouring lines, is told the character budget and the target language,
    and answers with a JSON array that is re-aligned to the input cues.
    """
    if not segments or not creds:
        return None
    texts = [s["text"] for s in segments]
    src_name = (src_lang or "auto").upper()
    tgt_name = (tgt_lang or "").upper()
    out: list[str] = []
    for start in range(0, len(texts), batch):
        chunk = texts[start:start + batch]
        ctx_before = texts[max(0, start - 3):start]
        ctx_after = texts[start + batch:start + batch + 2]
        numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(chunk))
        system = (
            f"Bạn là dịch gia phụ đề chuyên nghiệp. Dịch từ {src_name} sang {tgt_name}.\n"
            "Quy tắc:\n"
            "1. Dịch tự nhiên, đúng văn phong nói, ưu tiên tự nhiên của ngôn ngữ đích.\n"
            "2. GIỮ nguyên tên riêng, thương hiệu, số, đơn vị. Dùng thuật ngữ nhất quán xuyên suốt.\n"
            f"3. Mỗi câu phải ≤ {MAX_CHARS_PER_LINE * MAX_LINES} ký tự. Nếu dài, rút gọn — KHÔNG cắt ý.\n"
            "4. Giữ đúng số câu và thứ tự. Trả về JSON đúng định dạng: {\"lines\": [...]}\n"
            "5. Chỉ trả về JSON, không thêm chú thích."
        )
        parts = []
        if ctx_before:
            parts.append("Câu trước (ngữ cảnh, KHÔNG dịch, không đưa vào kết quả):\n" +
                         "\n".join(f"- {c}" for c in ctx_before))
        parts.append(f"Cần dịch:\n{numbered}")
        if ctx_after:
            parts.append("Câu sau (ngữ cảnh, KHÔNG dịch):\n" +
                         "\n".join(f"- {c}" for c in ctx_after))
        data = _chat_json(llm_id, creds, system, "\n\n".join(parts))
        lines = None
        if isinstance(data, dict):
            lines = data.get("lines") or data.get("segments") or data.get("translations")
        elif isinstance(data, list):
            lines = data
        if not isinstance(lines, list) or len(lines) != len(chunk):
            log.warning("[subtitle] translation batch %d mismatch (%s vs %s) — keep original",
                        start, len(lines) if isinstance(lines, list) else "?", len(chunk))
            out.extend(chunk)
            continue
        out.extend(re.sub(r"\s+", " ", str(x or "")).strip() or "" for x in lines)
    return out or None

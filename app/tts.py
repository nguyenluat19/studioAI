"""Text-to-Speech qua edge-tts (Microsoft Neural voices) hoặc ElevenLabs (voice clone thật).

Ngôn ngữ thoại (Tiếng Việt / English) do người dùng chọn; giọng tự động theo
giới tính nhân vật theo ngôn ngữ tương ứng. Giọng clone ElevenLabs có prefix "el:".
"""
import asyncio
import re
import time
from pathlib import Path

import httpx

from .config import settings

import edge_tts

# Giá trị đặc biệt: auto-pick giọng theo giới tính nhân vật.
VOICE_AUTO = "auto"
# Giữ nguyên âm thanh gốc do model video sinh ra (không chạy TTS).
VOICE_NATIVE = "native"

VIETNAMESE_VOICES = [
    {"id": "vi-VN-HoaiMyNeural", "name": "Hoài My (Nữ)", "gender": "Female", "lang": "vi"},
    {"id": "vi-VN-NamMinhNeural", "name": "Nam Minh (Nam)", "gender": "Male", "lang": "vi"},
]

ENGLISH_VOICES = [
    {"id": "en-US-AriaNeural", "name": "Aria (Female)", "gender": "Female", "lang": "en"},
    {"id": "en-US-GuyNeural", "name": "Guy (Male)", "gender": "Male", "lang": "en"},
]

ALL_VOICES = [*VIETNAMESE_VOICES, *ENGLISH_VOICES]

LANGUAGE_NAMES = {"vi": "Tiếng Việt", "en": "English"}
GENDER_VOICES = {
    ("vi", "Female"): "vi-VN-HoaiMyNeural",
    ("vi", "Male"): "vi-VN-NamMinhNeural",
    ("en", "Female"): "en-US-AriaNeural",
    ("en", "Male"): "en-US-GuyNeural",
}
# Giá trị truy vấn: "english", "en", "tiếng Anh" (bỏ dấu) ...
_LANG_ALIASES = {"vi": "vi", "vietnamese": "vi", "tiếng việt": "vi", "việt": "vi",
                 "en": "en", "english": "en", "tieng anh": "en", "tiếng anh": "en"}
_GENDER_ALIASES = {"nữ": "Female", "nu": "Female", "female": "Female", "f": "Female",
                   "nam": "Male", "male": "Male", "m": "Male"}

ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"
ELEVEN_PREFIX = "el:"          # voice value của giọng clone ElevenLabs: "el:<voice_id>"
ELEVEN_MODEL = "eleven_multilingual_v2"

# Cảm xúc -> (rate, pitch, volume) cho edge-tts — rate/pitch điều khiển nhịp + cao độ, volume điều khiển độ lớn tiếng.
# Key tiếng Việt không dấu (đã bỏ dấu khi so khớp).
_EMOTION_PRESETS = {
    "vui ve":        ("+8%",  "+3Hz",  "+8%"),
    "han hoan":      ("+10%", "+3Hz",  "+10%"),
    "phan khich":    ("+13%", "+5Hz",  "+12%"),
    "lac quan":      ("+4%",  "+1Hz",  "+5%"),
    "tu tin":        ("+2%",  "+1Hz",  "+8%"),
    "nghiem tuc":    ("-5%",  "-2Hz",  "+2%"),
    "binh thuong":   ("+0%",  "+0Hz",  "+0%"),
    "binh than":     ("-3%",  "-1Hz",  "-5%"),
    "nhung niu":     ("+2%",  "+5Hz",  "-5%"),
    "ngot ngao":     ("+0%",  "+5Hz",  "-8%"),
    "cam dong":      ("-8%",  "+1Hz",  "-8%"),
    "cam thong":     ("-8%",  "-1Hz",  "-8%"),
    "buon ba":       ("-12%", "-4Hz",  "-10%"),
    "that vong":     ("-8%",  "-3Hz",  "-10%"),
    "chan nan":      ("-10%", "-3Hz",  "-10%"),
    "tuc gian":      ("+6%",  "+6Hz",  "+12%"),
    "gian du":       ("+6%",  "+7Hz",  "+14%"),
    "so hai":        ("+12%", "+7Hz",  "-5%"),
    "hoang loan":    ("+15%", "+8Hz",  "-5%"),
    "ngac nhien":    ("+8%",  "+7Hz",  "+5%"),
    "soc":           ("+8%",  "+8Hz",  "+5%"),
    "thi tham":      ("-15%", "-6Hz",  "-25%"),
    "khoc":          ("-15%", "-5Hz",  "-12%"),
    "thut thit":     ("-15%", "-5Hz",  "-14%"),
    "thong thai":    ("-5%",  "+2Hz",  "+0%"),
    "cao hung":      ("+12%", "+4Hz",  "+10%"),
    # English aliases
    "happy":         ("+8%",  "+3Hz",  "+8%"),
    "excited":       ("+12%", "+5Hz",  "+12%"),
    "joyful":        ("+10%", "+4Hz",  "+10%"),
    "optimistic":    ("+4%",  "+1Hz",  "+5%"),
    "confident":     ("+2%",  "+1Hz",  "+8%"),
    "serious":       ("-5%",  "-2Hz",  "+2%"),
    "calm":          ("-3%",  "-1Hz",  "-5%"),
    "neutral":       ("+0%",  "+0Hz",  "+0%"),
    "sad":           ("-12%", "-4Hz",  "-10%"),
    "disappointed":  ("-8%",  "-3Hz",  "-10%"),
    "upset":         ("-8%",  "-2Hz",  "-10%"),
    "empathetic":    ("-8%",  "-1Hz",  "-8%"),
    "moved":         ("-8%",  "+1Hz",  "-8%"),
    "angry":         ("+6%",  "+6Hz",  "+12%"),
    "furious":       ("+6%",  "+7Hz",  "+14%"),
    "scared":        ("+12%", "+7Hz",  "-5%"),
    "afraid":        ("+12%", "+7Hz",  "-5%"),
    "fearful":       ("+15%", "+8Hz",  "-5%"),
    "surprised":     ("+8%",  "+7Hz",  "+5%"),
    "shocked":       ("+8%",  "+8Hz",  "+5%"),
    "whisper":       ("-15%", "-6Hz",  "-25%"),
    "whispered":     ("-15%", "-6Hz",  "-25%"),
    "crying":        ("-15%", "-5Hz",  "-12%"),
    "sob":           ("-15%", "-5Hz",  "-14%"),
    "sweet":         ("+2%",  "+5Hz",  "-5%"),
    "cuddly":        ("+0%",  "+5Hz",  "-8%"),
    "wise":          ("-5%",  "+2Hz",  "+0%"),
}

# Tag do LLM trả về -> cue diễn xuất bằng tiếng Anh (nhúng vào video prompt cho Veo).
_EMOTION_EN = {
    "vui ve": "joyful, warm smile", "han hoan": "cheerful, upbeat",
    "phan khich": "highly excited, energetic", "lac quan": "optimistic, light",
    "tu tin": "self-assured, confident", "nghiem tuc": "serious, grave",
    "binh thuong": "calm, natural", "binh than": "calm and composed",
    "nhung niu": "cute, petting, playful", "ngot ngao": "sweet, gentle",
    "cam dong": "touched, moved, teary-eyed", "cam thong": "empathetic, gentle",
    "buon ba": "sad, sorrowful", "that vong": "disappointed, let down",
    "chan nan": "bored, weary", "tuc gian": "angry, irritated",
    "gian du": "furious, hostile", "so hai": "scared, frightened",
    "hoang loan": "panicking, frantic", "ngac nhien": "surprised, astonished",
    "soc": "shocked, stunned", "thi tham": "whispering, hushed",
    "khoc": "crying, tearful", "thut thit": "sobbing quietly",
    "thong thai": "wise, measured", "cao hung": "exhilarated, passionate",
    "happy": "joyful, warm smile", "excited": "highly excited, energetic",
    "joyful": "joyful, upbeat", "optimistic": "optimistic, light",
    "confident": "self-assured, confident", "serious": "serious, grave",
    "calm": "calm and composed", "neutral": "calm, natural",
    "sad": "sad, sorrowful", "disappointed": "disappointed, let down",
    "upset": "upset, hurt", "empathetic": "empathetic, gentle",
    "moved": "touched, teary-eyed", "angry": "angry, irritated",
    "furious": "furious, hostile", "scared": "scared, frightened",
    "afraid": "afraid, frightened", "fearful": "panicking, frantic",
    "surprised": "surprised, astonished", "shocked": "shocked, stunned",
    "whisper": "whispering, hushed", "whispered": "whispering, hushed",
    "crying": "crying, tearful", "sob": "sobbing quietly",
    "sweet": "sweet, gentle", "cuddly": "cute, playful",
    "wise": "wise, measured",
}


def _strip_accents(s: str) -> str:
    import unicodedata
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", str(s or "").lower())
        if not unicodedata.combining(ch)
    ).replace("đ", "d").replace("Đ", "d")


def _match_emotion(emotion: str | None):
    """Tìm preset cảm xúc phù hợp nhất: khớp cụm dài nhất trước, bỏ qua hoa/thường + dấu."""
    if not emotion:
        return None
    txt = _strip_accents(emotion)
    # Khớp thẳng tag trước (dài nhất), sau đó mới khớp theo chiều rộng 'chứa trong'.
    keys = sorted(_EMOTION_PRESETS, key=len, reverse=True)
    for k in keys:
        if k == txt:
            return _EMOTION_PRESETS[k]
    for k in keys:
        if k in txt:
            return _EMOTION_PRESETS[k]
    return None


class TTSError(RuntimeError):
    pass


def norm_lang(lang: str | None) -> str:
    l = _LANG_ALIASES.get(str(lang or "vi").strip().lower())
    return l or "vi"


def voice_for_gender(gender: str | None, default: str = "vi-VN-HoaiMyNeural",
                     language: str = "vi") -> str:
    """Map giới tính nhân vật (nam/nữ) sang giọng edge-tts theo ngôn ngữ."""
    lang = norm_lang(language)
    if gender:
        g = _GENDER_ALIASES.get(str(gender).strip().lower(), str(gender).strip().title())
        v = GENDER_VOICES.get((lang, g))
        if v:
            return v
        # Giới tính hợp lệ nhưng ngôn ngữ không có giọng tương ứng -> mặc định theo ngôn ngữ.
        if lang in ("vi", "en"):
            return GENDER_VOICES[(lang, "Female")]
    return default if lang == "vi" else GENDER_VOICES[("en", "Female")]


def _norm(s) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", str(s or "").strip().lower())


def gender_of_character(name: str, characters: list[dict]) -> str | None:
    """Tìm giới tính nhân vật theo tên (khớp thô, bỏ dấu, không phân biệt hoa/thường)."""
    if not name or not characters:
        return None
    target = _norm(name)
    # exact match first, then substring
    for c in characters:
        if _norm(c.get("tên")) == target:
            return c.get("giới_tính")
    for c in characters:
        cn = _norm(c.get("tên"))
        if cn and (cn in target or target in cn):
            return c.get("giới_tính")
    return None


def resolve_voice(voice: str, gender: str | None = None, language: str = "vi") -> str:
    """Trả về giọng thật: voice==auto -> theo gender + ngôn ngữ; ngược lại dùng voice của user."""
    lang = norm_lang(language)
    if not voice or voice == VOICE_AUTO:
        default = GENDER_VOICES[(lang, "Female")]
        return voice_for_gender(gender, default=default, language=lang)
    # Giọng clone ElevenLabs (el:<voice_id>) được passthrough như một giọng explicit.
    if voice and str(voice).startswith(ELEVEN_PREFIX):
        return voice
    # Giọng explicit phải khớp ngôn ngữ; nếu không, bám về giọng auto theo gender.
    ids = {v["id"]: v["lang"] for v in ALL_VOICES}
    if voice in ids and ids[voice] == lang:
        return voice
    return voice_for_gender(gender, default=GENDER_VOICES[(lang, "Female")], language=lang)


def emotion_params(emotion: str | None) -> tuple[str, str, str]:
    """Map biểu cảm sang (rate, pitch, volume) cho edge-tts. Mặc định neutral."""
    return _match_emotion(emotion) or ("+0%", "+0Hz", "+0%")


def emotion_cue_en(emotion: str | None) -> str:
    """English acting cue for the video prompt (e.g. 'joyful, warm smile'). Mặc định: 'calm, natural'."""
    if not emotion:
        return "calm, natural"
    txt = _strip_accents(emotion)
    keys = sorted(_EMOTION_EN, key=len, reverse=True)
    for k in keys:
        if k == txt:
            return _EMOTION_EN[k]
    for k in keys:
        if k in txt:
            return _EMOTION_EN[k]
    return "calm, natural"


def _sanitize(text: str) -> str:
    """Loại bỏ ký tự đặc biệt có thể gây lỗi edge-tts; thêm dấu câu cuối câu cho ngắt nhịp tự nhiên."""
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"[\"'`]", "", text)
    text = text.strip()
    if len(text) < 3:
        return ""
    if text[-1] not in ".!?…,;:":
        text += "."          # dấu câu cuối câu giúp edge-tts ngắt giọng đúng chỗ, bớt "máy đọc"
    return text


async def _synthesize(text: str, voice: str, dest: Path, rate: str, pitch: str, volume: str) -> None:
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume)
    await communicate.save(str(dest))


def gen_tts(text: str, dest, *, voice: str = "vi-VN-HoaiMyNeural", timeout: float = 300,
            rate: str | None = None, pitch: str | None = None, volume: str | None = None) -> Path:
    """Tạo audio MP3 từ text. Voice bắt đầu bằng "el:" sẽ dùng ElevenLabs clone, còn lại edge-tts."""
    text = _sanitize(text)
    if not text:
        raise TTSError("Text rỗng sau khi sanitize — bỏ qua TTS")
    dest.parent.mkdir(parents=True, exist_ok=True)
    clone_id = value_to_voice_id(voice)
    if clone_id:
        return gen_clone_tts(text, dest, voice_id=clone_id, timeout=timeout)
    if rate is None or pitch is None or volume is None:
        d_rate, d_pitch, d_volume = emotion_params("")
        rate = rate or d_rate
        pitch = pitch or d_pitch
        volume = volume or d_volume
    last_err = None
    for attempt in range(5):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_synthesize(text, voice, dest, rate, pitch, volume))
            finally:
                loop.close()
            if dest.exists() and dest.stat().st_size >= 100:
                return dest
            last_err = "File audio rỗng"
        except Exception as e:
            last_err = str(e)
            if dest.exists():
                dest.unlink(missing_ok=True)
            time.sleep(3 * (attempt + 1))
    raise TTSError(f"TTS lỗi sau 5 lần thử: {last_err}")


def list_voices(lang: str | None = None) -> list[dict]:
    if not lang:
        return [{"id": VOICE_AUTO, "name": "Tự động theo giới tính nhân vật", "gender": "Auto", "lang": "both"},
                *VIETNAMESE_VOICES, *ENGLISH_VOICES]
    l = norm_lang(lang)
    return [{"id": VOICE_AUTO, "name": "Tự động theo giới tính nhân vật", "gender": "Auto", "lang": l},
            *[v for v in ALL_VOICES if v["lang"] == l]]


# ---------------------------------------------------------------------------
# Voice clone qua ElevenLabs (chỉ chạy khi admin đặt ELEVENLABS_API_KEY)
# ---------------------------------------------------------------------------
class VoiceCloneError(TTSError):
    """Lõi clone giọng / TTS clone (chưa đặt key, gateway lỗi, file mẫu lỗi)."""


def elevenlabs_enabled() -> bool:
    return bool(settings.elevenlabs_api_key)


def voice_to_value(voice_id: str) -> str:
    return ELEVEN_PREFIX + voice_id


def value_to_voice_id(value: str | None) -> str | None:
    v = (value or "").strip()
    return v[len(ELEVEN_PREFIX):] if v.startswith(ELEVEN_PREFIX) else None


def clone_voice(name: str, samples: list[Path]) -> str:
    """Upload file mẫu lên ElevenLabs, trả về voice_id clone hoàn chỉnh."""
    if not settings.elevenlabs_api_key:
        raise VoiceCloneError("Chưa cấu hình ELEVENLABS_API_KEY — thêm vào .env để clone giọng thật")
    if not samples:
        raise VoiceCloneError("Cần ít nhất 1 file mẫu giọng")
    files = [("files", (Path(p).name, Path(p).read_bytes(), "audio/mpeg")) for p in samples]
    r = httpx.post(
        f"{ELEVENLABS_BASE_URL}/voices/add",
        headers={"xi-api-key": settings.elevenlabs_api_key},
        data={"name": str(name)[:100] or "voice"},
        files=files,
        timeout=120,
    )
    if r.status_code >= 400:
        raise VoiceCloneError(f"ElevenLabs {r.status_code}: {r.text[:300]}")
    data = r.json()
    voice_id = data.get("voice_id")
    if not voice_id:
        raise VoiceCloneError("ElevenLabs không trả về voice_id")
    return voice_id


def delete_elevenlabs_voice(voice_id: str) -> None:
    """Xoá voice clone trên ElevenLabs (best effort — lỗi cũng không chặn xoá local)."""
    if not settings.elevenlabs_api_key or not voice_id:
        return
    try:
        httpx.delete(f"{ELEVENLABS_BASE_URL}/voices/{voice_id}",
                     headers={"xi-api-key": settings.elevenlabs_api_key},
                     timeout=30)
    except Exception:
        pass


def gen_clone_tts(text: str, dest, *, voice_id: str, timeout: float = 300) -> Path:
    """Tạo MP3 bằng giọng clone ElevenLabs (voice_id)."""
    if not settings.elevenlabs_api_key:
        raise VoiceCloneError("Chưa cấu hình ELEVENLABS_API_KEY — thêm vào .env để dùng giọng clone")
    clean = _sanitize(text) or ""
    if not clean:
        raise TTSError("Text rỗng sau khi sanitize")
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = httpx.post(
        f"{ELEVENLABS_BASE_URL}/text-to-speech/{voice_id}",
        headers={"xi-api-key": settings.elevenlabs_api_key, "Accept": "audio/mpeg"},
        json={"text": clean, "model_id": ELEVEN_MODEL},
        timeout=timeout,
    )
    if r.status_code >= 400:
        raise VoiceCloneError(f"ElevenLabs {r.status_code}: {r.text[:300]}")
    dest.write_bytes(r.content)
    if not dest.exists() or dest.stat().st_size < 100:
        dest.unlink(missing_ok=True)
        raise VoiceCloneError("ElevenLabs trả về audio rỗng")
    return dest

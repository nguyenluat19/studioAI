"""TTS voice selection: auto theo giới tính nhân vật + cảm xúc."""

from app import tts


def test_voice_for_gender_maps_male_female():
    assert tts.voice_for_gender("nam") == "vi-VN-NamMinhNeural"
    assert tts.voice_for_gender("nữ") == "vi-VN-HoaiMyNeural"
    assert tts.voice_for_gender("Male") == "vi-VN-NamMinhNeural"
    assert tts.voice_for_gender("Female") == "vi-VN-HoaiMyNeural"


def test_voice_for_gender_default_when_unknown():
    assert tts.voice_for_gender(None) == "vi-VN-HoaiMyNeural"
    assert tts.voice_for_gender("không rõ") == "vi-VN-HoaiMyNeural"


def test_resolve_voice_auto_uses_gender():
    assert tts.resolve_voice("auto", "nam") == "vi-VN-NamMinhNeural"
    assert tts.resolve_voice("auto", "nữ") == "vi-VN-HoaiMyNeural"
    assert tts.resolve_voice("", "nam") == "vi-VN-NamMinhNeural"


def test_resolve_voice_explicit_wins():
    # User chọn giọng cụ thể -> dùng đúng giọng đó, bất kể giới tính nhân vật.
    assert tts.resolve_voice("vi-VN-NamMinhNeural", "nữ") == "vi-VN-NamMinhNeural"
    assert tts.resolve_voice("vi-VN-HoaiMyNeural", "nam") == "vi-VN-HoaiMyNeural"


def test_emotion_params():
    assert tts.emotion_params("vui vẻ") != ("+0%", "+0Hz", "+0%")
    assert tts.emotion_params("buồn bã") != ("+0%", "+0Hz", "+0%")
    assert tts.emotion_params("bình thường") == ("+0%", "+0Hz", "+0%")
    assert tts.emotion_params(None) == ("+0%", "+0Hz", "+0%")
    assert len(tts.emotion_params("vui vẻ")) == 3      # (rate, pitch, volume)


def test_emotion_params_volume_whisper_vs_angry():
    whisper = tts.emotion_params("thì thầm")
    angry = tts.emotion_params("tức giận")
    assert whisper[2] == "-25%"                        # thì thầm phải nhỏ giọng
    assert angry[2] == "+12%"                         # tức giận to tiếng
    assert tts.emotion_params("crying")[0] == "-15%"  # alias tiếng Anh
    assert tts.emotion_params("tuc gian")[0] == "+6%" # không dấu — phải khớp
    assert tts.emotion_params("emotion lạ không có") == ("+0%", "+0Hz", "+0%")  # fallback an toàn


def test_emotion_cue_en():
    assert tts.emotion_cue_en("vui vẻ") == "joyful, warm smile"
    assert tts.emotion_cue_en("Tức Giận") == "angry, irritated"   # hoa/thường + dấu
    assert tts.emotion_cue_en(None) == "calm, natural"
    assert tts.emotion_cue_en("không khớp gì cả") == "calm, natural"


def test_sanitize_adds_final_punctuation():
    assert tts._sanitize("Xin chào bạn") == "Xin chào bạn."
    assert tts._sanitize("Trời đẹp quá!") == "Trời đẹp quá!"        # giữ nguyên dấu câu có sẵn
    assert tts._sanitize("(không kèo thoại)") == ""                  # ngoặc loại bỏ → rỗng
    assert tts._sanitize("Hi") == ""                              # ngắn quá → rỗng


def test_gender_of_character_matches_by_name():
    chars = [
        {"tên": "Lan", "giới_tính": "nữ"},
        {"tên": "Minh", "giới_tính": "nam"},
    ]
    assert tts.gender_of_character("Lan", chars) == "nữ"
    assert tts.gender_of_character("Minh", chars) == "nam"
    assert tts.gender_of_character("Lan và Minh", chars) in ("nữ", "nam")
    assert tts.gender_of_character("Người lạ", chars) is None
    assert tts.gender_of_character("", chars) is None


def test_language_english_voices():
    assert tts.resolve_voice("auto", "nữ", language="en") == "en-US-AriaNeural"
    assert tts.resolve_voice("auto", "nam", language="en") == "en-US-GuyNeural"
    assert tts.resolve_voice("auto", None, language="en") == "en-US-AriaNeural"
    # Giọng tiếng Việt chọn trong bản English -> tự bám về giọng English cùng giới tính
    assert tts.resolve_voice("vi-VN-HoaiMyNeural", "nữ", language="en") == "en-US-AriaNeural"
    assert tts.resolve_voice("vi-VN-NamMinhNeural", "nam", language="en") == "en-US-GuyNeural"


def test_language_vietnamese_unchanged():
    assert tts.resolve_voice("auto", "nữ", language="vi") == "vi-VN-HoaiMyNeural"
    assert tts.resolve_voice("vi-VN-NamMinhNeural", "nam", language="vi") == "vi-VN-NamMinhNeural"


def test_list_voices_filter_by_language():
    ids_vi = {v["id"] for v in tts.list_voices("vi")}
    ids_en = {v["id"] for v in tts.list_voices("en")}
    assert "vi-VN-HoaiMyNeural" in ids_vi and "en-US-AriaNeural" not in ids_vi
    assert "en-US-GuyNeural" in ids_en and "vi-VN-NamMinhNeural" not in ids_en
    assert tts.VOICE_AUTO in ids_vi and tts.VOICE_AUTO in ids_en


def test_norm_lang_aliases():
    assert tts.norm_lang("English") == "en"
    assert tts.norm_lang("tiếng anh") == "en"
    assert tts.norm_lang("Tiếng Việt") == "vi"
    assert tts.norm_lang(None) == "vi"
    assert tts.norm_lang("??") == "vi"

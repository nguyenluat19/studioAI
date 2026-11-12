"""Guard: mọi cảnh phải dùng chung ảnh nhân vật tham chiếu và identity lock."""
from pathlib import Path

from app import autopipeline


class FakeJob:
    def __init__(self):
        self.job_id = "j1"
        self.user_id = 1
        self.aspect_ratio = "9:16"
        self.character_image_url = ""
        self.use_tts = False
        self.voice = "native"
        self.language = "vi"
        self.duration = 8
        self.idea = "test idea"
        self.selections = {"image_generate": "img-model", "video_i2v": "minimax-h3-768p", "llm": "llm"}

    def update(self, **_kwargs):
        return None

    def is_cancelled(self):
        return False


class FakeDB:
    def get(self, *_args):
        return None


class FakeModel:
    max_clip_seconds = 4
    step = "video_i2v"


def _plan():
    return {
        "character_bible": {"mô_tả": "Vietnamese woman", "khuôn_mặt": "round face, brown eyes",
                            "tóc": "black hair", "trang_phúc": "red swimsuit"},
        "nhân_vật": [{"tên": "Lan", "giới_tính": "nữ", "mô_tả": "same woman"}],
        "style_bible": {},
        "các_cảnh": [
            {"stt": 1, "thời_lượng_giây": 4, "loại_shot": "MS", "góc_máy": "front",
             "hành_động": "walks", "biểu_cảm": "happy", "thoại": "xin chào",
             "tỉ_lệ_khung_hình": "9:16"},
            {"stt": 2, "thời_lượng_giây": 4, "loại_shot": "CU", "góc_máy": "close",
             "hành_động": "turns", "biểu_cảm": "smile", "thoại": "xin chào nữa",
             "tỉ_lệ_khung_hình": "9:16"},
        ],
    }


def test_keyframes_share_character_reference(monkeypatch):
    captured = []

    def fake_gen_image(prompt, dest, **kwargs):
        captured.append({"prompt": prompt, "reference": kwargs.get("reference"), "dest": Path(dest)})
        Path(dest).write_bytes(b"\x89PNG\r\n\x1a\n")
        return dest

    monkeypatch.setattr(autopipeline.vilao_image, "gen_image", fake_gen_image)
    monkeypatch.setattr(autopipeline.adminmodels, "creds",
                        lambda _db, model_id: {"base_url": "https://api.test", "api_key": "k",
                                               "model_name": model_id})
    monkeypatch.setattr(autopipeline, "resolve", lambda _url: None)
    monkeypatch.setattr(autopipeline.pricing, "catalog", lambda: {})

    keyframes = autopipeline._run_keyframing(FakeJob(), _plan(), FakeDB())

    assert len(captured) == 2
    assert captured[0]["reference"] is None
    assert captured[1]["reference"] == captured[0]["dest"]
    assert all("IDENTITY LOCK" in item["prompt"] for item in captured)
    assert keyframes[0]["identity_lock"] == keyframes[1]["identity_lock"]
    assert keyframes[1]["character_reference_url"]


def test_keyframing_fails_when_no_reference_can_be_made(monkeypatch):
    def failing_gen_image(*_args, **_kwargs):
        raise autopipeline.vilao_image.ImageError("gateway down")

    monkeypatch.setattr(autopipeline.vilao_image, "gen_image", failing_gen_image)
    monkeypatch.setattr(autopipeline.adminmodels, "creds",
                        lambda _db, model_id: {"base_url": "https://api.test", "api_key": "k",
                                               "model_name": model_id})
    monkeypatch.setattr(autopipeline, "resolve", lambda _url: None)
    monkeypatch.setattr(autopipeline.pricing, "catalog", lambda: {})

    try:
        autopipeline._run_keyframing(FakeJob(), _plan(), FakeDB())
    except ValueError as e:
        assert "nhân vật" in str(e)
    else:
        raise AssertionError("phải dừng khi không tạo được ảnh tham chiếu")


def test_rendering_uses_per_chunk_first_frame(monkeypatch):
    """Mỗi chunk video phải bắt đầu từ keyframe của chính nó — không dùng chung
    một ảnh cho mọi chunk (nguyên nhân lặp cảnh trong thành phẩm)."""
    captured = []

    def fake_generate(prompt, dest, **kwargs):
        captured.append({"first_frame": kwargs.get("first_frame"), "prompt": prompt})
        Path(dest).write_bytes(b"\x00" * 2048)
        return Path(dest)

    monkeypatch.setattr(autopipeline.minimax, "generate", fake_generate)
    monkeypatch.setattr(autopipeline, "resolve", lambda u: Path(u) if u else None)
    monkeypatch.setattr(autopipeline, "get_model", lambda _mid: FakeModel())
    monkeypatch.setattr(autopipeline.pricing, "catalog", lambda: {})

    keyframes = [
        {"stt": 1, "thời_lượng_giây": 4, "image_url": "/media/outputs/k1.png",
         "identity_lock": "LOCK", "video_prompt": "scene one", "thoại": "Xin chào mọi người"},
        {"stt": 2, "thời_lượng_giây": 4, "image_url": "/media/outputs/k2.png",
         "identity_lock": "LOCK", "video_prompt": "scene two", "thoại": "Hôm nay mình nấu bún chả"},
    ]
    job = FakeJob()
    autopipeline._run_rendering(job, keyframes, FakeDB())

    assert len(captured) == 2
    assert captured[0]["first_frame"] == Path("/media/outputs/k1.png")
    assert captured[1]["first_frame"] == Path("/media/outputs/k2.png")
    # Câu thoại của kịch bản phải nằm trong prompt video (Veo nói đúng lời kịch bản)
    assert "tiếng Việt" in captured[0]["prompt"]
    assert "Xin chào mọi người" in captured[0]["prompt"]
    assert "IDENTITY LOCK" in captured[0]["prompt"] or "LOCK" in captured[0]["prompt"]


def test_rendering_fails_closed_when_keyframe_missing(monkeypatch):
    called = []
    monkeypatch.setattr(autopipeline.minimax, "generate", lambda *a, **k: called.append(True))
    monkeypatch.setattr(autopipeline, "resolve", lambda _url: None)
    monkeypatch.setattr(autopipeline, "get_model", lambda _mid: FakeModel())
    monkeypatch.setattr(autopipeline.pricing, "catalog", lambda: {})
    with __import__("pytest").raises(ValueError, match="Không tìm thấy ảnh keyframe"):
        autopipeline._gen_scene_video(
            FakeJob(), {"stt": 1, "thời_lượng_giây": 4, "image_url": "/media/outputs/missing.png",
                       "video_prompt": "keep exact image"}, FakeDB(), ci=0, total_scenes=1,
            video_model_id="minimax-h3-768p", model_price=0, per_scene_sec=4)
    assert called == []


def test_rendering_english_dialogue_instruction(monkeypatch):
    captured = []

    def fake_generate(prompt, dest, **kwargs):
        captured.append({"prompt": prompt})
        Path(dest).write_bytes(b"\x00" * 2048)
        return Path(dest)

    monkeypatch.setattr(autopipeline.minimax, "generate", fake_generate)
    monkeypatch.setattr(autopipeline, "resolve", lambda u: Path(u) if u else None)
    monkeypatch.setattr(autopipeline, "get_model", lambda _mid: FakeModel())
    monkeypatch.setattr(autopipeline.pricing, "catalog", lambda: {})

    keyframes = [{"stt": 1, "thời_lượng_giây": 4, "image_url": "/media/outputs/k1.png",
                  "identity_lock": "LOCK", "video_prompt": "scene one",
                  "thoại": "Today I cook bun cha"}]
    job = FakeJob()
    job.language = "en"
    autopipeline._run_rendering(job, keyframes, FakeDB())

    assert "spoken in English" in captured[0]["prompt"]
    assert "Today I cook bun cha" in captured[0]["prompt"]

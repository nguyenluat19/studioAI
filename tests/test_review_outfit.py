"""Chế độ review sản phẩm: 2 ảnh tham chiếu (nhân vật + bộ đồ), storyboard hook → biến hình → review → chi tiết."""
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from app import autopipeline, videopipeline, vilao_image
from app.config import settings

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


# ---------------------------------------------------------------------------
# Gateway ảnh giả: đếm số ảnh tham chiếu trong multipart
# ---------------------------------------------------------------------------
class FakeEdit(BaseHTTPRequestHandler):
    raw = b""
    status = 200

    def do_POST(self):
        FakeEdit.raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if FakeEdit.status != 200:
            return self._send(FakeEdit.status, {"error": "reject"})
        self._send(200, {"data": [{"b64_json": base64.b64encode(PNG).decode()}]})

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def log_message(self, *a):
        pass


def _edit_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeEdit)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_gen_image_sends_multiple_references(tmp_path):
    srv = _edit_server()
    FakeEdit.status = 200
    base = f"http://127.0.0.1:{srv.server_port}"
    char = tmp_path / "char.png"; char.write_bytes(PNG)
    outfit = tmp_path / "outfit.png"; outfit.write_bytes(PNG)
    try:
        dest = tmp_path / "out.png"
        vilao_image.gen_image("dress her", dest, base_url=base, api_key="k", model="m",
                              references=[char, outfit])
        assert dest.exists()
        assert FakeEdit.raw.count(b'name="image[]"') == 2
    finally:
        srv.shutdown()


def test_gen_image_multi_reference_rejected(tmp_path):
    srv = _edit_server()
    FakeEdit.status = 400
    base = f"http://127.0.0.1:{srv.server_port}"
    char = tmp_path / "char.png"; char.write_bytes(PNG)
    outfit = tmp_path / "outfit.png"; outfit.write_bytes(PNG)
    try:
        with pytest.raises(vilao_image.MultiReferenceUnsupported):
            vilao_image.gen_image("dress her", tmp_path / "x.png", base_url=base, api_key="k",
                                  model="m", references=[char, outfit])
    finally:
        FakeEdit.status = 200
        srv.shutdown()


# ---------------------------------------------------------------------------
# Storyboard review mode
# ---------------------------------------------------------------------------
class _FakeLLMModel:
    id = "llm-1"
    step = "llm"
    enabled = True


def _storyboard_json(scenes):
    return {"content": json.dumps({
        "character_bible": {"mô_tả": "woman", "khuôn_mặt": "round face",
                            "tóc": "black", "trang_phúc": "black shirt"},
        "outfit_bible": {"mô_tả": "red dress", "màu_sắc": "red", "chất_liệu": "silk"},
        "nhân_vật": [{"tên": "Lan", "giới_tính": "nữ", "mô_tả": "same woman"}],
        "style_bible": {"ánh_sáng": "soft"},
        "các_cảnh": scenes,
    })}


def test_plan_storyboard_review_mode(monkeypatch):
    scenes = [
        {"stt": 1, "thời_lượng_giây": 3, "giai_đoạn": "hook", "thoại": "Đoán xem tôi mặc gì?",
         "loại_shot": "MS", "góc_máy": "front", "hành_động": "smiles", "biểu_cảm": "curious",
         "image_prompt": "p1", "video_prompt": "v1"},
        {"stt": 2, "thời_lượng_giây": 3, "giai_đoạn": "biến hình", "thoại": "Nhìn này!",
         "loại_shot": "MS", "góc_máy": "spin", "hành_động": "spins", "biểu_cảm": "surprised",
         "image_prompt": "p2", "video_prompt": "v2"},
        {"stt": 3, "thời_lượng_giây": 3, "giai_đoạn": "review", "thoại": "Vải mát, form chuẩn",
         "loại_shot": "CU", "góc_máy": "close", "hành_động": "talks", "biểu_cảm": "happy",
         "image_prompt": "p3", "video_prompt": "v3"},
        {"stt": 4, "thời_lượng_giây": 3, "giai_đoạn": "chi tiết sản phẩm", "thoại": "Chốt đơn thôi!",
         "loại_shot": "CU", "góc_máy": "macro", "hành_động": "detail", "biểu_cảm": "",
         "image_prompt": "p4", "video_prompt": "v4"},
    ]
    monkeypatch.setattr(videopipeline, "get_model", lambda _mid: _FakeLLMModel())
    monkeypatch.setattr(videopipeline.ai, "chat", lambda *a, **k: _storyboard_json(scenes))

    plan = videopipeline.plan_storyboard(
        "review bộ đồ", "llm-1", duration_seconds=12, aspect_ratio="9:16",
        character_image_url="/media/uploads/c.png", language="vi",
        mode="review_outfit", outfit_image_url="/media/uploads/o.png", hook_seconds=4)

    assert plan["mode"] == "review_outfit"
    assert plan["outfit_bible"]["source_of_truth"] == "user-uploaded product/garment image only"
    phases = [s["giai_đoạn"] for s in plan["các_cảnh"]]
    assert phases == ["hook", "bien_hinh", "review", "chi_tiet_san_pham"]
    assert plan["các_cảnh"][0]["thời_lượng_giây"] == 4  # hook đúng số giây user chọn
    assert sum(s["thời_lượng_giây"] for s in plan["các_cảnh"]) == 12


def test_plan_storyboard_standard_mode_has_no_phases(monkeypatch):
    scenes = [{"stt": 1, "thời_lượng_giây": 4, "thoại": "hi", "loại_shot": "MS",
               "góc_máy": "front", "hành_động": "walks", "biểu_cảm": "happy",
               "image_prompt": "p", "video_prompt": "v"}]
    monkeypatch.setattr(videopipeline, "get_model", lambda _mid: _FakeLLMModel())
    monkeypatch.setattr(videopipeline.ai, "chat", lambda *a, **k: _storyboard_json(scenes))

    plan = videopipeline.plan_storyboard("x", "llm-1", 4, "9:16", language="vi")
    assert plan["mode"] == "standard"
    assert plan["outfit_bible"] == {}
    assert plan["các_cảnh"][0]["giai_đoạn"] == ""


# ---------------------------------------------------------------------------
# Keyframing: ảnh tham chiếu theo từng giai đoạn
# ---------------------------------------------------------------------------
class FakeJob:
    mode = "review_outfit"

    def __init__(self, char_url, outfit_url):
        self.job_id = "j-review"
        self.user_id = 1
        self.aspect_ratio = "9:16"
        self.character_image_url = char_url
        self.outfit_image_url = outfit_url
        self.hook_seconds = 3
        self.use_tts = False
        self.voice = "native"
        self.language = "vi"
        self.duration = 12
        self.idea = "review"
        self.selections = {"image_generate": "img", "video_i2v": "minimax-h3-768p", "llm": "llm"}

    def update(self, **_kwargs):
        return None

    def is_cancelled(self):
        return False


class FakeDB:
    def get(self, *_args):
        return None


def _review_plan():
    return {
        "character_bible": {"trang_phúc": "black shirt"},
        "outfit_bible": {"mô_tả": "red dress"},
        "nhân_vật": [{"tên": "Lan", "giới_tính": "nữ"}],
        "style_bible": {},
        "các_cảnh": [
            {"stt": 1, "thời_lượng_giây": 3, "giai_đoạn": "hook", "loại_shot": "MS",
             "góc_máy": "front", "hành_động": "smiles", "biểu_cảm": "happy", "thoại": "hook",
             "tỉ_lệ_khung_hình": "9:16"},
            {"stt": 2, "thời_lượng_giây": 3, "giai_đoạn": "bien_hinh", "loại_shot": "MS",
             "góc_máy": "spin", "hành_động": "spins", "biểu_cảm": "surprised", "thoại": "wow",
             "tỉ_lệ_khung_hình": "9:16"},
            {"stt": 3, "thời_lượng_giây": 3, "giai_đoạn": "review", "loại_shot": "CU",
             "góc_máy": "close", "hành_động": "talks", "biểu_cảm": "happy", "thoại": "đẹp",
             "tỉ_lệ_khung_hình": "9:16"},
            {"stt": 4, "thời_lượng_giây": 3, "giai_đoạn": "chi_tiet_san_pham", "loại_shot": "CU",
             "góc_máy": "macro", "hành_động": "detail", "biểu_cảm": "", "thoại": "",
             "tỉ_lệ_khung_hình": "9:16"},
        ],
    }


def _make_upload(name: str, data: bytes = PNG) -> Path:
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    p = settings.uploads_dir / name
    p.write_bytes(data)
    return p


def test_review_keyframes_pick_references_by_phase(monkeypatch):
    from app.media import url_for
    char = _make_upload("review_char.png")
    outfit = _make_upload("review_outfit.png")
    captured = []

    def fake_gen_image(prompt, dest, **kwargs):
        refs = list(kwargs.get("references") or [])
        if kwargs.get("reference") is not None:
            refs.insert(0, kwargs["reference"])
        captured.append({"refs": refs, "prompt": prompt})
        Path(dest).write_bytes(PNG)
        return dest

    monkeypatch.setattr(autopipeline.vilao_image, "gen_image", fake_gen_image)
    monkeypatch.setattr(autopipeline.adminmodels, "creds",
                        lambda _db, _mid: {"base_url": "https://api.test", "api_key": "k",
                                           "model_name": "img"})
    monkeypatch.setattr(autopipeline, "resolve", lambda url: outfit if "outfit" in url else char)
    monkeypatch.setattr(autopipeline.pricing, "catalog", lambda: {})

    job = FakeJob(url_for(char), url_for(outfit))
    keyframes = autopipeline._run_keyframing(job, _review_plan(), FakeDB())

    assert [k["giai_đoạn"] for k in keyframes] == ["hook", "bien_hinh", "review", "chi_tiet_san_pham"]
    assert captured[0]["refs"] == [char, outfit]
    assert captured[1]["refs"] == [char, outfit]
    assert captured[2]["refs"] == [char, outfit]
    assert captured[3]["refs"] == [outfit]
    assert "outfit" in captured[0]["prompt"].lower()
    assert "PRODUCT REFERENCE LOCK" in captured[3]["prompt"]
    assert keyframes[0]["product_reference_locked"] is True
    assert keyframes[0]["product_reference_url"] == url_for(outfit)
    assert keyframes[0]["character_reference_url"] == url_for(char)


def test_review_keyframing_requires_outfit(monkeypatch):
    job = FakeJob("/media/uploads/c.png", "")
    job.outfit_image_url = ""
    monkeypatch.setattr(autopipeline.pricing, "catalog", lambda: {})
    monkeypatch.setattr(autopipeline.adminmodels, "creds",
                        lambda _db, _mid: {"base_url": "https://api.test", "api_key": "k",
                                           "model_name": "img"})
    monkeypatch.setattr(autopipeline, "resolve", lambda _u: Path("x.png"))

    with pytest.raises(ValueError, match="ảnh bộ đồ"):
        autopipeline._run_keyframing(job, _review_plan(), FakeDB())


# ---------------------------------------------------------------------------
# Rendering: cảnh chi tiết sản phẩm không có nhân vật
# ---------------------------------------------------------------------------
class FakeVideoModel:
    max_clip_seconds = 4
    step = "video_i2v"


def test_rendering_product_scene_has_no_identity(monkeypatch):
    captured = []

    def fake_generate(prompt, dest, **kwargs):
        captured.append({"prompt": prompt, "first_frame": kwargs.get("first_frame"),
                         "subject_reference": kwargs.get("subject_reference")})
        Path(dest).write_bytes(b"\x00")
        return Path(dest)

    monkeypatch.setattr(autopipeline.minimax, "generate", fake_generate)
    monkeypatch.setattr(autopipeline, "resolve", lambda u, *_args: Path(u) if u else None)
    monkeypatch.setattr(autopipeline, "get_model", lambda _mid: FakeVideoModel())
    monkeypatch.setattr(autopipeline.pricing, "catalog", lambda: {})

    keyframes = [
        {"stt": 1, "thời_lượng_giây": 4, "giai_đoạn": "review", "image_url": "/media/outputs/k1.png",
         "character_reference_url": "/media/uploads/c.png", "product_reference_url": "/media/uploads/o.png",
         "identity_lock": "IDENTITY LOCK: keep face", "video_prompt": "scene one", "thoại": "đẹp",
         "product_reference_locked": True},
        {"stt": 2, "thời_lượng_giây": 4, "giai_đoạn": "chi_tiet_san_pham",
         "image_url": "/media/outputs/k2.png", "product_reference_url": "/media/uploads/o.png",
         "identity_lock": "IDENTITY LOCK: keep face",
         "video_prompt": "fabric detail", "thoại": ""},
    ]
    job = FakeJob("/media/uploads/c.png", "/media/uploads/o.png")
    autopipeline._run_rendering(job, keyframes, FakeDB())

    assert "IDENTITY LOCK" not in captured[1]["prompt"]
    assert "Animate the supplied product image only" in captured[1]["prompt"]
    assert "fabric detail movement only." in captured[1]["prompt"]
    assert captured[1]["first_frame"] == Path("/media/outputs/k2.png")
    assert captured[0]["subject_reference"] == Path("/media/uploads/c.png")
    assert captured[1]["subject_reference"] == Path("/media/uploads/o.png")
    assert "Preserve the exact same person" in captured[0]["prompt"]
    assert "Animate the supplied product image only" in captured[1]["prompt"]
    assert "scene one movement only." in captured[0]["prompt"]
    assert "fabric detail movement only." in captured[1]["prompt"]
    assert captured[0]["subject_reference"] != captured[1]["subject_reference"]


def test_scene_video_prompt_locks_exact_product_and_mouth_audio_modes():
    job = FakeJob("/media/uploads/c.png", "/media/uploads/o.png")
    kf = {"giai_đoạn": "review", "source_image_prompt": "exact image prompt",
          "video_prompt": "different video prompt", "thoại": "Áo này rất đẹp",
          "character_reference_url": "/media/uploads/c.png", "product_reference_locked": True}
    prompt = autopipeline._scene_video_prompt(job, kf)
    assert prompt.startswith("Use the supplied first frame as the immutable visual source")
    assert "Preserve the exact same person" in prompt
    assert "product, objects, composition, and background" in prompt
    assert "different video prompt movement only." in prompt

    job.use_tts = True
    job.voice = "vi-VN-HoaiMyNeural"
    assert autopipeline._scene_video_prompt(job, kf) == prompt

    product_kf = {"giai_đoạn": "chi_tiet_san_pham", "source_image_prompt": "product image prompt"}
    product_prompt = autopipeline._scene_video_prompt(job, product_kf)
    assert "Animate the supplied product image only" in product_prompt
    assert "Subtle natural movement" in product_prompt
    assert "Language selected by user: vi" in product_prompt


def test_scene_video_prompt_uses_video_motion_prompt_first():
    job = FakeJob("", "")
    prompt = autopipeline._scene_video_prompt(job, {
        "source_image_prompt": "static image description",
        "video_prompt": "camera slowly tracks as the subject turns",
    })
    assert "camera slowly tracks as the subject turns movement only." in prompt
    assert "Use the supplied first frame as the immutable visual source" in prompt


def test_tts_mux_maps_only_external_audio(monkeypatch, tmp_path):
    video = tmp_path / "clip.mp4"; video.write_bytes(b"video")
    audio = tmp_path / "voice.mp3"; audio.write_bytes(b"audio")
    captured = {}
    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        Path(cmd[-1]).write_bytes(b"muxed")
        class R: returncode = 0; stderr = ""
        return R()
    monkeypatch.setattr("subprocess.run", fake_run)
    autopipeline._mux_tts_voiceover(video, audio, 4)
    assert video.read_bytes() == b"muxed"
    assert "0:v:0" in captured["cmd"] and "1:a:0" in captured["cmd"]
    assert "-shortest" in captured["cmd"]


# ---------------------------------------------------------------------------
# API validation
# ---------------------------------------------------------------------------
def test_pipeline_review_requires_both_images(client, make_user):
    headers, _ = make_user()
    payload = {"idea": "review bộ đồ", "mode": "review_outfit",
               "character_image_url": "/media/uploads/c.png"}
    r = client.post("/api/assistant/pipeline", headers=headers, json=payload)
    assert r.status_code == 422
    assert "bộ đồ" in r.text

    payload["character_image_url"] = ""
    payload["outfit_image_url"] = "/media/uploads/o.png"
    r = client.post("/api/assistant/pipeline", headers=headers, json=payload)
    assert r.status_code == 422


def test_pipeline_rejects_unknown_mode(client, make_user):
    headers, _ = make_user()
    r = client.post("/api/assistant/pipeline", headers=headers, json={
        "idea": "review", "mode": "khong_hop_le"})
    assert r.status_code == 422

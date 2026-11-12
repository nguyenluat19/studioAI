"""Tool chỉ tạo clip phôi — pipeline KHÔNG dựng video final, tự lưu raw template."""
import threading

from app import autopipeline


class _FakeDB:
    """Substitute for SessionLocal that supports just enough for credits/pricing calls."""
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def get(self, _model, _id):
        return None

    def execute(self, *_a, **_kw):
        return _FakeResult()

    def scalars(self, *_a, **_kw):
        return []

    def scalar(self, *_a, **_kw):
        return 0

    def add(self, _o):
        pass

    def commit(self):
        pass

    def rollback(self):
        pass

    def refresh(self, _o):
        pass


class _FakeResult:
    rowcount = 0


class FakeJob:
    def __init__(self):
        self.job_id = "j-raw"
        self.user_id = 1
        self.duration = 20
        self.aspect_ratio = "9:16"
        self.idea = "raw test"
        self.character_image_url = ""
        self.mode = "standard"
        self.outfit_image_url = None
        self.hook_seconds = 3
        self.language = "vi"
        self.voice = "native"
        self.use_tts = False
        self.selections = {"llm": "l", "image_generate": "i", "video_i2v": "v"}
        self.status = "queued"
        self.progress = 0
        self.step = ""
        self.error = ""
        self.result = None
        self.created_at = "t"
        self.updated_at = "t"
        self.cancelled = False
        self._lock = threading.Lock()

    def update(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

    def is_cancelled(self):
        return self.cancelled

    def cancel(self):
        self.cancelled = True
        self.status = "cancelled"

    def to_dict(self):
        return {"job_id": self.job_id, "status": self.status, "error": self.error,
                "result": self.result, "progress": self.progress, "step": self.step}


_PLAN = {"các_cảnh": [{"stt": 1, "thời_lượng_giây": 4}], "tổng_số_cảnh": 1}


def _setup(monkeypatch, keyframes):
    calls = []
    monkeypatch.setattr(autopipeline, "_run_planning", lambda job: _PLAN)
    monkeypatch.setattr(autopipeline, "_run_keyframing", lambda job, plan, db: keyframes)
    monkeypatch.setattr(autopipeline, "_run_rendering", lambda job, kfs, db: kfs)
    monkeypatch.setattr(autopipeline, "SessionLocal", _FakeDB)
    monkeypatch.setattr(autopipeline, "save_pipeline_template",
                        lambda job, db: calls.append("saved") or {"id": 42, "title": "t"})
    return calls


def test_pipeline_completes_with_raw_clips(monkeypatch):
    keyframes = [{"stt": 1, "video_url": "/media/outputs/v.mp4", "image_url": "/media/outputs/i.png"}]
    calls = _setup(monkeypatch, keyframes)

    job = FakeJob()
    autopipeline._run_full_pipeline(job)

    assert job.status == "done"
    assert job.result["clip_count"] == 1
    assert "final_url" not in job.result
    assert "saved" in calls  # dự án raw phải được tự động lưu (kể cả lưu theo từng bước công đoạn)
    assert calls.count("saved") >= 2  # ít nhất: lúc bắt đầu và lúc xong


def test_pipeline_fails_when_all_clips_fail(monkeypatch):
    keyframes = [{"stt": 1, "video_url": "", "image_url": "/media/outputs/i.png", "error": "boom"}]
    _setup(monkeypatch, keyframes)

    job = FakeJob()
    autopipeline._run_full_pipeline(job)

    assert job.status == "failed"
    assert job.error


def test_pipeline_images_only_skips_render(monkeypatch):
    keyframes = [{"stt": 1, "image_url": "/media/outputs/i.png", "thời_lượng_giây": 4}]
    render_calls = []

    monkeypatch.setattr(autopipeline, "_run_planning", lambda job: _PLAN)
    monkeypatch.setattr(autopipeline, "_run_keyframing", lambda job, plan, db: keyframes)
    monkeypatch.setattr(autopipeline, "_run_rendering",
                        lambda job, kfs, db: render_calls.append(1) or kfs)
    monkeypatch.setattr(autopipeline, "SessionLocal", _FakeDB)
    monkeypatch.setattr(autopipeline, "save_pipeline_template",
                        lambda job, db: {"id": 42, "title": "t"})

    job = FakeJob()
    job.mode = "images_only"
    autopipeline._run_full_pipeline(job)

    assert job.status == "done"
    assert render_calls == []                       # KHÔNG gen video
    assert job.result.get("images_only") is True
    assert job.result.get("clip_count") == 0


def test_pipeline_images_only_fails_when_all_images_fail(monkeypatch):
    keyframes = [{"stt": 1, "image_url": "", "thời_lượng_giây": 4, "image_error": "model ảnh lỗi"}]

    monkeypatch.setattr(autopipeline, "_run_planning", lambda job: _PLAN)
    monkeypatch.setattr(autopipeline, "_run_keyframing", lambda job, plan, db: keyframes)
    monkeypatch.setattr(autopipeline, "_run_rendering", lambda job, kfs, db: kfs)
    monkeypatch.setattr(autopipeline, "SessionLocal", _FakeDB)
    monkeypatch.setattr(autopipeline, "save_pipeline_template",
                        lambda job, db: {"id": 42, "title": "t"})

    job = FakeJob()
    job.mode = "images_only"
    autopipeline._run_full_pipeline(job)

    assert job.status == "failed"
    assert "ảnh" in (job.error or "").lower()


def _single_clip_setup(monkeypatch, keyframes_list):
    monkeypatch.setattr(autopipeline, "SessionLocal", _FakeDB)
    monkeypatch.setattr(autopipeline, "save_pipeline_template",
                        lambda job, db: {"id": 42, "title": "t"})
    monkeypatch.setattr(autopipeline, "get_model",
                        lambda mid: type("M", (), {"step": "video_i2v"})())
    monkeypatch.setattr(autopipeline, "_gen_scene_video",
                        lambda job, kf, db, **kw: kf.update(video_url="/media/outputs/clip.mp4",
                                                            status="done"))
    return keyframes_list


def test_text_to_video_single_clip(monkeypatch):
    from app import videopipeline
    expanded = []

    def fake_expand(idea, model_id, **kw):
        expanded.append((idea, model_id))
        return "A cinematic golden-hour rice-paddy walk, slow dolly in, 35mm film look"

    monkeypatch.setattr(videopipeline, "expand_single_prompt", fake_expand)
    _single_clip_setup(monkeypatch, None)

    job = FakeJob()
    job.mode = "text_to_video"
    job.idea = "Cô gái trong váy hoa đi giữa cánh đồng lúa"
    job.character_image_url = ""
    autopipeline._run_full_pipeline(job)

    assert job.status == "done"
    assert job.result["clip_count"] == 1
    assert job.result["plan"]["single_clip"] is True
    assert expanded == [("Cô gái trong váy hoa đi giữa cánh đồng lúa", "l")]
    kf = job.result["keyframes"][0]
    assert kf["video_url"] == "/media/outputs/clip.mp4"
    assert kf["image_url"] == ""                                   # t2v không gửi ảnh đầu
    assert "golden-hour" in (kf["video_prompt"] or "")


def test_image_to_video_requires_image(monkeypatch):
    from app import videopipeline
    monkeypatch.setattr(videopipeline, "expand_single_prompt", lambda *a, **kw: "expanded prompt")
    _single_clip_setup(monkeypatch, None)

    job = FakeJob()
    job.mode = "image_to_video"
    job.character_image_url = ""
    job.idea = "test"
    autopipeline._run_full_pipeline(job)

    assert job.status == "failed"
    assert "ảnh" in (job.error or "").lower()


def test_image_to_video_with_image_ok(monkeypatch, tmp_path):
    from pathlib import Path
    from app import videopipeline
    fake_img = tmp_path / "me.png"
    fake_img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    monkeypatch.setattr(videopipeline, "expand_single_prompt", lambda *a, **kw: "push in dolly")
    monkeypatch.setattr(autopipeline, "resolve", lambda _url: fake_img)
    _single_clip_setup(monkeypatch, None)

    job = FakeJob()
    job.mode = "image_to_video"
    job.character_image_url = "/media/uploads/me.png"
    job.idea = "Bước vào khách sạn"
    autopipeline._run_full_pipeline(job)

    assert job.status == "done"
    kf = job.result["keyframes"][0]
    assert kf["video_url"] == "/media/outputs/clip.mp4"
    assert kf["image_url"] == "/media/uploads/me.png"               # i2v gửi ảnh làm first frame


def test_retry_failed_scenes_regenerates_only_failures(monkeypatch):
    job = FakeJob()
    job.status = "done"
    job.result = {"keyframes": [
        {"stt": 1, "thời_lượng_giây": 4, "video_url": "/media/outputs/v.mp4", "image_url": "/media/outputs/i.png"},
        {"stt": 2, "thời_lượng_giây": 4, "video_url": "", "image_url": "/media/outputs/j.png", "error": "gateway 503"},
    ], "saved_template_id": None}
    monkeypatch.setattr(autopipeline, "get_job", lambda job_id: job)
    monkeypatch.setattr(autopipeline, "get_model",
                        lambda mid: type("M", (), {"step": "video_i2v"})())
    monkeypatch.setattr(autopipeline, "SessionLocal", _FakeDB)
    monkeypatch.setattr(autopipeline, "_gen_scene_video",
                        lambda j, kf, db, **kw: kf.update(video_url="/media/outputs/k.mp4", status="done"))

    out = autopipeline.retry_failed_scenes("j-raw")

    assert out["retried"] == 1 and out["succeeded"] == 2 and out["total"] == 2
    kfs = job.result["keyframes"]
    assert kfs[0]["video_url"] == "/media/outputs/v.mp4"      # cảnh đã có clip KHÔNG gen lại
    assert kfs[1]["video_url"] == "/media/outputs/k.mp4"      # cảnh lỗi đã có clip
    assert kfs[1]["status"] == "done"
    assert job.status == "done"
    assert "2/2" in job.step

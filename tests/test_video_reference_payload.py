import base64
import json
from pathlib import Path

from app import minimax


def test_minimax_payload_contains_each_scene_first_frame_and_subject_reference(tmp_path):
    frame = tmp_path / "scene-frame.png"
    frame.write_bytes(b"frame-bytes")
    subject = tmp_path / "subject.png"
    subject.write_bytes(b"subject-bytes")

    payload = minimax.build_payload(
        "scene motion", 4, "9:16", "768P", first_frame=frame,
        subject_reference=subject, model="minimax-h3-768p",
    )

    assert payload["content"][0] == {"type": "text", "text": "scene motion"}
    assert payload["content"][1]["role"] == "first_frame"
    assert base64.b64decode(payload["content"][1]["image_url"]["url"].split(",", 1)[1]) == b"frame-bytes"
    assert payload["content"][2]["role"] == "subject_reference"
    assert base64.b64decode(payload["content"][2]["image_url"]["url"].split(",", 1)[1]) == b"subject-bytes"


def test_openai_query_prefers_gateway_returned_video_url():
    class Response:
        status_code = 200
        text = ""
        def json(self):
            return {"status": "completed", "video_url": "https://cdn.test/result.mp4"}

    class Client:
        def get(self, *_args, **_kwargs):
            return Response()

    state, url, _raw = minimax._openai_query(
        Client(), "task-1", base="https://gateway.test", api_key="key", model="video-model")

    assert state == "ok"
    assert url == "https://cdn.test/result.mp4"


def test_openai_query_waits_until_video_url_is_ready():
    class Response:
        status_code = 200
        text = ""
        def json(self):
            return {"status": "processing", "video_url": "https://cdn.test/not-ready.mp4"}

    class Client:
        def get(self, *_args, **_kwargs):
            return Response()

    state, url, _raw = minimax._openai_query(
        Client(), "task-1", base="https://gateway.test", api_key="key", model="video-model")

    assert state == "pending"
    assert url is None


def test_openai_video_payload_contains_exact_first_frame_and_subject_reference(tmp_path):
    image = tmp_path / "keyframe.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"pixels")
    subject = tmp_path / "character.png"
    subject.write_bytes(b"\x89PNG\r\n\x1a\n" + b"character pixels")
    captured = {}

    class Response:
        status_code = 200
        text = ""
        def json(self):
            return {"id": "task-1"}

    class Client:
        def post(self, url, **kwargs):
            captured.update(kwargs["json"])
            return Response()

    monkeypatcher = __import__("pytest").MonkeyPatch()
    monkeypatcher.setattr(minimax, "_openai_seconds", lambda *a: 4)
    try:
        task_id = minimax._openai_create(
            Client(), base="https://gateway.test", api_key="secret", model="video-i2v",
            prompt="keep the exact keyframe", duration=4, ratio="9:16", first_frame=image,
            subject_reference=subject)
    finally:
        monkeypatcher.undo()
    assert task_id == "task-1"
    assert captured["input_image"].startswith("data:image/png;base64,")
    assert base64.b64decode(captured["input_image"].split(",", 1)[1]).startswith(b"\x89PNG")
    assert captured["subject_reference"].startswith("data:image/png;base64,")
    assert base64.b64decode(captured["subject_reference"].split(",", 1)[1]).endswith(b"character pixels")

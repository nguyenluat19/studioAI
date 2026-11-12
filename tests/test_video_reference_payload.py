import base64
import json
from pathlib import Path

from app import minimax


def test_openai_video_payload_contains_exact_first_frame_data_uri(tmp_path):
    image = tmp_path / "keyframe.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"pixels")
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
            prompt="keep the exact keyframe", duration=4, ratio="9:16", first_frame=image)
    finally:
        monkeypatcher.undo()
    assert task_id == "task-1"
    assert captured["input_image"].startswith("data:image/png;base64,")
    assert base64.b64decode(captured["input_image"].split(",", 1)[1]).startswith(b"\x89PNG")

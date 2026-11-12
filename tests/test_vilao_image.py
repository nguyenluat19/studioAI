"""Gateway ảnh kiểu vilao.ai: POST /images/generations -> GET url -> lưu file."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from app import vilao_image


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


class FakeImage(BaseHTTPRequestHandler):
    log = []
    b64_mode = False
    edits_ok = True

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        if self.path == "/images/edits":
            FakeImage.log.append(("POST", self.path, self.headers.get("Content-Type", "")))
            if not FakeImage.edits_ok:
                return self._send(404, {})
            self._send(200, {"data": [{"b64_json": __import__("base64").b64encode(PNG).decode()}]})
            return None
        body = json.loads(raw)
        FakeImage.log.append(("POST", self.path, body))
        if self.path != "/images/generations":
            return self._send(404, {})
        if FakeImage.b64_mode:
            self._send(200, {"data": [{"b64_json": __import__("base64").b64encode(PNG).decode()}]})
        else:
            self._send(200, {"data": [{"url": f"http://127.0.0.1:{self.server.server_port}/img/img1"}]})
        return None

    def do_GET(self):
        if self.path == "/img/img1":
            self.send_response(200); self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(PNG))); self.end_headers()
            self.wfile.write(PNG); return
        self._send(404, {})

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def log_message(self, *a):
        pass


def _srv():
    FakeImage.log = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeImage)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_gen_image_from_url():
    srv = _srv()
    base = f"http://127.0.0.1:{srv.server_port}"
    try:
        dest = Path(__import__("tempfile").mkdtemp()) / "k.png"
        out = vilao_image.gen_image("a cat", dest, base_url=base, api_key="k", model="m", ratio="9:16")
        assert out == dest and dest.exists() and dest.read_bytes().startswith(b"\x89PNG")
        assert FakeImage.log[0][1] == "/images/generations"
        assert FakeImage.log[0][2]["size"] == "1024x1792"
    finally:
        srv.shutdown()


def test_gen_image_from_b64():
    srv = _srv()
    FakeImage.b64_mode = True
    base = f"http://127.0.0.1:{srv.server_port}"
    try:
        dest = Path(__import__("tempfile").mkdtemp()) / "b.png"
        vilao_image.gen_image("a dog", dest, base_url=base, api_key="k", model="m", ratio="1:1")
        assert dest.read_bytes().startswith(b"\x89PNG")
    finally:
        FakeImage.b64_mode = False
        srv.shutdown()


def test_gen_image_missing_creds():
    with pytest.raises(vilao_image.ImageError):
        vilao_image.gen_image("x", Path("t.png"))


def test_gen_image_with_reference_uses_edits(tmp_path):
    srv = _srv()
    base = f"http://127.0.0.1:{srv.server_port}"
    ref = tmp_path / "ref.png"
    ref.write_bytes(PNG)
    try:
        dest = tmp_path / "with-ref.png"
        vilao_image.gen_image("same person", dest, base_url=base, api_key="k", model="m",
                              reference=ref)
        assert dest.exists()
        assert FakeImage.log[0][1] == "/images/edits"
        assert "multipart/form-data" in FakeImage.log[0][2]
    finally:
        srv.shutdown()


def test_reference_unsupported_does_not_fallback(tmp_path):
    srv = _srv()
    base = f"http://127.0.0.1:{srv.server_port}"
    ref = tmp_path / "ref.png"
    ref.write_bytes(PNG)
    FakeImage.edits_ok = False
    try:
        with pytest.raises(vilao_image.ReferenceImageUnsupported):
            vilao_image.gen_image("same person", tmp_path / "x.png", base_url=base,
                                  api_key="k", model="m", reference=ref)
        assert not any(row[1] == "/images/generations" for row in FakeImage.log)
    finally:
        FakeImage.edits_ok = True
        srv.shutdown()

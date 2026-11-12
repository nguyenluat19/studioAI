"""Local stand-ins for MiniMax-H3 (real HTTP, real mp4 bytes)."""
import json
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def make_video_bytes(audio=True, seconds=2) -> bytes:
    out = Path(tempfile.mkdtemp()) / "fake.mp4"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=s=320x568:d={seconds}:r=10"]
    cmd += ["-f", "lavfi", "-i", f"sine=d={seconds}", "-shortest", "-c:a", "aac"] if audio else []
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)]
    subprocess.run(cmd, check=True)
    return out.read_bytes()


class FakeMiniMax(BaseHTTPRequestHandler):
    """Behaviour is driven by class attributes so a test can flip modes."""
    video = b""
    log: list = []
    polls_before_done = 0
    style = "v2"            # v2: /v2/video_generation/{id}, status succeeded, content.url
                            # v1: only /v1/query/video_generation?task_id=, status Success + file_id
                            # openai_video: POST /videos, GET /videos/{id}?model= (gateway kiểu Veo)
    fail_task = False
    create_status = 200
    corrupt_file = False
    polls: dict = {}
    openai_model = "Veo-3.1"

    @classmethod
    def reset(cls):
        cls.log, cls.polls = [], {}
        cls.polls_before_done, cls.style, cls.fail_task = 0, "v2", False
        cls.create_status, cls.corrupt_file = 200, False

    def _send(self, code, obj=None, raw=None, ctype="application/json"):
        body = raw if raw is not None else json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        if self.headers.get("Content-Type", "").startswith("multipart/form-data"):
            body = {"multipart": True}
        else:
            body = json.loads(raw)
        FakeMiniMax.log.append(("POST", self.path, self.headers.get("Authorization"), body))
        if self.path == "/videos" and FakeMiniMax.style == "openai_video":
            tid = f"vid{len([l for l in FakeMiniMax.log if l[0] == 'POST'])}"
            FakeMiniMax.polls[tid] = 0
            return self._send(200, {"id": tid, "status": "queued"})
        if self.path != "/v2/video_generation" or FakeMiniMax.style == "openai_video":
            return self._send(404, {})   # gateway kiểu Veo: không có route MiniMax
        if FakeMiniMax.create_status != 200:
            return self._send(FakeMiniMax.create_status, {"error": "boom"})
        tid = f"task{len([l for l in FakeMiniMax.log if l[0] == 'POST'])}"
        FakeMiniMax.polls[tid] = 0
        self._send(200, {"task_id": tid})

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        FakeMiniMax.log.append(("GET", self.path, self.headers.get("Authorization"), None))
        host = f"http://127.0.0.1:{self.server.server_port}"
        if u.path.startswith("/files/"):
            return self._send(200, raw=b"junk" * 500 if FakeMiniMax.corrupt_file else FakeMiniMax.video,
                              ctype="video/mp4")
        if u.path == "/v1/files/retrieve":
            return self._send(200, {"file": {"download_url": f"{host}/files/{q['file_id'][0]}.mp4"}})
        if FakeMiniMax.style == "openai_video":
            if u.path == "/models":
                return self._send(200, {"data": [{"id": FakeMiniMax.openai_model,
                                                  "model_options": {"seconds": [4, 6, 8]}}]})
            if u.path.startswith("/videos/"):
                tid = u.path.rsplit("/", 1)[1]
                if tid not in FakeMiniMax.polls:
                    return self._send(404, {})
                FakeMiniMax.polls[tid] += 1
                if FakeMiniMax.fail_task:
                    return self._send(200, {"status": "failed"})
                if FakeMiniMax.polls[tid] <= FakeMiniMax.polls_before_done:
                    return self._send(200, {"status": "running"})
                return self._send(200, {"status": "completed",
                                        "url": f"{host}/files/{tid}.mp4",
                                        "video_url": f"{host}/files/{tid}.mp4"})
            return self._send(404, {})
        tid = None
        if FakeMiniMax.style == "v2" and u.path.startswith("/v2/video_generation/"):
            tid = u.path.rsplit("/", 1)[1]
        elif FakeMiniMax.style == "v1" and u.path == "/v1/query/video_generation":
            tid = q["task_id"][0]
        if tid is None or tid not in FakeMiniMax.polls:
            return self._send(404, {})
        FakeMiniMax.polls[tid] += 1
        if FakeMiniMax.fail_task:
            return self._send(200, {"status": "failed" if FakeMiniMax.style == "v2" else "Fail"})
        if FakeMiniMax.polls[tid] <= FakeMiniMax.polls_before_done:
            return self._send(200, {"status": "running" if FakeMiniMax.style == "v2" else "Processing"})
        if FakeMiniMax.style == "v2":
            return self._send(200, {"status": "succeeded", "content": {"url": f"{host}/files/{tid}.mp4"}})
        self._send(200, {"status": "Success", "file_id": tid, "base_resp": {"status_code": 0}})

    def log_message(self, *a):
        pass


def start_minimax(video: bytes | None = None):
    FakeMiniMax.video = video if video is not None else make_video_bytes()
    FakeMiniMax.reset()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeMiniMax)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv

"""Real processes: Redis + Celery worker + uvicorn + fake MimicMotion CLI. No mocks of our own code."""
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from tests.fakes import FakeMiniMax, start_minimax

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
FAKE_MM = Path(__file__).parent / "fixtures" / "fake_mimicmotion"
pytestmark = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("redis-server") and shutil.which("celery")),
                                reason="needs ffmpeg, redis-server and celery")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_http(url, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if httpx.get(url, timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(0.2)
    raise RuntimeError(f"{url} did not come up")


class Stack:
    def __init__(self, tmp):
        self.tmp, self.procs = tmp, {}
        self.rport, self.port = free_port(), free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.mm = start_minimax()
        self.env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp}/e2e.db", "STORAGE_DIR": str(tmp),
                    "SECRET_KEY": "e2e-secret-e2e-secret-e2e-secret-12", "ADMIN_PASSWORD": "adminpass123",
                    "SEPAY_API_KEY": "sepay-key", "REDIS_URL": f"redis://127.0.0.1:{self.rport}/0",
                    "MIMICMOTION_DIR": str(FAKE_MM), "MIMICMOTION_PYTHON": sys.executable,
                    "CELERY_ALWAYS_EAGER": "0", "REGISTER_PER_HOUR": "1000",
                    "VILAO_BASE_URL": "", "VILAO_API_KEY": "",
                    "MINIMAX_API_KEY": "mm-key", "MINIMAX_BASE_URL": f"http://127.0.0.1:{self.mm.server_port}",
                    "MINIMAX_POLL_SECONDS": "0.05", "PYTHONPATH": str(ROOT)}
        self.log = {}

    def start(self, name, cmd):
        self.log[name] = open(self.tmp / f"{name}.log", "w")
        self.procs[name] = subprocess.Popen(cmd, cwd=ROOT, env=self.env, stdout=self.log[name], stderr=subprocess.STDOUT)

    def stop(self, name):
        p = self.procs.pop(name, None)
        if p:
            p.terminate()
            try:
                p.wait(10)
            except subprocess.TimeoutExpired:
                p.kill()

    def logs(self, name):
        return (self.tmp / f"{name}.log").read_text()[-1500:]


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    st = Stack(tmp_path_factory.mktemp("e2e"))
    st.start("redis", ["redis-server", "--port", str(st.rport), "--save", "", "--appendonly", "no"])
    st.start("web", [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(st.port)])
    # same split run.py uses: many parallel API jobs on `ai`, one GPU job at a time on `gpu`
    st.start("worker", ["celery", "-A", "app.tasks.celery_app", "worker", "-n", "ai@%h", "-Q", "ai", "-c", "3",
                        "--loglevel=info"])
    st.start("gpuworker", ["celery", "-A", "app.tasks.celery_app", "worker", "-n", "gpu@%h", "-Q", "gpu", "-c", "1",
                           "--loglevel=info"])
    try:
        wait_http(st.base + "/api/health")
        end = time.time() + 30
        while "ready" not in st.logs("worker") and time.time() < end:
            time.sleep(0.3)
        assert "ready" in st.logs("worker"), st.logs("worker")
        yield st
    finally:
        for n in list(st.procs):
            st.stop(n)
        st.mm.shutdown()


def mk_user(st, name):
    r = httpx.post(st.base + "/api/auth/register", json={"username": name, "email": f"{name}@x.io",
                                                         "password": "password123",
                                                         "phone": "09" + str(20000000 + len(name) * 7 + abs(hash(name)) % 999999)})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def bal(st, h):
    return httpx.get(st.base + "/api/auth/me", headers=h).json()["credits_balance"]


def upload(st, h, name, data, mime):
    return httpx.post(st.base + "/api/uploads", headers=h, files={"file": (name, data, mime)}).json()["url"]


def fund(st, h, pkg="p100"):
    from tests.test_flow import AMOUNTS
    tx = httpx.post(st.base + "/api/billing/topup", headers=h, json={"amount_vnd": AMOUNTS[pkg]}).json()
    r = httpx.post(st.base + "/api/webhooks/payment", headers={"Authorization": "Apikey sepay-key"},
                   json={"transferType": "in", "transferAmount": tx["amount_vnd"],
                         "content": f"CK {tx['transaction_code']}"})
    assert r.json()["results"][0]["status"] == "success"


def sample_assets(st, h, tmp):
    png, mp4 = tmp / "c.png", tmp / "v.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=64x64",
                    "-frames:v", "1", str(png)], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=s=128x128:d=1:r=10",
                    str(mp4)], check=True)
    return upload(st, h, "c.png", png.read_bytes(), "image/png"), upload(st, h, "v.mp4", mp4.read_bytes(), "video/mp4")


def wait_gen(st, h, gid, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        g = httpx.get(f"{st.base}/api/generations/{gid}", headers=h).json()
        if g["status"] in ("success", "failed"):
            return g
        time.sleep(0.3)
    raise AssertionError(f"timeout; worker log:\n{st.logs('worker')}")


def test_heavy_render_via_real_celery_and_redis(stack, tmp_path):
    h = mk_user(stack, "heavy1")
    fund(stack, h)                                              # 110 credits
    img, vid = sample_assets(stack, h, tmp_path)
    t = httpx.post(stack.base + "/api/templates", headers=h, json={
        "title": "M", "base_video_url": vid, "template_schema": {"motion_transfer": True, "layers": []}}).json()
    r = httpx.post(stack.base + "/api/generate", headers=h, json={
        "template_id": t["id"], "render_type": "auto", "input_data": {"character_image": img}})
    assert r.status_code == 200 and r.json()["render_type"] == "heavy_mimicmotion", r.text
    assert r.json()["status"] in ("pending", "processing")      # returned immediately, work is async
    assert bal(stack, h) == 100                                 # 110 - 10 charged up-front
    g = wait_gen(stack, h, r.json()["id"])
    assert g["status"] == "success", g["error_message"]
    mp4 = httpx.get(stack.base + g["output_video_url"])
    assert mp4.status_code == 200 and mp4.headers["content-type"] == "video/mp4" and len(mp4.content) > 1000
    assert bal(stack, h) == 100


def test_heavy_failure_in_worker_refunds(stack, tmp_path):
    h = mk_user(stack, "heavy2")
    fund(stack, h, "p50")
    img, vid = sample_assets(stack, h, tmp_path)
    t = httpx.post(stack.base + "/api/templates", headers=h, json={
        "title": "bad", "base_video_url": vid, "template_schema": {"motion_transfer": True, "layers": []}}).json()
    (Path(stack.tmp) / "uploads" / Path(img).name).write_bytes(b"corrupt")       # corrupt the character image
    r = httpx.post(stack.base + "/api/generate", headers=h, json={
        "template_id": t["id"], "render_type": "heavy_mimicmotion", "input_data": {"character_image": img}})
    assert r.status_code == 200
    g = wait_gen(stack, h, r.json()["id"])
    assert g["status"] == "failed" and "MimicMotion" in g["error_message"], g
    assert bal(stack, h) == 50                                  # refunded by the worker


def test_fast_and_wallet_over_real_http(stack):
    h = mk_user(stack, "fast1")
    fund(stack, h, "p50")
    t = httpx.post(stack.base + "/api/templates", headers=h, json={"title": "f", "template_schema": {
        "width": 200, "height": 200, "duration": 1, "fps": 10, "layers": [{"id": "t", "type": "text", "default": "x"}]}}).json()
    r = httpx.post(stack.base + "/api/generate", headers=h, json={"template_id": t["id"], "render_type": "fast_remotion"})
    g = wait_gen(stack, h, r.json()["id"])
    assert g["status"] == "success" and bal(stack, h) == 49


def titled(st, h, title):
    return next(t["id"] for t in httpx.get(st.base + "/api/templates", headers=h).json() if t["title"] == title)


def test_ai_video_via_real_ai_queue(stack):
    h = mk_user(stack, "aivid1")
    fund(stack, h, "p200")
    r = httpx.post(stack.base + "/api/generate", headers=h, json={
        "template_id": titled(stack, h, "Video AI từ mô tả (MiniMax-H3)"),
        "input_data": {"prompt": "mèo nhảy múa", "duration": 5}})
    assert r.status_code == 200 and r.json()["render_type"] == "ai_video", r.text
    g = wait_gen(stack, h, r.json()["id"])
    assert g["status"] == "success", g["error_message"]
    assert httpx.get(stack.base + g["output_video_url"]).status_code == 200
    assert bal(stack, h) == 230 - 20


def test_dance_combo_hops_between_ai_and_gpu_queues(stack, tmp_path):
    h = mk_user(stack, "dance1")
    fund(stack, h, "p200")
    img, _ = sample_assets(stack, h, tmp_path)
    r = httpx.post(stack.base + "/api/generate", headers=h, json={
        "template_id": titled(stack, h, "Nhảy theo ảnh nhân vật (MiniMax-H3 + MimicMotion)"),
        "input_data": {"prompt": "nhảy hiphop", "character_image": img, "duration": 5}})
    assert r.status_code == 200 and r.json()["render_type"] == "ai_dance", r.text
    g = wait_gen(stack, h, r.json()["id"])
    assert g["status"] == "success", g["error_message"] + stack.logs("gpuworker")
    assert bal(stack, h) == 230 - 30
    gpu_log, ai_log = (stack.tmp / "gpuworker.log").read_text(), (stack.tmp / "worker.log").read_text()
    assert "Task render.heavy[" in gpu_log                       # stage 2 ran on the GPU worker
    assert "Task render.ai[" in ai_log                           # stage 1 on the API worker
    assert "Task render.heavy[" not in ai_log and "Task render.ai[" not in gpu_log


def test_ai_video_works_without_redis_but_dance_refunds(stack, tmp_path):
    """Run last in the file: it stops Redis (test_broker_down_returns_503_and_refunds already did)."""
    h = mk_user(stack, "noredis1")
    fund(stack, h, "p200")
    stack.stop("redis")
    r = httpx.post(stack.base + "/api/generate", headers=h, json={
        "template_id": titled(stack, h, "Video AI từ mô tả (MiniMax-H3)"), "input_data": {"prompt": "x"}}, timeout=90)
    assert r.status_code == 200, r.text                                      # fell back to in-process
    assert wait_gen(stack, h, r.json()["id"])["status"] == "success"
    img, _ = sample_assets(stack, h, tmp_path)
    r2 = httpx.post(stack.base + "/api/generate", headers=h, json={
        "template_id": titled(stack, h, "Nhảy theo ảnh nhân vật (MiniMax-H3 + MimicMotion)"),
        "input_data": {"prompt": "x", "character_image": img}}, timeout=90)
    assert r2.status_code == 503
    assert bal(stack, h) == 230 - 20                                          # only the finished ai_video is paid


def test_broker_down_returns_503_and_refunds(stack, tmp_path):
    h = mk_user(stack, "broker1")
    fund(stack, h, "p50")
    img, vid = sample_assets(stack, h, tmp_path)
    t = httpx.post(stack.base + "/api/templates", headers=h, json={
        "title": "M", "base_video_url": vid, "template_schema": {"motion_transfer": True, "layers": []}}).json()
    stack.stop("redis")
    r = httpx.post(stack.base + "/api/generate", headers=h, json={
        "template_id": t["id"], "render_type": "heavy_mimicmotion", "input_data": {"character_image": img}}, timeout=90)
    assert r.status_code == 503, r.text
    assert bal(stack, h) == 50
    hist = httpx.get(stack.base + "/api/generations", headers=h).json()
    assert hist[0]["status"] == "failed"

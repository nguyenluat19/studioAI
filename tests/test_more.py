import json
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app import ai
from app.config import settings
from tests.test_flow import SCHEMA, balance, make_template, pay, topup, wait_done

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg missing")


def make_png(path, color="red", size="64x64"):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={color}:s={size}",
                    "-frames:v", "1", str(path)], check=True)
    return path


def up(client, h, path, mime="image/png"):
    r = client.post("/api/uploads", headers=h, files={"file": (path.name, path.read_bytes(), mime)})
    assert r.status_code == 200, r.text
    return r.json()["url"]


def probe(url_path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,codec_name", "-of", "json", str(url_path)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)["streams"][0]


def funded(client, make_user, pkg="p100"):
    h, uid = make_user()
    pay(client, topup(client, h, uid, pkg))
    return h, uid


# ---------- rendering with images / logo / background / base video ----------
def test_render_with_logo_image_and_background(client, make_user, tmp_path):
    h, uid = funded(client, make_user)
    bg = up(client, h, make_png(tmp_path / "bg.png", "green", "200x200"))
    logo = up(client, h, make_png(tmp_path / "logo.png", "red"))
    schema = {"width": 360, "height": 640, "duration": 1, "fps": 10, "layers": [
        {"id": "bg", "type": "background"},
        {"id": "logo", "type": "logo", "x": 10, "y": 10, "w": 80},
        {"id": "pic", "type": "image", "x": 100, "y": 200, "w": 100},
        {"id": "title", "type": "text", "default": "Tiếng Việt có dấu: ắ ề ổ", "fontsize": 28, "box": True}]}
    t = make_template(client, h, schema)
    r = client.post("/api/generate", headers=h, json={"template_id": t["id"], "render_type": "fast_remotion",
                    "input_data": {"bg": bg, "logo": logo, "pic": logo, "title": "Xin chào: \"quote\" 'x' %{n}"}})
    g = wait_done(client, h, r.json()["id"])
    assert g["status"] == "success", g["error_message"]
    from app.media import resolve as _media_resolve
    out = _media_resolve(g["output_video_url"])
    assert out is not None and out.exists()
    s = probe(out)
    assert (s["width"], s["height"], s["codec_name"]) == (360, 640, "h264")


def test_render_over_uploaded_base_video(client, make_user, tmp_path):
    h, uid = funded(client, make_user)
    vid = tmp_path / "base.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=s=160x120:d=1:r=10",
                    "-f", "lavfi", "-i", "sine=d=1", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(vid)], check=True)
    vurl = up(client, h, vid, "video/mp4")
    t = client.post("/api/templates", headers=h, json={"title": "V", "base_video_url": vurl,
                    "template_schema": {**SCHEMA, "duration": 1}}).json()
    g = wait_done(client, h, client.post("/api/generate", headers=h, json={
        "template_id": t["id"], "render_type": "fast_remotion", "input_data": {"title": "Hi"}}).json()["id"])
    assert g["status"] == "success", g["error_message"]


def test_upload_rejects_bad_extension_and_traversal(client, make_user):
    h, _ = make_user()
    assert client.post("/api/uploads", headers=h, files={"file": ("a.exe", b"x")}).status_code == 415
    assert client.post("/api/uploads", files={"file": ("a.png", b"x")}).status_code == 401
    r = client.post("/api/templates", headers=h, json={"title": "x", "base_video_url": "/media/uploads/../test.db",
                                                       "template_schema": {}})
    assert r.status_code == 422


# ---------- concurrency: balance never goes negative, exactly N succeed ----------
def test_concurrent_generate_cannot_overdraw(client, make_user, admin_headers):
    h, uid = make_user()
    pay(client, topup(client, h, uid))            # 50 credits
    t = make_template(client, h)
    client.put("/api/admin/pricing/render.fast", headers=admin_headers, json={"price": 10})   # -> exactly 5 affordable
    try:
        def go(_):
            return client.post("/api/generate", headers=h, json={"template_id": t["id"],
                               "render_type": "fast_remotion"}).status_code
        with ThreadPoolExecutor(12) as ex:
            codes = list(ex.map(go, range(12)))
    finally:
        client.put("/api/admin/pricing/render.fast", headers=admin_headers, json={"price": 1})
    assert codes.count(200) == 5 and codes.count(402) == 7, codes
    assert balance(uid) == 0
    hist = client.get("/api/generations", headers=h).json()
    assert len(hist) == 5 and all(g["status"] == "success" for g in hist)


def test_concurrent_webhook_replays_credit_once(client, make_user):
    h, uid = make_user()
    tx = topup(client, h, uid)
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda _: pay(client, tx).json()["results"][0]["status"], range(8)))
    assert res.count("success") == 1 and balance(uid) == 50, res


# ---------- QR link ----------
def test_qr_url_shape(client, make_user):
    h, uid = make_user()
    tx = topup(client, h, uid, "p200")
    from urllib.parse import parse_qs, urlparse
    u = urlparse(tx["qr_url"])
    q = parse_qs(u.query)
    assert u.netloc == "img.vietqr.io" and f"{settings.bank_bin}-{settings.bank_account_no}" in u.path
    assert q["amount"] == ["230000"] and q["addInfo"] == [tx["transaction_code"]]
    assert len(tx["transaction_code"]) == 11 and tx["transaction_code"].startswith("NAP")


def test_my_transactions_and_status_isolation(client, make_user):
    h1, _ = make_user()
    h2, u2 = make_user()
    tx = topup(client, h2, u2)
    assert client.get(f"/api/billing/transactions/{tx['id']}", headers=h1).status_code == 404
    assert client.get(f"/api/billing/transactions/{tx['id']}", headers=h2).json()["status"] == "pending"
    pay(client, tx)
    mine = client.get("/api/billing/transactions", headers=h2).json()
    assert mine[0]["status"] == "success" and mine[0]["qr_url"] is None


# ---------- admin ----------
def test_admin_endpoints(client, make_user, admin_headers):
    h, uid = make_user()
    assert client.get("/api/admin/stats", headers=h).status_code == 403
    assert client.get("/api/admin/stats", headers=admin_headers).json()["users"] >= 2
    tx = topup(client, h, uid)
    pay(client, tx, amount=1)                                      # mismatch -> pending
    assert client.post(f"/api/admin/transactions/{tx['id']}/approve", headers=admin_headers).status_code == 200
    assert balance(uid) == 50
    assert client.post(f"/api/admin/transactions/{tx['id']}/approve", headers=admin_headers).status_code == 409
    assert client.post(f"/api/admin/users/{uid}/credits", headers=admin_headers, json={"amount": -999}).status_code == 422
    assert client.post(f"/api/admin/users/{uid}/credits", headers=admin_headers, json={"amount": 5}).json()["credits_balance"] == 55


def test_auth_validation(client):
    bad = client.post("/api/auth/register", json={"username": "a b", "email": "nope", "password": "short", "phone": "0900000099"})
    assert bad.status_code == 422
    client.post("/api/auth/register", json={"username": "dupuser", "email": "dup@x.io", "password": "password123", "phone": "0900000098"})
    assert client.post("/api/auth/register", json={"username": "dupuser", "email": "o@x.io",
                                                   "password": "password123", "phone": "0900000097"}).status_code == 409
    assert client.post("/api/auth/login", json={"username": "dupuser", "password": "wrongwrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "dup@x.io", "password": "password123"}).status_code == 200


# ---------- Inkstone client against a real local HTTP server ----------
class _Fake(BaseHTTPRequestHandler):
    log: list = []
    decision = {"render_type": "heavy_mimicmotion"}

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Fake.log.append((self.path, self.headers.get("Authorization"), body))
        if body["model"] == "boom":
            self.send_response(500); self.end_headers(); return
        content = json.dumps(_Fake.decision) if body["model"] == "intern-decision-4b" else f"reply-from-{body['model']}"
        out = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a): pass


@pytest.fixture()
def inkstone():
    srv = HTTPServer(("127.0.0.1", 0), _Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    old = (settings.inkstone_base_url, settings.inkstone_api_key)
    settings.inkstone_base_url, settings.inkstone_api_key = f"http://127.0.0.1:{srv.server_port}/v1", "k123"
    _Fake.log.clear(); _Fake.decision = {"render_type": "heavy_mimicmotion"}
    yield _Fake
    settings.inkstone_base_url, settings.inkstone_api_key = old
    srv.shutdown()


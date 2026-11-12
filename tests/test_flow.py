import shutil
import time

import pytest

from app.db import SessionLocal
from app.models import GenerationHistory, Transaction, User

SCHEMA = {"width": 320, "height": 240, "duration": 1, "fps": 10, "bg_color": "navy",
          "layers": [{"id": "title", "type": "text", "default": "Xin chào", "fontsize": 32, "y": "h*0.4"}]}
HAVE_FFMPEG = shutil.which("ffmpeg") is not None


def balance(uid):
    with SessionLocal() as db:
        return db.get(User, uid).credits_balance


# Old fixed packs, kept as shorthand so existing expectations hold: amount in đ -> credits at 1.000đ/credit.
AMOUNTS = {"p50": 50_000, "p100": 110_000, "p200": 230_000, "p500": 600_000}   # -> 50 / 110 / 230 / 600 credits


def topup(client, headers, uid, pkg="p50"):
    r = client.post("/api/billing/topup", headers=headers, json={"amount_vnd": AMOUNTS.get(pkg, pkg)})
    assert r.status_code == 200, r.text
    return r.json()


def pay(client, tx, amount=None, **kw):
    return client.post("/api/webhooks/payment", headers={"Authorization": "Apikey sepay-key"}, json={
        "transferType": "in", "transferAmount": amount or tx["amount_vnd"],
        "content": f"MBVCB 123 {tx['transaction_code']} chuyen tien", **kw})


def make_template(client, headers, schema=SCHEMA):
    r = client.post("/api/templates", headers=headers, json={"title": "T", "template_schema": schema})
    assert r.status_code == 200, r.text
    return r.json()


def wait_done(client, headers, gid):
    for _ in range(100):
        g = client.get(f"/api/generations/{gid}", headers=headers).json()
        if g["status"] in ("success", "failed"):
            return g
        time.sleep(0.1)
    raise AssertionError("render timed out")


# ---------- top-up ----------
def test_topup_webhook_credits_exactly_once(client, make_user):
    h, uid = make_user()
    tx = topup(client, h, uid)
    assert tx["status"] == "pending" and "img.vietqr.io" in tx["qr_url"] and tx["transaction_code"] in tx["qr_url"]
    assert pay(client, tx).json()["results"][0]["status"] == "success"
    assert balance(uid) == 50
    assert pay(client, tx).json()["results"][0]["status"] == "duplicate"  # replay
    assert balance(uid) == 50


def test_webhook_rejects_bad_auth_and_amount_mismatch(client, make_user):
    h, uid = make_user()
    tx = topup(client, h, uid)
    assert client.post("/api/webhooks/payment", json={}).status_code == 401
    assert client.post("/api/webhooks/payment", headers={"Authorization": "Apikey nope"}, json={}).status_code == 401
    assert pay(client, tx, amount=1000).json()["results"][0]["status"] == "amount_mismatch"
    assert balance(uid) == 0
    with SessionLocal() as db:
        assert db.get(Transaction, tx["id"]).status == "pending"


def test_casso_webhook_and_separator_stripped_content(client, make_user):
    h, uid = make_user()
    tx = topup(client, h, uid, "p100")
    code = tx["transaction_code"]
    r = client.post("/api/webhooks/payment", headers={"secure-token": "casso-token"},
                    json={"error": 0, "data": [{"description": f"{code[:3]}-{code[3:]} abc", "amount": 110000}]})
    assert r.json()["results"][0]["status"] == "success"
    assert balance(uid) == 110


# ---------- credits & rendering ----------
def test_insufficient_credit_rejected(client, make_user):
    h, uid = make_user()
    t = make_template(client, h)
    r = client.post("/api/generate", headers=h, json={"template_id": t["id"], "render_type": "fast_remotion"})
    assert r.status_code == 402
    assert balance(uid) == 0


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg missing")
def test_history_includes_aspect_ratio(client, make_user):
    h, uid = make_user()
    pay(client, topup(client, h, uid))
    t = make_template(client, h, {**SCHEMA, "aspect_ratio": "16:9"})
    r = client.post("/api/generate", headers=h, json={"template_id": t["id"], "render_type": "fast_remotion",
                                                      "input_data": {"title": "Hello Việt Nam"}})
    assert r.status_code == 200
    hist = client.get("/api/generations", headers=h).json()
    assert hist and hist[0]["aspect_ratio"] == "16:9", hist


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg missing")
def test_fast_render_charges_and_succeeds(client, make_user):
    h, uid = make_user()
    pay(client, topup(client, h, uid))
    t = make_template(client, h)
    r = client.post("/api/generate", headers=h, json={"template_id": t["id"], "render_type": "fast_remotion",
                                                      "input_data": {"title": "Hello Việt Nam"}})
    assert r.status_code == 200
    g = wait_done(client, h, r.json()["id"])
    assert g["status"] == "success", g
    assert client.get(g["output_video_url"]).status_code == 200
    assert balance(uid) == 49
    assert client.get(f"/api/templates/{t['id']}", headers=h).json()["usage_count"] == 1


def test_failed_render_refunds_exact_cost(client, make_user):
    h, uid = make_user()
    pay(client, topup(client, h, uid))
    # Schema references a missing background upload -> still valid layer, so force failure via bad ffmpeg input.
    t = make_template(client, h, {"width": 0, "height": 0, "duration": 1, "layers": []})
    r = client.post("/api/generate", headers=h, json={"template_id": t["id"], "render_type": "fast_remotion"})
    g = wait_done(client, h, r.json()["id"])
    assert g["status"] == "failed" and g["error_message"]
    assert balance(uid) == 50  # fully refunded


def test_refund_is_idempotent(client, make_user):
    from app import credits
    h, uid = make_user()
    pay(client, topup(client, h, uid))
    t = make_template(client, h, {"width": 0, "height": 0, "duration": 1, "layers": []})
    g = wait_done(client, h, client.post("/api/generate", headers=h, json={
        "template_id": t["id"], "render_type": "fast_remotion"}).json()["id"])
    with SessionLocal() as db:
        assert credits.fail_and_refund(db, g["id"], "again") is False
    assert balance(uid) == 50


def test_heavy_without_mimicmotion_refunds(client, make_user, tmp_path):
    h, uid = make_user()
    pay(client, topup(client, h, uid))
    img = client.post("/api/uploads", headers=h, files={"file": ("c.png", b"\x89PNG\r\n", "image/png")}).json()["url"]
    vid = client.post("/api/uploads", headers=h, files={"file": ("v.mp4", b"x", "video/mp4")}).json()["url"]
    t = client.post("/api/templates", headers=h, json={
        "title": "M", "base_video_url": vid, "template_schema": {"motion_transfer": True, "layers": []}}).json()
    r = client.post("/api/generate", headers=h, json={"template_id": t["id"], "render_type": "auto",
                                                      "input_data": {"character_image": img}})
    assert r.status_code == 200 and r.json()["render_type"] == "heavy_mimicmotion"
    # Celery runs eagerly in tests, so the job has already failed and refunded here.
    g = wait_done(client, h, r.json()["id"])
    assert g["status"] == "failed" and "MimicMotion" in g["error_message"]
    assert balance(uid) == 50


# ---------- moderation & access ----------
def test_template_private_until_admin_publishes(client, make_user, admin_headers):
    h1, _ = make_user()
    h2, _ = make_user()
    t = make_template(client, h1)
    assert t["status"] == "private"
    assert client.get(f"/api/templates/{t['id']}", headers=h2).status_code == 404
    assert t["id"] not in [x["id"] for x in client.get("/api/templates", headers=h2).json()]
    assert client.post(f"/api/admin/templates/{t['id']}/publish", headers=h1).status_code == 403
    assert client.post(f"/api/admin/templates/{t['id']}/publish", headers=admin_headers).json()["status"] == "publish"
    assert t["id"] in [x["id"] for x in client.get("/api/templates", headers=h2).json()]


def test_media_does_not_expose_database(client):
    assert client.get("/media/app.db").status_code == 404
    assert client.get("/media/test.db").status_code == 404


def test_schema_validation(client, make_user):
    h, _ = make_user()
    r = client.post("/api/templates", headers=h, json={"title": "x", "template_schema": {"layers": [{"id": "a", "type": "evil"}]}})
    assert r.status_code == 422


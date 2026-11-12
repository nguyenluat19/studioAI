"""Bug 6: POST /api/generations/{id}/reuse — tạo render mới từ input cũ.
   Bug 9: API key của model admin lưu trong .env (MODEL_<ID>_API_KEY), không lưu DB;
   sync() tự migrate key cũ trong DB sang .env."""
import os

from app import adminmodels
from app.db import SessionLocal
from app.models import AppModel, User, GenerationHistory

AMOUNTS = {"p50": 50_000}
SCHEMA = {"width": 240, "height": 320, "duration": 1, "fps": 10, "bg_color": "navy", "layers": [
    {"id": "title", "type": "text", "default": "Gốc", "fontsize": 30},
    {"id": "bg", "type": "background"}]}


def topup(client, headers, uid):
    r = client.post("/api/billing/topup", headers=headers, json={"amount_vnd": AMOUNTS["p50"]})
    assert r.status_code == 200, r.text
    return r.json()


def pay(client, tx):
    return client.post("/api/webhooks/payment", headers={"Authorization": "Apikey sepay-key"}, json={
        "transferType": "in", "transferAmount": tx["amount_vnd"],
        "content": f"MBVCB 123 {tx['transaction_code']} chuyen tien"})


def make_template(client, headers):
    r = client.post("/api/templates", headers=headers, json={"title": "T", "template_schema": SCHEMA})
    assert r.status_code == 200, r.text
    return r.json()


def balance(uid):
    with SessionLocal() as db:
        return db.get(User, uid).credits_balance


def _gen(client, h, tid, **kw):
    r = client.post("/api/generate", headers=h,
                    json={"template_id": tid, "render_type": "fast_remotion", **kw})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------- Bug 6: /reuse ----------------

def test_reuse_creates_new_job_with_old_inputs(client, make_user):
    h, uid = make_user()
    pay(client, topup(client, h, uid))
    t = make_template(client, h)
    g = _gen(client, h, t["id"], input_data={"title": "Bản cũ"}, title="Bản cũ")

    before = balance(uid)
    r = client.post(f"/api/generations/{g['id']}/reuse", headers=h)
    assert r.status_code == 200, r.text
    g2 = r.json()
    assert g2["id"] != g["id"]
    assert g2["template_id"] == t["id"] and g2["render_type"] == "fast_remotion"
    assert g2["input_data"]["title"] == "Bản cũ"
    assert balance(uid) == before - 1                      # fast = 1 credit
    with SessionLocal() as db:
        row = db.get(GenerationHistory, g2["id"])
        assert row.user_id == uid


def test_reuse_with_overrides(client, make_user):
    h, uid = make_user()
    pay(client, topup(client, h, uid))
    t = make_template(client, h)
    g = _gen(client, h, t["id"], input_data={"title": "Cũ"}, title="Cũ", user_category="Tiktok")

    r = client.post(f"/api/generations/{g['id']}/reuse", headers=h, json={
        "input_data": {"title": "Mới"}, "title": "Mới", "user_category": "Youtube"})
    assert r.status_code == 200, r.text
    g2 = r.json()
    assert g2["input_data"]["title"] == "Mới"
    assert g2["title"] == "Mới" and g2["user_category"] == "Youtube"


def test_reuse_requires_owner(client, make_user):
    h1, uid1 = make_user()
    pay(client, topup(client, h1, uid1))
    t = make_template(client, h1)
    g = _gen(client, h1, t["id"], input_data={"title": "X"})

    h2, _ = make_user()
    r = client.post(f"/api/generations/{g['id']}/reuse", headers=h2)
    assert r.status_code == 404


def test_reuse_402_when_out_of_credits(client, make_user):
    h, uid = make_user()                        # 0 credit
    t = make_template(client, h)
    # tạo generation thủ công (không qua /generate để không cần deduct)
    with SessionLocal() as db:
        row = GenerationHistory(user_id=uid, template_id=t["id"], render_type="fast_remotion",
                                input_data={"title": "X"}, credits_cost=1, status="success",
                                share_to_library=False, title="X", user_category="Mặc định")
        db.add(row)
        db.commit()
        db.refresh(row)
    r = client.post(f"/api/generations/{row.id}/reuse", headers=h)
    assert r.status_code == 402


# ---------------- Bug 9: key trong .env, không trong DB ----------------

def test_model_api_key_stored_in_env_not_db(client, admin_headers):
    r = client.post("/api/admin/models", headers=admin_headers, json={
        "name": "Env Key Model", "step": "llm", "base_url": "https://gw.example.io",
        "api_key": "sk-env-test-987654321", "model_name": "m"})
    assert r.status_code == 200, r.text
    mid = r.json()["model"]["id"]
    env_var = f"MODEL_{mid.upper().replace('-', '_')}_API_KEY"
    try:
        assert os.environ.get(env_var) == "sk-env-test-987654321"
        with SessionLocal() as db:
            assert db.get(AppModel, mid).api_key == ""       # key không lưu DB
        assert r.json()["model"]["has_key"] is True
        assert "sk-env-test-987654321" not in r.text         # key không lộ ra API
    finally:
        client.delete(f"/api/admin/models/{mid}", headers=admin_headers)
    assert os.environ.get(env_var) is None                   # xoá model -> key khỏi .env


def test_sync_migrates_legacy_db_key_to_env(client, admin_headers):
    with SessionLocal() as db:
        row = AppModel(id="legacy-key-model", name="Legacy Key Model", step="llm",
                       base_url="https://gw.example.io", api_key="sk-legacy-12345",
                       model_name="m", enabled=True, max_clip_seconds=15,
                       supported_durations=[])
        db.add(row)
        db.commit()
    try:
        adminmodels.sync()
        with SessionLocal() as db:
            assert db.get(AppModel, "legacy-key-model").api_key == ""
        assert os.environ.get("MODEL_LEGACY_KEY_MODEL_API_KEY") == "sk-legacy-12345"
    finally:
        client.delete("/api/admin/models/legacy-key-model", headers=admin_headers)

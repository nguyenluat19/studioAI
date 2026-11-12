"""QR expiry, late payments, webhook log, stuck-job reaper, library pipeline, AI fallback, limits, migrations."""
import json
import shutil
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from app import ai, maintenance
from app.config import settings
from app.db import SessionLocal
from app.models import GenerationHistory, SharedVideoLibrary, Transaction, User
from tests.test_flow import SCHEMA, balance, make_template, pay, topup, wait_done
from tests.test_more import _Fake, inkstone, make_png, up  # noqa: F401  (fixture re-export)

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg missing")


def age_tx(tx_id, seconds):
    with SessionLocal() as db:
        t = db.get(Transaction, tx_id)
        t.created_at = datetime.now(timezone.utc) - timedelta(seconds=seconds)
        db.commit()


def tx_status(tx_id):
    with SessionLocal() as db:
        return db.get(Transaction, tx_id).status


# ---------------- A2: QR lifetime 5 minutes ----------------
def test_qr_has_five_minute_lifetime(client, make_user):
    h, uid = make_user()
    tx = topup(client, h, uid)
    assert settings.tx_ttl_seconds == 300
    assert 295 <= tx["seconds_left"] <= 300 and tx["expires_at"]
    assert client.get(f"/api/billing/transactions/{tx['id']}", headers=h).json()["status"] == "pending"


def test_expired_qr_becomes_failed_and_hides_qr(client, make_user):
    h, uid = make_user()
    tx = topup(client, h, uid)
    age_tx(tx["id"], 301)
    st = client.get(f"/api/billing/transactions/{tx['id']}", headers=h).json()
    assert st["status"] == "failed" and st["qr_url"] is None and st["seconds_left"] == 0
    assert balance(uid) == 0


def test_not_yet_expired_stays_pending(client, make_user):
    h, uid = make_user()
    tx = topup(client, h, uid)
    age_tx(tx["id"], 290)
    assert client.get(f"/api/billing/transactions/{tx['id']}", headers=h).json()["status"] == "pending"


def test_sweeper_expires_without_anyone_looking(client, make_user):
    h, uid = make_user()
    fresh, old = topup(client, h, uid), topup(client, h, uid)
    age_tx(old["id"], 400)
    with SessionLocal() as db:
        assert maintenance.expire_transactions(db) >= 1
    assert tx_status(old["id"]) == "failed" and tx_status(fresh["id"]) == "pending"


def test_payment_on_time_still_credits(client, make_user):
    h, uid = make_user()
    tx = topup(client, h, uid)
    age_tx(tx["id"], 250)
    assert pay(client, tx).json()["results"][0]["status"] == "success"
    assert balance(uid) == 50


def test_late_payment_is_logged_not_credited_then_admin_can_approve(client, make_user, admin_headers):
    h, uid = make_user()
    tx = topup(client, h, uid)
    age_tx(tx["id"], 360)
    assert pay(client, tx).json()["results"][0]["status"] == "late_payment"
    assert balance(uid) == 0 and tx_status(tx["id"]) == "failed"
    log = client.get("/api/admin/webhook-log?result=late_payment", headers=admin_headers).json()
    assert any(w["transaction_code"] == tx["transaction_code"] for w in log)
    assert client.post(f"/api/admin/transactions/{tx['id']}/approve", headers=admin_headers).status_code == 200
    assert balance(uid) == 50 and tx_status(tx["id"]) == "success"


def test_late_payment_autocredit_flag(client, make_user):
    h, uid = make_user()
    tx = topup(client, h, uid)
    age_tx(tx["id"], 360)
    settings.late_payment_autocredit = True
    try:
        assert pay(client, tx).json()["results"][0]["status"] == "late_credited"
        assert pay(client, tx).json()["results"][0]["status"] == "duplicate"
    finally:
        settings.late_payment_autocredit = False
    assert balance(uid) == 50


def test_webhook_log_records_every_outcome(client, make_user, admin_headers):
    h, uid = make_user()
    tx = topup(client, h, uid)
    pay(client, tx, amount=5)
    pay(client, tx)
    pay(client, tx)
    client.post("/api/webhooks/payment", headers={"Authorization": "Apikey sepay-key"},
                json={"transferType": "in", "transferAmount": 1, "content": "hello"})
    client.post("/api/webhooks/payment", headers={"Authorization": "Apikey sepay-key"},
                json={"transferType": "in", "transferAmount": 1, "content": "NAPZZZZZZZZ"})
    rows = client.get("/api/admin/webhook-log", headers=admin_headers).json()
    mine = [w["result"] for w in rows if w["transaction_code"] == tx["transaction_code"]]
    assert mine == ["duplicate", "success", "amount_mismatch"]
    allr = {w["result"] for w in rows}
    assert {"ignored_no_code", "ignored_unknown_code"} <= allr
    assert client.get("/api/admin/webhook-log", headers=h).status_code == 403


# ---------------- A1: stuck jobs are failed and refunded ----------------
def stuck_generation(client, h, uid, rtype, status, age):
    t = make_template(client, h)
    with SessionLocal() as db:
        db.execute(User.__table__.update().where(User.id == uid).values(credits_balance=User.credits_balance - 10))
        g = GenerationHistory(user_id=uid, template_id=t["id"], render_type=rtype, input_data={},
                              credits_cost=10, status=status, share_to_library=True,
                              updated_at=datetime.now(timezone.utc) - timedelta(seconds=age))
        db.add(g)
        db.commit()
        return g.id


def gen_status(gid):
    with SessionLocal() as db:
        return db.get(GenerationHistory, gid).status


def test_reaper_fails_and_refunds_stuck_jobs(client, make_user):
    h, uid = make_user()
    pay(client, topup(client, h, uid))                        # 50
    stuck = {
        "fast_proc": stuck_generation(client, h, uid, "fast_remotion", "processing", settings.fast_timeout + 5),
        "fast_pend": stuck_generation(client, h, uid, "fast_remotion", "pending", settings.fast_timeout + 5),
        "heavy_proc": stuck_generation(client, h, uid, "heavy_mimicmotion", "processing", settings.heavy_timeout + 5),
        "heavy_pend": stuck_generation(client, h, uid, "heavy_mimicmotion", "pending", settings.heavy_queue_timeout + 5),
    }
    live = {
        "fast_ok": stuck_generation(client, h, uid, "fast_remotion", "processing", 30),
        "heavy_running": stuck_generation(client, h, uid, "heavy_mimicmotion", "processing", settings.fast_timeout + 60),
        "heavy_queued": stuck_generation(client, h, uid, "heavy_mimicmotion", "pending", settings.heavy_timeout + 60),
    }
    assert balance(uid) == 50 - 70
    with SessionLocal() as db:
        assert maintenance.reap_generations(db) == 4
    assert all(gen_status(g) == "failed" for g in stuck.values())
    assert all(gen_status(g) != "failed" for g in live.values())
    assert balance(uid) == 50 - 70 + 40                         # exactly the 4 reaped were refunded
    with SessionLocal() as db:
        assert maintenance.reap_generations(db) == 0           # idempotent
    assert balance(uid) == 20


def test_late_success_after_reaping_cannot_double_pay(client, make_user):
    from app import credits
    h, uid = make_user()
    pay(client, topup(client, h, uid))
    gid = stuck_generation(client, h, uid, "fast_remotion", "processing", settings.fast_timeout + 5)
    with SessionLocal() as db:
        maintenance.reap_generations(db)
        credits.mark_success(db, gid, "/media/outputs/x.mp4")   # the straggler finishes afterwards
    assert gen_status(gid) == "failed" and balance(uid) == 50


# ---------------- B2: finished video -> admin library -> publish -> reuse & customise ----------------
def finished_entry(client, h, tmp_path, **gen_extra):
    logo = up(client, h, make_png(tmp_path / "l.png", "red"))
    schema = {"width": 240, "height": 320, "duration": 1, "fps": 10, "bg_color": "navy", "layers": [
        {"id": "title", "type": "text", "default": "Gốc", "fontsize": 30},
        {"id": "logo", "type": "logo", "x": 10, "y": 10, "w": 60},
        {"id": "bg", "type": "background"}]}
    t = make_template(client, h, schema)
    r = client.post("/api/generate", headers=h, json={"template_id": t["id"], "render_type": "fast_remotion",
                    "input_data": {"title": "Của user A", "logo": logo}, **gen_extra})
    return t, logo, wait_done(client, h, r.json()["id"])


@needs_ffmpeg
def test_finished_video_lands_in_admin_queue_private(client, make_user, admin_headers, tmp_path):
    h, uid = make_user()
    pay(client, topup(client, h, uid))
    t, logo, g = finished_entry(client, h, tmp_path)
    assert g["status"] == "success" and g["output_video_url"]          # user gets the video back
    entries = client.get("/api/admin/templates?source=generated", headers=admin_headers).json()
    e = next(x for x in entries if x["source_generation_id"] == g["id"])
    assert e["status"] == "private" and e["creator_id"] == uid
    assert e["preview_video_url"] == g["output_video_url"]
    assert e["thumbnail_url"] and client.get(e["thumbnail_url"]).status_code == 200
    layers = {l["id"]: l for l in e["template_schema"]["layers"]}
    assert layers["title"]["default"] == "Của user A" and layers["logo"]["default"] == logo
    assert t["template_schema"]["layers"][0]["default"] == "Gốc"       # source template untouched
    h2, _ = make_user()                                                  # not visible to others yet
    assert e["id"] not in [x["id"] for x in client.get("/api/templates", headers=h2).json()]
    assert client.get(f"/api/templates/{e['id']}", headers=h2).status_code == 404


@needs_ffmpeg
def test_publish_then_other_user_reuses_and_customises_everything(client, make_user, admin_headers, tmp_path):
    ha, ua = make_user()
    pay(client, topup(client, ha, ua))
    _, logo_a, ga = finished_entry(client, ha, tmp_path)
    e = next(x for x in client.get("/api/admin/templates?source=generated", headers=admin_headers).json()
             if x["source_generation_id"] == ga["id"])
    assert client.post(f"/api/admin/templates/{e['id']}/publish", headers=admin_headers).json()["status"] == "publish"

    hb, ub = make_user()
    pay(client, topup(client, hb, ub))
    assert e["id"] in [x["id"] for x in client.get("/api/templates", headers=hb).json()]

    # user B changes the text, the logo AND the background — nothing is locked
    logo_b = up(client, hb, make_png(tmp_path / "lb.png", "yellow"))
    bg_b = up(client, hb, make_png(tmp_path / "bgb.png", "green", "100x100"))
    r = client.post("/api/generate", headers=hb, json={"template_id": e["id"], "render_type": "fast_remotion",
                    "input_data": {"title": "Của user B", "logo": logo_b, "bg": bg_b}})
    assert r.status_code == 200
    gb = wait_done(client, hb, r.json()["id"])
    assert gb["status"] == "success", gb["error_message"]
    assert gb["input_data"]["title"] == "Của user B" and gb["input_data"]["logo"] == logo_b
    assert client.get(f"/api/templates/{e['id']}", headers=hb).json()["usage_count"] == 1
    # B's own result goes to the admin queue too, as a separate private entry
    again = client.get("/api/admin/templates?source=generated&status=private", headers=admin_headers).json()
    assert any(x["source_generation_id"] == gb["id"] for x in again)

    # B only overriding one field keeps A's other values as defaults
    r2 = client.post("/api/generate", headers=hb, json={"template_id": e["id"], "render_type": "fast_remotion",
                     "input_data": {"title": "Chỉ đổi chữ"}})
    g2 = wait_done(client, hb, r2.json()["id"])
    assert g2["status"] == "success" and g2["input_data"]["title"] == "Chỉ đổi chữ"


@needs_ffmpeg
def test_opt_out_of_sharing(client, make_user, admin_headers, tmp_path):
    h, uid = make_user()
    pay(client, topup(client, h, uid))
    _, _, g = finished_entry(client, h, tmp_path, share_to_library=False)
    assert g["status"] == "success" and g["share_to_library"] is False
    entries = client.get("/api/admin/templates?source=generated", headers=admin_headers).json()
    assert all(x["source_generation_id"] != g["id"] for x in entries)


def test_failed_render_creates_no_library_entry(client, make_user, admin_headers):
    h, uid = make_user()
    pay(client, topup(client, h, uid))
    t = make_template(client, h, {"width": 0, "height": 0, "duration": 1, "layers": []})
    g = wait_done(client, h, client.post("/api/generate", headers=h, json={
        "template_id": t["id"], "render_type": "fast_remotion"}).json()["id"])
    assert g["status"] == "failed"
    entries = client.get("/api/admin/templates?source=generated", headers=admin_headers).json()
    assert all(x["source_generation_id"] != g["id"] for x in entries)


@needs_ffmpeg
def test_admin_reject_and_guards(client, make_user, admin_headers, tmp_path):
    h, uid = make_user()
    pay(client, topup(client, h, uid))
    _, _, g = finished_entry(client, h, tmp_path)
    e = next(x for x in client.get("/api/admin/templates?source=generated", headers=admin_headers).json()
             if x["source_generation_id"] == g["id"])
    assert client.delete(f"/api/admin/templates/{e['id']}", headers=h).status_code == 403
    client.post(f"/api/admin/templates/{e['id']}/publish", headers=admin_headers)
    assert client.delete(f"/api/admin/templates/{e['id']}", headers=admin_headers).status_code == 409  # public
    client.post(f"/api/admin/templates/{e['id']}/unpublish", headers=admin_headers)
    assert client.delete(f"/api/admin/templates/{e['id']}", headers=admin_headers).json() == {"deleted": e["id"]}
    # a never-used private template can be rejected; one with history cannot
    t = make_template(client, h)
    assert client.delete(f"/api/admin/templates/{t['id']}", headers=admin_headers).status_code == 200
    t2 = make_template(client, h)
    client.post("/api/generate", headers=h, json={"template_id": t2["id"], "render_type": "fast_remotion"})
    assert client.delete(f"/api/admin/templates/{t2['id']}", headers=admin_headers).status_code == 409


@needs_ffmpeg
def test_template_with_base_video_gets_thumbnail(client, make_user, tmp_path):
    h, _ = make_user()
    vid = tmp_path / "b.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=s=160x120:d=1:r=10",
                    str(vid)], check=True)
    t = client.post("/api/templates", headers=h, json={"title": "V", "base_video_url": up(client, h, vid, "video/mp4"),
                                                       "template_schema": SCHEMA}).json()
    assert t["thumbnail_url"] and client.get(t["thumbnail_url"]).status_code == 200


# ---------------- AI model fallback ----------------
class _Flaky(_Fake):
    """Fails for the models in `bad`, answers for the rest."""
    bad: set = set()

    def do_POST(self):
        n = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(n))
        _Fake.log.append((self.path, self.headers.get("Authorization"), body))
        if body["model"] in _Flaky.bad:
            self.send_response(503); self.end_headers(); return
        out = json.dumps({"choices": [{"message": {"content": f"ok-{body['model']}"}}]}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(out)


@pytest.fixture()
def flaky():
    import threading
    from http.server import HTTPServer
    srv = HTTPServer(("127.0.0.1", 0), _Flaky)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    old = (settings.inkstone_base_url, settings.inkstone_api_key)
    settings.inkstone_base_url, settings.inkstone_api_key = f"http://127.0.0.1:{srv.server_port}/v1", "k"
    _Fake.log.clear()
    yield _Flaky
    settings.inkstone_base_url, settings.inkstone_api_key = old
    _Flaky.bad = set()
    srv.shutdown()




# ---------------- C1: limits and production guard ----------------
def test_login_rate_limit_and_reset_on_success(client):
    client.post("/api/auth/register", json={"username": "ratelim", "email": "rl@x.io", "password": "password123", "phone": "0900000001"})
    for _ in range(settings.login_max_failures):
        assert client.post("/api/auth/login", json={"username": "ratelim", "password": "wrong-wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "ratelim", "password": "password123"}).status_code == 429
    assert client.post("/api/auth/login", json={"username": "someoneelse", "password": "x"}).status_code == 401
    from app import ratelimit
    ratelimit.clear("login:testclient:ratelim")
    assert client.post("/api/auth/login", json={"username": "ratelim", "password": "password123"}).status_code == 200


def test_register_rate_limit(client):
    from app import ratelimit
    ratelimit.clear("reg:testclient")
    old = settings.register_per_hour
    settings.register_per_hour = 2
    try:
        codes = [client.post("/api/auth/register", json={"username": f"reglim{i}", "email": f"reglim{i}@x.io",
                 "password": "password123", "phone": f"090000001{i}"}).status_code for i in range(4)]
    finally:
        settings.register_per_hour = old
        ratelimit.clear("reg:testclient")
    assert codes == [200, 200, 429, 429]


def test_production_refuses_unsafe_config():
    from app.main import check_production_settings
    s = settings
    old = (s.app_env, s.secret_key, s.admin_password)
    try:
        s.app_env, s.secret_key, s.admin_password = "production", "dev-secret-change-me", ""
        with pytest.raises(RuntimeError, match="SECRET_KEY.*ADMIN_PASSWORD"):
            check_production_settings()
        s.secret_key, s.admin_password = "x" * 40, "a-real-password"
        check_production_settings()
        s.app_env, s.secret_key, s.admin_password = "dev", "dev-secret-change-me", ""
        check_production_settings()
    finally:
        s.app_env, s.secret_key, s.admin_password = old


# ---------------- A3: migrations ----------------
def test_migrations_from_scratch_and_from_legacy(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, inspect
    import app.migrate as migrate

    def run(db_file, pre=None):
        eng = create_engine(f"sqlite:///{db_file}")
        if pre:
            pre(eng)
        monkeypatch.setattr(migrate, "engine", eng)
        migrate.upgrade_db()
        return inspect(eng), eng

    insp, _ = run(tmp_path / "new.db")
    assert {"users", "shared_video_library", "transactions", "generation_history", "webhook_log",
            "alembic_version", "pricing_items", "pricing_log", "app_settings", "promotions", "credit_adjustments",
            "app_models", "pipeline_jobs", "chat_messages", "phone_otps"} <= set(insp.get_table_names())
    assert {"updated_at", "share_to_library"} <= {c["name"] for c in insp.get_columns("generation_history")}
    assert {"preview_video_url", "source_generation_id"} <= {c["name"] for c in insp.get_columns("shared_video_library")}

    def legacy(eng):                         # database made by the previous (create_all) version
        from alembic import command
        from alembic.config import Config
        cfg = Config(str(migrate.ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(migrate.ROOT / "migrations"))
        cfg.set_main_option("sqlalchemy.url", str(eng.url).replace("%", "%%"))
        command.upgrade(cfg, "0001")
        with eng.begin() as c:
            c.exec_driver_sql("DROP TABLE alembic_version")
            c.exec_driver_sql("INSERT INTO users (username,email,password_hash,credits_balance,role) VALUES ('old','o@x','h',7,'user')")
            c.exec_driver_sql("INSERT INTO shared_video_library (title,creator_id,template_schema) VALUES ('t',1,'{}')")
            c.exec_driver_sql("INSERT INTO generation_history (user_id,template_id,render_type,status,created_at) "
                              "VALUES (1,1,'fast_remotion','success','2026-01-01 00:00:00')")

    insp, eng = run(tmp_path / "legacy.db", legacy)
    with eng.connect() as c:
        assert c.exec_driver_sql("SELECT credits_balance FROM users").scalar() == 7        # data preserved
        row = c.exec_driver_sql("SELECT updated_at, share_to_library FROM generation_history").one()
        assert row[0] == "2026-01-01 00:00:00" and row[1] == 1                              # backfilled
        assert c.exec_driver_sql("SELECT version_num FROM alembic_version").scalar() == "0014"

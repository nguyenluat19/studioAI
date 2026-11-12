"""Admin pricing dashboard: one source of truth, synced to every charge."""
import shutil
import sys
from pathlib import Path

import pytest

from app import minimax
from app.config import settings
from app.db import SessionLocal
from app.models import GenerationHistory, PricingLog, User
from tests.test_flow import balance, make_template, pay, topup, wait_done

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg missing")


@pytest.fixture()
def setp(client, admin_headers):
    """setp(key, price=None, enabled=None) -> response; everything touched is restored afterwards."""
    touched = {}

    def f(key, price=None, enabled=None):
        if key not in touched:
            cur = next(i for i in client.get("/api/admin/pricing", headers=admin_headers).json()["items"]
                       if i["key"] == key)
            touched[key] = (cur["price"], cur["enabled"])
        body = {k: v for k, v in (("price", price), ("enabled", enabled)) if v is not None}
        return client.put(f"/api/admin/pricing/{key}", headers=admin_headers, json=body)
    yield f
    for key, (p, e) in touched.items():
        client.put(f"/api/admin/pricing/{key}", headers=admin_headers, json={"price": p, "enabled": e})


def items(client, admin_headers):
    return {i["key"]: i for i in client.get("/api/admin/pricing", headers=admin_headers).json()["items"]}


# ---------- the dashboard API ----------
def test_dashboard_lists_every_priced_thing(client, admin_headers):
    d = client.get("/api/admin/pricing", headers=admin_headers).json()
    its = {i["key"]: i for i in d["items"]}
    assert {"render.fast", "render.mimicmotion"} <= set(its)
    assert its["render.fast"]["price"] == 1 and its["render.mimicmotion"]["price"] == 10
    assert d["settings"] == {"usd_vnd": 25000, "vnd_per_credit": 1000, "min_topup_vnd": 20000}
    assert its["render.fast"]["margin_percent"] is None                          # no provider cost known


def test_only_admins_can_see_or_change_prices(client, make_user):
    h, _ = make_user()
    assert client.get("/api/admin/pricing", headers=h).status_code == 403
    assert client.put("/api/admin/pricing/render.fast", headers=h, json={"price": 0}).status_code == 403
    assert client.put("/api/admin/pricing-settings", headers=h, json={"usd_vnd": 1}).status_code == 403
    assert client.put("/api/admin/pricing/render.fast", json={"price": 0}).status_code == 401


def test_validation(client, admin_headers, setp):
    for bad in (-1, 100001, "abc", None):
        r = client.put("/api/admin/pricing/render.fast", headers=admin_headers, json={"price": bad} if bad is not None
                       else {})
        assert r.status_code in (200, 422), r.text            # empty body is a no-op, never an error 500
    assert client.put("/api/admin/pricing/render.fast", headers=admin_headers, json={"price": -1}).status_code == 422
    assert client.put("/api/admin/pricing/render.fast", headers=admin_headers, json={"price": 1e9}).status_code == 422
    assert client.put("/api/admin/pricing/render.fast", headers=admin_headers, json={"price": "x"}).status_code == 422
    assert client.put("/api/admin/pricing/nope.nope", headers=admin_headers, json={"price": 1}).status_code == 404
    assert client.put("/api/admin/pricing-settings", headers=admin_headers, json={"usd_vnd": 0}).status_code == 422
    assert setp("render.fast", 1.239).json()["price"] == 1.24                    # rounded to 2 decimals
    assert items(client, admin_headers)["render.fast"]["price"] == 1.24


def test_change_log_and_reset(client, admin_headers, setp):
    setp("render.fast", 3)
    setp("render.fast", 3)                                                       # unchanged -> no log entry
    setp("render.fast", enabled=False)
    d = client.get("/api/admin/pricing", headers=admin_headers).json()
    mine = [l for l in d["log"] if l["key"] == "render.fast"][:2]
    assert mine[0]["new_enabled"] is False and mine[0]["admin"] == "admin"
    assert mine[1]["old_price"] == 1 and mine[1]["new_price"] == 3
    r = client.post("/api/admin/pricing-reset/render.fast", headers=admin_headers).json()
    assert r["price"] == 1 and r["enabled"] is True and r["price"] == r["default"]
    assert client.post("/api/admin/pricing-reset/zzz", headers=admin_headers).status_code == 404


def test_seed_never_overwrites_admin_edits(client, admin_headers, setp):
    from app import pricing
    setp("render.fast", 7)
    with SessionLocal() as db:
        pricing.seed(db)                                   # what every restart does
        assert pricing.price(db, "render.fast") == 7
    assert client.get("/api/pricing", headers=admin_headers).json()["fast"] == 7


# ---------- sync: every charge follows the dashboard ----------
def test_render_price_change_applies_to_next_job_only(client, make_user, admin_headers, setp):
    h, uid = make_user()
    pay(client, topup(client, h, uid))                                            # 50 credits
    t = make_template(client, h)
    first = client.post("/api/generate", headers=h, json={"template_id": t["id"], "render_type": "fast_remotion"}).json()
    assert first["credits_cost"] == 1
    setp("render.fast", 12.5)
    second = client.post("/api/generate", headers=h, json={"template_id": t["id"], "render_type": "fast_remotion"}).json()
    assert second["credits_cost"] == 12.5
    assert client.get("/api/generations/%d" % first["id"], headers=h).json()["credits_cost"] == 1   # history untouched
    assert balance(uid) == 50 - 1 - 12.5
    assert client.get("/api/pricing", headers=h).json()["fast"] == 12.5          # forms see the same number


def test_free_render_when_price_is_zero(client, make_user, setp):
    h, uid = make_user()                                                          # no credits at all
    setp("render.fast", 0)
    t = make_template(client, h)
    r = client.post("/api/generate", headers=h, json={"template_id": t["id"], "render_type": "fast_remotion"})
    assert r.status_code == 200 and r.json()["credits_cost"] == 0 and balance(uid) == 0


def test_disabled_render_flow_is_refused_without_charge(client, make_user, setp):
    h, uid = make_user()
    pay(client, topup(client, h, uid))
    t = make_template(client, h)
    setp("render.fast", enabled=False)
    r = client.post("/api/generate", headers=h, json={"template_id": t["id"], "render_type": "fast_remotion"})
    assert r.status_code == 422 and "tạm tắt" in r.json()["detail"] and balance(uid) == 50
    assert client.get("/api/pricing", headers=h).json()["fast_enabled"] is False



# ---------- legacy MiniMax template path (video_cost) ----------
def test_video_cost_zero_without_legacy_row(client):
    from app import pricing
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        assert pricing.video_cost(db, 10, "768P") == 0.0
    finally:
        db.close()


def test_video_cost_scales_with_duration(client):
    from app import pricing
    from app.models import PricingItem
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        db.merge(PricingItem(key=pricing.K_H3_768, price=0.5, enabled=True))
        db.commit()
        assert pricing.video_cost(db, 10, "768P") == 5.0
        assert pricing.video_cost(db, 10, "2K") == 0.0   # 2K row absent -> 0
    finally:
        row = db.get(PricingItem, pricing.K_H3_768)
        if row is not None:
            db.delete(row)
            db.commit()
        db.close()

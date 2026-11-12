"""Top-up with a free amount: minimum 20.000đ (admin-editable), credits = amount / đ-per-credit."""
import pytest

from app.config import MAX_TOPUP_VND
from tests.test_flow import balance, pay


@pytest.fixture()
def settings_restore(client, admin_headers):
    yield
    client.put("/api/admin/pricing-settings", headers=admin_headers,
               json={"vnd_per_credit": 1000, "min_topup_vnd": 20000})


def top(client, h, amount):
    return client.post("/api/billing/topup", headers=h, json={"amount_vnd": amount})


def test_default_minimum_is_20k(client, make_user):
    h, _ = make_user()
    cfg = client.get("/api/billing/config", headers=h).json()
    assert cfg["min_vnd"] == 20000 and cfg["vnd_per_credit"] == 1000 and cfg["max_vnd"] == MAX_TOPUP_VND
    assert [q["amount_vnd"] for q in cfg["quick_amounts"]][0] == 20000
    assert top(client, h, 19999).status_code == 422
    assert "20.000đ" in top(client, h, 19999).json()["detail"]
    assert top(client, h, 20000).status_code == 200                 # exactly the minimum is allowed
    assert top(client, h, 0).status_code == 422 and top(client, h, -5000).status_code == 422


def test_any_amount_above_minimum_converts_at_the_rate(client, make_user):
    h, uid = make_user()
    for amount, credits in ((20000, 20), (37500, 37.5), (123456, 123.46), (1_000_000, 1000)):
        tx = top(client, h, amount).json()
        assert tx["amount_vnd"] == amount and tx["credits_added"] == credits, tx
        assert f"amount={amount}" in tx["qr_url"] and tx["transaction_code"] in tx["qr_url"]
    tx = top(client, h, 37500).json()
    assert pay(client, tx).json()["results"][0]["status"] == "success"      # webhook credits the fractional amount
    assert balance(uid) == 37.5


def test_rejects_garbage_and_huge_amounts(client, make_user):
    h, _ = make_user()
    assert top(client, h, MAX_TOPUP_VND + 1).status_code == 422
    assert top(client, h, MAX_TOPUP_VND).status_code == 200
    for bad in ("abc", None, 25000.5, [], {}):
        assert client.post("/api/billing/topup", headers=h, json={"amount_vnd": bad}).status_code == 422
    assert client.post("/api/billing/topup", headers=h, json={}).status_code == 422
    assert client.post("/api/billing/topup", headers=h, json={"package_id": "p50"}).status_code == 422   # old API gone
    assert client.post("/api/billing/topup", json={"amount_vnd": 50000}).status_code == 401


def test_admin_can_change_the_minimum(client, make_user, admin_headers, settings_restore):
    h, _ = make_user()
    assert client.put("/api/admin/pricing-settings", headers=admin_headers,
                      json={"min_topup_vnd": 50000}).json()["min_topup_vnd"] == 50000
    assert top(client, h, 49999).status_code == 422 and top(client, h, 50000).status_code == 200
    cfg = client.get("/api/billing/config", headers=h).json()
    assert cfg["min_vnd"] == 50000 and all(q["amount_vnd"] >= 50000 for q in cfg["quick_amounts"])
    for bad in (0, 500, 6_000_000, "x"):
        assert client.put("/api/admin/pricing-settings", headers=admin_headers,
                          json={"min_topup_vnd": bad}).status_code == 422
    assert client.put("/api/admin/pricing-settings", headers=h, json={"min_topup_vnd": 1000}).status_code == 403
    assert client.get("/api/admin/pricing", headers=admin_headers).json()["settings"]["min_topup_vnd"] == 50000


def test_rate_change_applies_to_new_top_ups_only(client, make_user, admin_headers, settings_restore):
    h, uid = make_user()
    before = top(client, h, 100000).json()
    assert before["credits_added"] == 100
    client.put("/api/admin/pricing-settings", headers=admin_headers, json={"vnd_per_credit": 500})
    after = top(client, h, 100000).json()
    assert after["credits_added"] == 200                                    # new rate
    assert client.get(f"/api/billing/transactions/{before['id']}", headers=h).json()["credits_added"] == 100
    pay(client, before)                                                      # the earlier QR still pays out at ITS rate
    assert balance(uid) == 100
    assert client.get("/api/billing/config", headers=h).json()["vnd_per_credit"] == 500


def test_expiry_and_late_payment_still_apply_to_custom_amounts(client, make_user):
    from tests.test_features import age_tx, tx_status
    h, uid = make_user()
    tx = top(client, h, 33000).json()
    age_tx(tx["id"], 400)
    assert pay(client, tx).json()["results"][0]["status"] == "late_payment"
    assert tx_status(tx["id"]) == "failed" and balance(uid) == 0

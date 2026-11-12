"""Admins add/remove any amount of credits on any account; only users top up."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.test_flow import balance, make_template, pay, topup


def grant(client, admin_headers, uid, amount, reason=None):
    body = {"amount": amount}
    if reason is not None:
        body["reason"] = reason
    return client.post(f"/api/admin/users/{uid}/credits", headers=admin_headers, json=body)


def admin_id(client, admin_headers):
    return client.get("/api/auth/me", headers=admin_headers).json()["id"]


# ---------- admin can add arbitrary amounts ----------
def test_admin_can_add_any_amount(client, make_user, admin_headers):
    h, uid = make_user()
    for amount, expected in ((1, 1), (49.5, 50.5), (1234567.89, 1234618.39), (0.01, 1234618.4)):
        r = grant(client, admin_headers, uid, amount)
        assert r.status_code == 200 and r.json()["credits_balance"] == expected, r.text
    assert client.get("/api/auth/me", headers=h).json()["credits_balance"] == 1234618.4   # the user sees it


def test_credits_granted_are_really_spendable(client, make_user, admin_headers):
    h, uid = make_user()
    t = make_template(client, h)
    assert client.post("/api/generate", headers=h, json={"template_id": t["id"], "render_type": "fast_remotion"}
                       ).status_code == 402                                              # broke
    grant(client, admin_headers, uid, 25, "Tặng thử")
    r = client.post("/api/generate", headers=h, json={"template_id": t["id"], "render_type": "fast_remotion"})
    assert r.status_code == 200 and balance(uid) == 24


def test_admin_can_deduct_but_never_below_zero(client, make_user, admin_headers):
    h, uid = make_user()
    grant(client, admin_headers, uid, 30)
    assert grant(client, admin_headers, uid, -10.5).json()["credits_balance"] == 19.5
    r = grant(client, admin_headers, uid, -19.51)
    assert r.status_code == 422 and "âm" in r.json()["detail"] and balance(uid) == 19.5   # refused, unchanged
    assert grant(client, admin_headers, uid, -19.5).json()["credits_balance"] == 0        # exactly to zero is fine
    assert grant(client, admin_headers, uid, -0.01).status_code == 422


@pytest.mark.parametrize("raw", ['{"amount": 0}', '{"amount": 0.001}', '{"amount": 10000001}',
                                 '{"amount": -10000001}', '{"amount": "abc"}', '{"amount": null}', '{}',
                                 '{"amount": 1e999}', '{"amount": -1e999}', '{"amount": NaN}'])
def test_rejects_zero_huge_and_garbage_amounts(client, make_user, admin_headers, raw):
    h, uid = make_user()
    r = client.post(f"/api/admin/users/{uid}/credits", headers={**admin_headers, "Content-Type": "application/json"},
                    content=raw)
    assert r.status_code == 422 and balance(uid) == 0, (raw, r.text)


def test_can_adjust_any_account_including_admins_and_own(client, make_user, admin_headers):
    aid = admin_id(client, admin_headers)
    before = client.get("/api/auth/me", headers=admin_headers).json()["credits_balance"]
    assert grant(client, admin_headers, aid, 100, "tự nạp để test").json()["credits_balance"] == before + 100
    assert client.get("/api/auth/me", headers=admin_headers).json()["credits_balance"] == before + 100
    grant(client, admin_headers, aid, -100)


def test_unknown_account_and_permissions(client, make_user, admin_headers):
    h, uid = make_user()
    assert grant(client, admin_headers, 99999999, 5).status_code == 404
    assert client.post(f"/api/admin/users/{uid}/credits", headers=h, json={"amount": 5}).status_code == 403
    assert client.post(f"/api/admin/users/{uid}/credits", json={"amount": 5}).status_code == 401
    assert client.get("/api/admin/credit-log", headers=h).status_code == 403
    assert client.get("/api/admin/users", headers=h).status_code == 403
    assert balance(uid) == 0


# ---------- audit trail ----------
def test_every_adjustment_is_logged_with_reason_and_balance(client, make_user, admin_headers):
    h, uid = make_user()
    grant(client, admin_headers, uid, 100, "  Tặng nhân dịp lễ  ")
    grant(client, admin_headers, uid, -40.25, "Hoàn lại do lỗi")
    grant(client, admin_headers, uid, -999)                                              # refused -> must not be logged
    log = client.get(f"/api/admin/credit-log?user_id={uid}", headers=admin_headers).json()
    assert [(l["amount"], l["balance_after"], l["reason"]) for l in log] == [
        (-40.25, 59.75, "Hoàn lại do lỗi"), (100, 100, "Tặng nhân dịp lễ")]               # newest first, reason trimmed
    assert all(l["admin"] == "admin" and l["created_at"].endswith("+00:00") for l in log)
    assert log[0]["username"] and client.get("/api/admin/credit-log", headers=admin_headers).json()[0]["id"] == log[0]["id"]


def test_reason_is_optional_and_capped(client, make_user, admin_headers):
    h, uid = make_user()
    grant(client, admin_headers, uid, 1)
    grant(client, admin_headers, uid, 1, "x" * 500)
    log = client.get(f"/api/admin/credit-log?user_id={uid}", headers=admin_headers).json()
    assert log[1]["reason"] == "" and len(log[0]["reason"]) == 200


def test_user_sees_only_own_adjustments(client, make_user, admin_headers):
    h1, u1 = make_user()
    h2, u2 = make_user()
    grant(client, admin_headers, u1, 10, "cho user 1")
    grant(client, admin_headers, u2, 20, "cho user 2")
    mine = client.get("/api/billing/adjustments", headers=h1).json()
    assert [(a["amount"], a["reason"]) for a in mine] == [(10, "cho user 1")]
    assert "admin" not in mine[0] and client.get("/api/billing/adjustments").status_code == 401


# ---------- concurrency ----------
def test_parallel_deductions_cannot_overdraw(client, make_user, admin_headers):
    h, uid = make_user()
    grant(client, admin_headers, uid, 50)
    with ThreadPoolExecutor(12) as ex:
        codes = list(ex.map(lambda _: grant(client, admin_headers, uid, -10).status_code, range(12)))
    assert codes.count(200) == 5 and codes.count(422) == 7, codes
    assert balance(uid) == 0
    assert len(client.get(f"/api/admin/credit-log?user_id={uid}", headers=admin_headers).json()) == 6   # 1 grant + 5 deductions


def test_parallel_grants_all_count(client, make_user, admin_headers):
    h, uid = make_user()
    with ThreadPoolExecutor(10) as ex:
        list(ex.map(lambda _: grant(client, admin_headers, uid, 7.5), range(10)))
    assert balance(uid) == 75


# ---------- accounts list ----------
def test_account_search(client, make_user, admin_headers):
    h, uid = make_user()
    name = client.get("/api/auth/me", headers=h).json()["username"]
    rows = client.get(f"/api/admin/users?q={name[:10].upper()}", headers=admin_headers).json()   # case-insensitive
    assert [r["id"] for r in rows] == [uid] and rows[0]["credits_balance"] == 0
    assert client.get("/api/admin/users?q=zzzz-nobody-zzzz", headers=admin_headers).json() == []
    assert any(r["role"] == "admin" for r in client.get("/api/admin/users", headers=admin_headers).json())
    assert len(client.get("/api/admin/users?limit=1", headers=admin_headers).json()) == 1


# ---------- only users top up ----------
def test_admin_cannot_top_up_but_users_can(client, make_user, admin_headers):
    r = client.post("/api/billing/topup", headers=admin_headers, json={"amount_vnd": 50000})
    assert r.status_code == 403 and "Tài khoản" in r.json()["detail"]
    h, uid = make_user()
    tx = topup(client, h, uid)
    assert pay(client, tx).json()["results"][0]["status"] == "success" and balance(uid) == 50

"""Lịch sử dòng tiền: topup/refund/chi tiêu/adjustment ghi vào CreditLedgerEntry
và user chỉ thấy các mục của chính mình."""


def topup(client, headers, uid):
    tx = client.post("/api/billing/topup", headers=headers,
                     json={"amount_vnd": 50_000}).json()
    return tx


def pay(client, tx):
    return client.post("/api/webhooks/payment", headers={"Authorization": "Apikey sepay-key"},
                       json={"transferType": "in", "transferAmount": tx["amount_vnd"],
                             "content": f"MBVCB {tx['transaction_code']} chuyen tien"})


def balance(client, headers):
    return client.get("/api/auth/me", headers=headers).json()["credits_balance"]


def test_topup_creates_ledger_row(client, make_user):
    h, uid = make_user()
    tx = topup(client, h, uid)
    r = pay(client, tx)
    assert r.json()["results"][0]["status"] == "success"
    rows = client.get("/api/auth/me/credit-ledger", headers=h).json()
    assert any(row["kind"] == "topup" and row["amount"] == 50.0 for row in rows)


def test_charge_creates_negative_ledger_row(client, make_user):
    h, uid = make_user()
    tx = topup(client, h, uid)
    pay(client, tx)
    from app.db import SessionLocal
    from app.models import User
    from app import credits
    with SessionLocal() as db:
        u = db.get(User, uid)
        bal_before = u.credits_balance
        ok = credits.charge(db, uid, 10.0, reason="Chi tiêu thử")
        assert ok
        db.commit()
    assert abs(balance(client, h) - (bal_before - 10.0)) < 1e-6
    rows = client.get("/api/auth/me/credit-ledger", headers=h).json()
    assert rows[0]["kind"] == "spend" and rows[0]["amount"] == -10.0
    assert "Chi tiêu thử" in rows[0]["reason"]


def test_adjust_creates_adjustment_ledger(client, make_user, admin_headers):
    h, uid = make_user()
    tx = topup(client, h, uid)
    pay(client, tx)
    r = client.post(f"/api/admin/users/{uid}/credits", headers=admin_headers,
                    json={"amount": -10, "reason": "Trừ test"})
    assert r.status_code == 200
    rows = client.get("/api/auth/me/credit-ledger", headers=h).json()
    assert any(row["kind"] == "adjustment" and row["amount"] == -10.0 for row in rows)


def test_ledger_is_private_per_user(client, make_user, admin_headers):
    h1, uid1 = make_user()
    h2, uid2 = make_user()
    tx = topup(client, h1, uid1)
    pay(client, tx)
    # user 2 chưa hề có biến động, ledger phải trống
    rows2 = client.get("/api/auth/me/credit-ledger", headers=h2).json()
    assert rows2 == []
    rows1 = client.get("/api/auth/me/credit-ledger", headers=h1).json()
    assert rows1


def test_feature_policy_reserve_quota_and_refund(client, make_user, admin_headers):
    from app import featurebilling
    from app.db import SessionLocal
    from app.models import User, FeatureUsage
    h, uid = make_user()
    top = topup(client, h, uid)
    pay(client, top)
    with SessionLocal() as db:
        featurebilling.update_policy(db, "support_chat", "test-model", unit_price=2, free_limit=2)
        first = featurebilling.reserve(db, uid, "support_chat", model_id="test-model", units=2, model_cost=1)
        assert first.is_free and first.charge == 2
        featurebilling.finish(db, first.id, success=True, actual_charge=1)
        bal_after_first = db.get(User, uid).credits_balance
        second = featurebilling.reserve(db, uid, "support_chat", model_id="test-model", units=1, model_cost=1)
        assert not second.is_free and second.charge == 3
        featurebilling.finish(db, second.id, success=False)
        assert db.get(User, uid).credits_balance == bal_after_first
        featurebilling.finish(db, second.id, success=False)  # idempotent
        assert db.get(FeatureUsage, second.id).status == "failed"


def test_feature_policy_disables_feature(client, make_user):
    from app import featurebilling
    from app.db import SessionLocal
    from fastapi import HTTPException
    _, uid = make_user()
    with SessionLocal() as db:
        featurebilling.update_policy(db, "support_chat", "disabled-model", enabled=False)
        try:
            featurebilling.reserve(db, uid, "support_chat", model_id="disabled-model")
            assert False, "expected disabled policy to reject usage"
        except HTTPException as exc:
            assert exc.status_code == 403

"""Top-up promotions: 'nạp từ 100k thưởng 10%'."""
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_flow import balance, pay


def iso(delta_hours):
    return (datetime.now(timezone.utc) + timedelta(hours=delta_hours)).isoformat()


@pytest.fixture()
def promo(client, admin_headers):
    """promo(name, tiers, start=None, end=None, enabled=True) -> json; all deleted after the test."""
    made = []

    def f(name="Lễ 30/4", tiers=((100000, 10),), start=None, end=None, enabled=True):
        body = {"name": name, "tiers": [{"min_vnd": a, "bonus_percent": p} for a, p in tiers],
                "start_at": start, "end_at": end, "enabled": enabled}
        r = client.post("/api/admin/promotions", headers=admin_headers, json=body)
        assert r.status_code == 200, r.text
        made.append(r.json()["id"])
        return r.json()
    yield f
    for pid in made:
        client.delete(f"/api/admin/promotions/{pid}", headers=admin_headers)


def quote(client, h, amount):
    r = client.get(f"/api/billing/quote?amount_vnd={amount}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def top(client, h, amount):
    r = client.post("/api/billing/topup", headers=h, json={"amount_vnd": amount})
    assert r.status_code == 200, r.text
    return r.json()


# ---------- the rule: 'từ 100k thưởng 10%' ----------
def test_no_promotion_means_no_bonus(client, make_user):
    h, _ = make_user()
    q = quote(client, h, 100000)
    assert q["bonus_percent"] == 0 and q["bonus_credits"] == 0 and q["total_credits"] == 100 and q["promo_name"] == ""


def test_bonus_applies_from_the_threshold_up(client, make_user, promo):
    h, uid = make_user()
    promo()                                                       # >= 100.000đ -> +10%
    assert quote(client, h, 99999)["bonus_credits"] == 0          # one đồng short
    assert quote(client, h, 100000) == {**quote(client, h, 100000), "bonus_percent": 10, "bonus_credits": 10,
                                        "total_credits": 110, "promo_name": "Lễ 30/4"}
    assert quote(client, h, 250000)["total_credits"] == 275       # any amount above, not just the threshold
    tx = top(client, h, 100000)
    assert tx["credits_added"] == 110 and tx["bonus_credits"] == 10 and tx["base_credits"] == 100
    assert tx["promo_name"] == "Lễ 30/4"
    assert pay(client, tx).json()["results"][0]["status"] == "success"
    assert balance(uid) == 110                                    # the webhook credits base + bonus, no human needed


def test_below_threshold_gets_nothing(client, make_user, promo):
    h, uid = make_user()
    promo()
    tx = top(client, h, 50000)
    assert tx["credits_added"] == 50 and tx["bonus_credits"] == 0 and tx["promo_name"] == ""


def test_higher_tiers_pay_more(client, make_user, promo):
    h, _ = make_user()
    promo(tiers=((100000, 10), (500000, 15), (1000000, 20)))
    assert [quote(client, h, a)["bonus_percent"] for a in (99999, 100000, 499999, 500000, 999999, 1000000)] == \
           [0, 10, 10, 15, 15, 20]
    assert quote(client, h, 1000000)["total_credits"] == 1200


def test_bonus_rounds_to_two_decimals(client, make_user, promo):
    h, _ = make_user()
    promo(tiers=((20000, 7.5),))
    q = quote(client, h, 33333)                                   # 33.33 credits * 7.5% = 2.5
    assert q["base_credits"] == 33.33 and q["bonus_credits"] == 2.5 and q["total_credits"] == 35.83


def test_bonus_is_computed_on_the_current_credit_rate(client, make_user, promo, admin_headers):
    h, _ = make_user()
    promo()
    try:
        client.put("/api/admin/pricing-settings", headers=admin_headers, json={"vnd_per_credit": 500})
        q = quote(client, h, 100000)
        assert q["base_credits"] == 200 and q["bonus_credits"] == 20
    finally:
        client.put("/api/admin/pricing-settings", headers=admin_headers, json={"vnd_per_credit": 1000})


# ---------- schedule, switch, stacking ----------
def test_schedule_window_and_switch(client, make_user, promo, admin_headers):
    h, _ = make_user()
    soon = promo("Sắp tới", start=iso(2), end=iso(5))
    old = promo("Đã qua", start=iso(-5), end=iso(-1))
    off = promo("Tắt", enabled=False)
    now_ = promo("Đang chạy", tiers=((20000, 5),), start=iso(-1), end=iso(1))
    states = {p["name"]: p["state"] for p in client.get("/api/admin/promotions", headers=admin_headers).json()}
    assert states["Sắp tới"] == "scheduled" and states["Đã qua"] == "expired"
    assert states["Tắt"] == "disabled" and states["Đang chạy"] == "active"
    q = quote(client, h, 100000)
    assert q["promo_name"] == "Đang chạy" and q["bonus_percent"] == 5   # only the live one counts
    cfg = client.get("/api/billing/config", headers=h).json()
    assert [p["name"] for p in cfg["promotions"]] == ["Đang chạy"]
    client.put(f"/api/admin/promotions/{now_['id']}", headers=admin_headers,
               json={"name": "Đang chạy", "tiers": now_["tiers"], "enabled": False})
    assert quote(client, h, 100000)["bonus_credits"] == 0                # switched off -> gone immediately


def test_open_ended_campaign_has_no_dates(client, make_user, promo):
    h, _ = make_user()
    promo("Không hạn", start=None, end=None)
    assert quote(client, h, 100000)["bonus_percent"] == 10


def test_overlapping_campaigns_do_not_stack_best_wins(client, make_user, promo):
    h, _ = make_user()
    promo("A", tiers=((100000, 10),))
    promo("B", tiers=((100000, 12), (500000, 25)))
    promo("C", tiers=((200000, 30),))
    q = quote(client, h, 100000)
    assert q["bonus_percent"] == 12 and q["promo_name"] == "B"            # not 22
    assert quote(client, h, 200000)["promo_name"] == "C" and quote(client, h, 200000)["bonus_percent"] == 30
    assert quote(client, h, 500000)["bonus_percent"] == 30                # C's 30 beats B's 25 here


def test_bonus_is_locked_when_the_qr_is_created(client, make_user, promo, admin_headers):
    h, uid = make_user()
    p = promo()
    tx = top(client, h, 100000)
    client.delete(f"/api/admin/promotions/{p['id']}", headers=admin_headers)    # promotion ends while QR is pending
    assert quote(client, h, 100000)["bonus_credits"] == 0
    assert pay(client, tx).json()["results"][0]["status"] == "success"
    assert balance(uid) == 110                                            # still honoured
    assert client.get("/api/billing/transactions", headers=h).json()[0]["promo_name"] == "Lễ 30/4"


def test_promotion_created_later_does_not_change_existing_qr(client, make_user, promo):
    h, uid = make_user()
    tx = top(client, h, 100000)
    promo()
    pay(client, tx)
    assert balance(uid) == 100


def test_expired_qr_never_gets_bonus_unless_admin_approves_with_it(client, make_user, promo, admin_headers):
    from tests.test_features import age_tx
    h, uid = make_user()
    promo()
    tx = top(client, h, 100000)
    age_tx(tx["id"], 400)
    assert pay(client, tx).json()["results"][0]["status"] == "late_payment" and balance(uid) == 0
    assert client.post(f"/api/admin/transactions/{tx['id']}/approve", headers=admin_headers).status_code == 200
    assert balance(uid) == 110                                            # approval honours what the QR promised


def test_quick_amounts_show_the_bonus(client, make_user, promo):
    h, _ = make_user()
    promo(tiers=((100000, 10),))
    quick = {q["amount_vnd"]: q for q in client.get("/api/billing/config", headers=h).json()["quick_amounts"]}
    assert quick[50000]["bonus_percent"] == 0 and quick[50000]["total_credits"] == 50
    assert quick[100000]["bonus_percent"] == 10 and quick[100000]["total_credits"] == 110
    assert quick[500000]["total_credits"] == 550


# ---------- admin API ----------
def test_admin_crud_and_permissions(client, make_user, promo, admin_headers):
    h, _ = make_user()
    body = {"name": "x", "tiers": [{"min_vnd": 100000, "bonus_percent": 10}]}
    assert client.get("/api/admin/promotions", headers=h).status_code == 403
    assert client.post("/api/admin/promotions", headers=h, json=body).status_code == 403
    assert client.delete("/api/admin/promotions/1", headers=h).status_code == 403
    p = promo("Gốc")
    r = client.put(f"/api/admin/promotions/{p['id']}", headers=admin_headers,
                   json={"name": "  Đổi tên ", "tiers": [{"min_vnd": 200000, "bonus_percent": 20},
                                                         {"min_vnd": 50000, "bonus_percent": 5}]})
    assert r.json()["name"] == "Đổi tên" and [t["min_vnd"] for t in r.json()["tiers"]] == [50000, 200000]  # sorted
    assert client.put("/api/admin/promotions/99999", headers=admin_headers, json=body).status_code == 404
    assert client.delete("/api/admin/promotions/99999", headers=admin_headers).status_code == 404


@pytest.mark.parametrize("tiers,start,end,needle", [
    ([], None, None, "ít nhất một mức"),
    ([{"min_vnd": 100000, "bonus_percent": 0}], None, None, "lớn hơn 0"),
    ([{"min_vnd": 100000, "bonus_percent": -5}], None, None, "lớn hơn 0"),
    ([{"min_vnd": 100000, "bonus_percent": 301}], None, None, "300"),
    ([{"min_vnd": 500, "bonus_percent": 10}], None, None, "1.000đ"),
    ([{"min_vnd": 100000, "bonus_percent": 10}, {"min_vnd": 100000, "bonus_percent": 20}], None, None, "Trùng"),
    ([{"min_vnd": 100000, "bonus_percent": 10}], iso(5), iso(1), "sau thời điểm bắt đầu"),
])
def test_validation(client, admin_headers, tiers, start, end, needle):
    r = client.post("/api/admin/promotions", headers=admin_headers,
                    json={"name": "bad", "tiers": tiers, "start_at": start, "end_at": end})
    assert r.status_code == 422 and needle in r.text, r.text
    assert client.post("/api/admin/promotions", headers=admin_headers,
                       json={"name": "  ", "tiers": [{"min_vnd": 100000, "bonus_percent": 10}]}).status_code == 422
    assert client.post("/api/admin/promotions", headers=admin_headers,
                       json={"name": "x", "tiers": [{"min_vnd": "abc", "bonus_percent": 10}]}).status_code == 422


def test_quote_validates_input(client, make_user):
    h, _ = make_user()
    assert client.get("/api/billing/quote?amount_vnd=-1", headers=h).status_code == 422
    assert client.get("/api/billing/quote?amount_vnd=999999999999", headers=h).status_code == 422
    assert client.get("/api/billing/quote?amount_vnd=abc", headers=h).status_code == 422
    assert client.get("/api/billing/quote?amount_vnd=100000").status_code == 401


def test_deleting_a_promotion_keeps_past_transactions(client, make_user, promo, admin_headers):
    h, uid = make_user()
    p = promo()
    tx = top(client, h, 100000)
    pay(client, tx)
    client.delete(f"/api/admin/promotions/{p['id']}", headers=admin_headers)
    row = client.get("/api/billing/transactions", headers=h).json()[0]
    assert row["bonus_credits"] == 10 and row["promo_name"] == "Lễ 30/4" and balance(uid) == 110


def test_dates_are_sent_with_an_explicit_utc_offset(client, make_user, promo, admin_headers):
    h, _ = make_user()
    p = promo("Giờ", start=iso(-1), end=iso(1))
    assert p["start_at"].endswith("+00:00") and p["end_at"].endswith("+00:00")   # browsers must not read it as local
    listed = next(x for x in client.get("/api/admin/promotions", headers=admin_headers).json() if x["id"] == p["id"])
    assert listed["end_at"].endswith("+00:00")
    assert client.get("/api/billing/config", headers=h).json()["promotions"][0]["ends_at"].endswith("+00:00")

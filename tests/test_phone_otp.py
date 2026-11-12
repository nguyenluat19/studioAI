"""Đăng ký & xác minh số điện thoại (OTP qua SMS).

Tính năng xác minh SĐT đang TẮT tạm thời (REQUIRE_PHONE_VERIFICATION=0) → đăng ký
không cần số điện thoại. Các test dưới đây bật cờ `require_phone_verification` để
kiểm tra lại đầy đủ luồng OTP (để bật lại tính năng chỉ cần đặt cờ trong .env).
"""
import pytest

from app import otp as otp_mod
from app.config import settings


@pytest.fixture()
def phone_on(monkeypatch):
    """Bật xác minh số điện thoại cho test."""
    monkeypatch.setattr(settings, "require_phone_verification", True)


def test_normalize_phone():
    assert otp_mod.normalize_phone("0912345678") == "0912345678"
    assert otp_mod.normalize_phone("+84 912 345 678") == "0912345678"
    assert otp_mod.normalize_phone("84912345678") == "0912345678"
    assert otp_mod.normalize_phone("12345") is None
    assert otp_mod.normalize_phone("0211234567") is None      # số cố định
    assert otp_mod.normalize_phone("") is None


# ─── Tính năng đang TẮT: đăng ký không cần SĐT ───

def test_register_without_phone_allowed_when_verification_off(client):
    r = client.post("/api/auth/register", json={"username": "nophone", "email": "np@x.io",
                                                "password": "password123"})
    assert r.status_code == 200, r.text
    assert r.json()["token"]
    lg = client.post("/api/auth/login", json={"username": "nophone", "password": "password123"})
    assert lg.status_code == 200


def test_register_ignores_invalid_phone_when_off(client):
    """Số điện thoại sai ở trạng thái tắt -> bỏ qua, không chặn đăng ký."""
    r = client.post("/api/auth/register", json={"username": "badphone", "email": "bp@x.io",
                                                "password": "password123", "phone": "123"})
    assert r.status_code == 200, r.text


def test_otp_endpoints_disabled_when_off(client):
    v = client.post("/api/auth/verify-phone", json={"username": "nophone", "code": "123456"})
    assert v.status_code == 409
    r = client.post("/api/auth/resend-otp", json={"username": "nophone"})
    assert r.status_code == 409


# ─── Khi BẬT lại xác minh SĐT ───

def test_register_requires_phone(client, phone_on):
    r = client.post("/api/auth/register", json={"username": "nophone2", "email": "np2@x.io",
                                                "password": "password123"})
    assert r.status_code == 422


def test_register_rejects_bad_phone(client, phone_on):
    r = client.post("/api/auth/register", json={"username": "badphone2", "email": "bp2@x.io",
                                                "password": "password123", "phone": "123"})
    assert r.status_code == 422


def test_register_dev_mode_auto_verifies(client, monkeypatch, phone_on):
    """Không có ESMS + APP_ENV != production → tự xác minh (để dev/test chạy được)."""
    monkeypatch.setattr(otp_mod, "sms_ready", lambda: False)
    monkeypatch.setattr(settings, "app_env", "dev")
    r = client.post("/api/auth/register", json={"username": "devuser", "email": "dv@x.io",
                                                "password": "password123", "phone": "0977777001"})
    assert r.status_code == 200, r.text
    assert r.json()["token"]


def test_register_production_without_sms_refuses(client, monkeypatch, phone_on):
    monkeypatch.setattr(otp_mod, "sms_ready", lambda: False)
    monkeypatch.setattr(settings, "app_env", "production")
    r = client.post("/api/auth/register", json={"username": "produser", "email": "pr@x.io",
                                                "password": "password123", "phone": "0977777002"})
    assert r.status_code == 503


def test_otp_flow_send_verify(client, monkeypatch, phone_on):
    """Có SMS: đăng ký trả need_verify, xác minh đúng mã thì mới vào được."""
    monkeypatch.setattr(otp_mod, "sms_ready", lambda: True)
    sent = {}

    def fake_send(phone, content):
        sent["phone"] = phone
        sent["content"] = content
        return True

    monkeypatch.setattr(otp_mod, "sms_send", fake_send)

    r = client.post("/api/auth/register", json={"username": "otpuser", "email": "ot@x.io",
                                                "password": "password123", "phone": "0977777003"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["need_verify"] is True
    assert "token" not in body
    assert sent["phone"] == "0977777003"
    code = "".join(ch for ch in sent["content"] if ch.isdigit())[-6:]
    assert len(code) == 6

    # Mã sai → bị từ chối
    bad = client.post("/api/auth/verify-phone", json={"username": "otpuser", "code": "000000"})
    assert bad.status_code == 400

    # Đăng nhập khi chưa xác minh → bị chặn 403 kèm cờ need_verify
    lg = client.post("/api/auth/login", json={"username": "otpuser", "password": "password123"})
    assert lg.status_code == 403
    assert lg.json()["detail"]["need_verify"] is True

    # Mã đúng → trả token
    ok = client.post("/api/auth/verify-phone", json={"username": "otpuser", "code": code})
    assert ok.status_code == 200, ok.text
    assert ok.json()["token"]

    # Đã xác minh → đăng nhập được
    lg2 = client.post("/api/auth/login", json={"username": "otpuser", "password": "password123"})
    assert lg2.status_code == 200


def test_resend_otp_rate_limited(client, monkeypatch, phone_on):
    monkeypatch.setattr(otp_mod, "sms_ready", lambda: True)
    monkeypatch.setattr(otp_mod, "sms_send", lambda p, c: True)
    r = client.post("/api/auth/register", json={"username": "resenduser", "email": "rs@x.io",
                                                "password": "password123", "phone": "0977777004"})
    assert r.status_code == 200
    codes = [client.post("/api/auth/resend-otp", json={"username": "resenduser"}).status_code
             for _ in range(6)]
    assert 429 in codes      # vượt giới hạn gửi/giờ


def test_duplicate_phone_rejected(client, monkeypatch, phone_on):
    monkeypatch.setattr(otp_mod, "sms_ready", lambda: False)
    monkeypatch.setattr(settings, "app_env", "dev")
    first = client.post("/api/auth/register", json={"username": "ph1", "email": "ph1@x.io",
                                                    "password": "password123", "phone": "0977777005"})
    assert first.status_code == 200
    second = client.post("/api/auth/register", json={"username": "ph2", "email": "ph2@x.io",
                                                     "password": "password123", "phone": "0977777005"})
    assert second.status_code == 409

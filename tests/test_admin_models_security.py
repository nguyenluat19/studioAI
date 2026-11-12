import socket
import pytest


@pytest.mark.parametrize("url,allowed", [
    ("http://127.0.0.1:8080", False),
    ("http://10.0.0.8", False),
    ("http://169.254.169.254/latest/meta-data", False),
    ("https://public-api.example.com", True),
])
def test_admin_model_blocks_private_ip_literals(client, admin_headers, url, allowed):
    r = client.post("/api/admin/models", headers=admin_headers, json={
        "name": "SSRF Test " + url,
        "step": "llm",
        "base_url": url,
        "api_key": "sk-test-key",
        "model_name": "model",
    })
    assert (r.status_code == 200) is allowed
    if allowed:
        mid = r.json()["model"]["id"]
        client.delete(f"/api/admin/models/{mid}", headers=admin_headers)


def test_admin_model_blocks_dns_to_private_ip(client, admin_headers, monkeypatch):
    from app import adminmodels

    monkeypatch.setattr(adminmodels.settings, "app_env", "production")
    monkeypatch.setattr(adminmodels.settings, "allow_private_model_urls", False)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("10.1.2.3", 443))])
    r = client.post("/api/admin/models", headers=admin_headers, json={
        "name": "SSRF DNS Test", "step": "llm", "base_url": "https://internal.example",
        "api_key": "sk-test-key", "model_name": "model",
    })
    assert r.status_code == 422
    assert "mạng nội bộ" in r.json()["detail"]

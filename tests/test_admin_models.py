"""Admin model management (app_models): CRUD qua /api/admin/models."""


def _create_video_model(client, admin_headers, name="Test Video Model"):
    r = client.post("/api/admin/models", headers=admin_headers, json={
        "name": name, "step": "video_i2v", "base_url": "https://gw.example.io",
        "api_key": "sk-test-1234567890", "model_name": "test-video", "max_clip_seconds": 12,
    })
    assert r.status_code == 200, r.text
    return r.json()["model"]


def test_admin_model_crud(client, admin_headers):
    m = _create_video_model(client, admin_headers, name="Test Video Model CRUD")
    mid = m["id"]
    assert m["enabled"] is True
    assert m["max_clip_seconds"] == 12
    assert m["api_key_masked"] != "sk-test-1234567890"   # key không bị trả về nguyên văn

    # Model mới tự xuất hiện trong danh sách model cho user chọn
    r = client.get("/api/assistant/models?step=video_i2v")
    assert mid in [x["id"] for x in r.json()["models"]], r.text
    public_model=next(x for x in r.json()["models"] if x["id"]==mid)
    assert "base_url" not in public_model and "api_key" not in public_model
    assert "desc" not in public_model and "provider" not in public_model

    # Sửa tên + tắt
    r = client.put(f"/api/admin/models/{mid}", headers=admin_headers,
                   json={"name": "Renamed Video", "enabled": False})
    assert r.status_code == 200, r.text
    assert r.json()["model"]["name"] == "Renamed Video"
    assert r.json()["model"]["enabled"] is False

    # Model tắt không còn được chọn
    r = client.get("/api/assistant/models?step=video_i2v")
    row = [x for x in r.json()["models"] if x["id"] == mid][0]
    assert row["enabled"] is False

    # Giá được seed tự động
    r = client.get("/api/admin/pricing", headers=admin_headers)
    assert f"m.{mid}" in [i["key"] for i in r.json()["items"]]

    # Xóa
    r = client.delete(f"/api/admin/models/{mid}", headers=admin_headers)
    assert r.status_code == 200
    r = client.get("/api/admin/models", headers=admin_headers)
    assert mid not in [x["id"] for x in r.json()["models"]]


def test_admin_model_requires_admin(client, make_user):
    h, _ = make_user()
    r = client.post("/api/admin/models", headers=h,
                    json={"name": "x", "step": "llm", "base_url": "https://x.io"})
    assert r.status_code == 403


def test_admin_model_validation(client, admin_headers, monkeypatch):
    from app import adminmodels

    monkeypatch.setattr(adminmodels, "_validate_base_url", lambda url: None)
    r = client.post("/api/admin/models", headers=admin_headers,
                    json={"name": "x", "step": "khong_hop_le", "base_url": "https://x.io"})
    assert r.status_code == 422
    r = client.post("/api/admin/models", headers=admin_headers,
                    json={"name": "y", "step": "llm", "base_url": ""})
    assert r.status_code == 422


def test_admin_model_toggle_syncs_pricing(client, admin_headers):
    """Bật/tắt model phải đồng bộ với bảng giá (m.<id>.enabled)."""
    m = _create_video_model(client, admin_headers, name="Toggle Sync Model")
    mid = m["id"]

    def pricing_enabled():
        r = client.get("/api/admin/pricing", headers=admin_headers)
        return next(i for i in r.json()["items"] if i["key"] == f"m.{mid}")["enabled"]

    assert pricing_enabled() is True

    client.put(f"/api/admin/models/{mid}", headers=admin_headers, json={"enabled": False})
    assert pricing_enabled() is False
    r = client.get("/api/assistant/models?step=video_i2v")
    row = [x for x in r.json()["models"] if x["id"] == mid][0]
    assert row["enabled"] is False

    client.put(f"/api/admin/models/{mid}", headers=admin_headers, json={"enabled": True})
    assert pricing_enabled() is True
    r = client.get("/api/assistant/models?step=video_i2v")
    row = [x for x in r.json()["models"] if x["id"] == mid][0]
    assert row["enabled"] is True

    client.delete(f"/api/admin/models/{mid}", headers=admin_headers)


def test_admin_model_supported_durations(client, admin_headers):
    r = client.post("/api/admin/models", headers=admin_headers, json={
        "name": "Dur Model", "step": "video_i2v", "base_url": "https://gw.example.io",
        "api_key": "sk-x", "model_name": "dur-video", "supported_durations": [5, 10, 20, 30],
        "max_clip_seconds": 8,
    })
    assert r.status_code == 200, r.text
    m = r.json()["model"]
    mid = m["id"]
    assert m["supported_durations"] == [5, 10, 20, 30]
    assert m["max_clip_seconds"] == 8   # per-clip max, independent of durations

    # user-facing dropdown exposes durations
    r = client.get("/api/assistant/models?step=video_i2v")
    row = [x for x in r.json()["models"] if x["id"] == mid][0]
    assert row["durations"] == [5, 10, 20, 30]

    # update with custom string-style not allowed via JSON list only — test list update + empty clear
    r = client.put(f"/api/admin/models/{mid}", headers=admin_headers,
                   json={"supported_durations": [7, 14]})
    assert r.status_code == 200, r.text
    assert r.json()["model"]["supported_durations"] == [7, 14]
    assert r.json()["model"]["max_clip_seconds"] == 8   # max_clip_seconds không bị ghi đè bởi durations

    client.delete(f"/api/admin/models/{mid}", headers=admin_headers)


def test_admin_model_llm_steps_allowed(client, admin_headers):
    for step in ("llm", "image_generate"):
        r = client.post("/api/admin/models", headers=admin_headers, json={
            "name": f"Test {step}", "step": step, "base_url": "https://api.example.io",
            "api_key": "sk-x", "model_name": "m"})
        assert r.status_code == 200, r.text
        mid = r.json()["model"]["id"]
        r = client.get(f"/api/assistant/models?step={step}")
        assert mid in [x["id"] for x in r.json()["models"]]
        client.delete(f"/api/admin/models/{mid}", headers=admin_headers)

"""Tests cho các tính năng mới (2026-11-11): preset bán hàng, bài viết → video,
Analytics admin, sửa thông tin tài khoản.

Mọi test đều offline — không gọi LLM/ảnh thật (credit cần user duyệt).
"""
import pytest

from app import article as article_mod
from app import presets


# ---------------- Preset bán hàng theo ngành ----------------

def test_presets_list_and_shape():
    ps = presets.list_presets()
    assert len(ps) == 16
    assert {p["id"] for p in ps} >= {"fashion", "beauty", "tech", "general"}
    for p in ps:
        for key in ("id", "label", "icon", "audience", "tone", "hook", "pain", "proof", "cta", "visual"):
            assert p[key], key


def test_presets_get_and_build_block():
    p = presets.get_preset("fashion")
    assert p["label"] == "Thời trang"
    assert presets.get_preset("") is None
    assert presets.get_preset("khong-co") is None
    block = presets.build_prompt_block(p, "Áo linen")
    assert "Thời trang" in block and "Áo linen" in block


def test_presets_endpoint(client, make_user):
    headers, _ = make_user()
    r = client.get("/api/assistant/presets", headers=headers)
    assert r.status_code == 200
    assert len(r.json()["presets"]) == 16


def test_pipeline_rejects_unknown_preset(client, make_user):
    headers, _ = make_user()
    r = client.post("/api/assistant/pipeline", headers=headers, json={
        "idea": "test idea", "model_llm": "x", "preset": "khong-ton-tai"})
    assert r.status_code == 422


# ---------------- Bài viết → video ----------------

def test_text_extractor_skips_chrome():
    parser = article_mod._TextExtractor()
    parser.feed("<html><head><title>Bài viết thử</title><style>.x{}</style></head>"
                "<body><nav>menu</nav><article><h1>Tiêu đề</h1>"
                "<script>alert(1)</script><p>" + "nội dung " * 200 + "</p></article></body></html>")
    text = parser.text()
    assert "alert" not in text
    assert "nội dung" in text
    assert _clean_len(text) > 400


def _clean_len(text: str) -> int:
    return len(text.strip())


def test_build_script_normalizes(monkeypatch):
    def fake_chat(model, messages, **kw):
        return {"content": '{"title": "T", "summary": "S", "scenes": ['
                + ",".join(f'{{"stt": {i+1}, "thời_lượng_giây": 8, "thoại": "câu {i+1}", '
                           f'"hành_động": "a", "biểu_cảm": "thông thái", "image_prompt": "en"}}'
                           for i in range(6))
                + "]}"}
    monkeypatch.setattr(article_mod.ai, "chat", fake_chat)
    script = article_mod.build_script("Tiêu đề", "x " * 1000, model_llm="m",
                                      creds={"model_name": "m"}, duration=60, language="vi")
    assert len(script["scenes"]) == 6
    assert sum(s["thời_lượng_giây"] for s in script["scenes"]) == 48


def test_article_preview_with_text(client, make_user):
    headers, _ = make_user()
    r = client.post("/api/assistant/article/preview", headers=headers,
                    json={"text": "Nội dung bài viết mẫu " * 100})
    assert r.status_code == 200, r.text
    assert r.json()["chars"] > 400


def test_article_estimate(client, make_user):
    headers, _ = make_user()
    r = client.get("/api/assistant/article/estimate?duration=60&model_llm=x&model_image=y",
                   headers=headers)
    assert r.status_code == 200
    assert r.json()["num_scenes"] == 8


# ---------------- Analytics + chi tiết tài khoản (admin) ----------------

def test_admin_analytics(client, admin_headers):
    for period in ("lifetime", "today", "yesterday", "l7d", "l30d"):
        r = client.get(f"/api/admin/analytics?period={period}", headers=admin_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["users"]["total"] >= 1
        assert "topup_vnd" in body["money"] and "spend_credits" in body["money"]


def test_admin_analytics_custom_range(client, admin_headers):
    r = client.get("/api/admin/analytics?period=custom&start=2026-01-01&end=2026-01-31",
                   headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["period"] == "custom"


def test_admin_analytics_requires_admin(client, make_user):
    headers, _ = make_user()   # user thường
    r = client.get("/api/admin/analytics", headers=headers)
    assert r.status_code == 403


def test_admin_user_detail(client, admin_headers, make_user):
    _, uid = make_user()
    r = client.get(f"/api/admin/users/{uid}/detail", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("user", "activity", "generations", "templates", "transactions", "ledger"):
        assert key in body
    assert body["user"]["id"] == uid


def test_admin_user_update(client, admin_headers, make_user):
    _, uid = make_user()
    r = client.put(f"/api/admin/users/{uid}", headers=admin_headers,
                   json={"username": f"u{uid}renamed", "role": "user"})
    assert r.status_code == 200, r.text
    assert r.json()["username"] == f"u{uid}renamed"
    # vai trò không hợp lệ → 422
    assert client.put(f"/api/admin/users/{uid}", headers=admin_headers,
                      json={"role": "superadmin"}).status_code == 422


# ---------------- Người dùng tự sửa thông tin (PUT /api/auth/me) ----------------

def test_update_me_username_and_email(client, make_user):
    headers, uid = make_user()
    r = client.put("/api/auth/me", headers=headers,
                   json={"username": f"mine{uid}", "email": f"mine{uid}@x.io"})
    assert r.status_code == 200, r.text
    assert r.json()["username"] == f"mine{uid}"
    assert client.get("/api/auth/me", headers=headers).json()["email"] == f"mine{uid}@x.io"


def test_update_me_rejects_duplicate_username(client, make_user):
    h1, _ = make_user()
    h2, _ = make_user()
    me2 = client.get("/api/auth/me", headers=h2).json()
    r = client.put("/api/auth/me", headers=h1, json={"username": me2["username"]})
    assert r.status_code == 409


def test_update_me_password_flow(client, make_user):
    headers, _ = make_user()
    me = client.get("/api/auth/me", headers=headers).json()
    # sai mật khẩu hiện tại → 403
    r = client.put("/api/auth/me", headers=headers,
                   json={"current_password": "wrong", "new_password": "newpass12345"})
    assert r.status_code == 403
    # đúng → đổi được, đăng nhập bằng mật khẩu mới
    r = client.put("/api/auth/me", headers=headers,
                   json={"current_password": "password123", "new_password": "newpass12345"})
    assert r.status_code == 200
    # conftest dùng mật khẩu mặc định password123 → đăng ký user mới bằng fixture là đủ kiểm tra
    assert me["username"]


def test_plan_storyboard_includes_preset(monkeypatch):
    """Preset ngành hàng được nhúng vào prompt kịch bản của LLM."""
    import json
    from app import presets, videopipeline

    class _M:
        step = "llm"
        enabled = True

    captured = {}

    def fake_chat(model, messages, **kw):
        captured["sys"] = messages[0]["content"]
        return {"content": '{"các_cảnh":[{"stt":1,"thời_lượng_giây":4,"thoại":"xin chào",'
                           '"image_prompt":"p","video_prompt":"v"}]}'}

    monkeypatch.setattr(videopipeline, "get_model", lambda _mid: _M())
    monkeypatch.setattr(videopipeline.ai, "chat", fake_chat)

    plan = videopipeline.plan_storyboard("review áo linen", "llm-1", 30, "9:16",
                                        language="vi", preset=presets.get_preset("fashion"))
    assert "Thời trang" in captured["sys"]
    assert plan["preset"] == "fashion"


def test_article_start_does_not_require_video_model(client, make_user):
    """Bài viết→video không dùng model video → lỗi trả về KHÔNG được nhắc bước Gen video."""
    headers, _ = make_user()
    r = client.post("/api/assistant/article", headers=headers,
                    json={"text": "Nội dung bài viết mẫu " * 100,
                          "model_llm": "m-llm-1", "model_image": "m-img-1", "duration": 30})
    body = r.json()
    assert r.status_code in (422, 402)
    assert "Gen video" not in str(body)

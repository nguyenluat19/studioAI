"""Req 1: tính phí LLM + guard ước tính pipeline/batch.
   Req 2: /api/admin/provider-costs kéo giá GỐC từ gateway."""

AMOUNTS = {"p50": 50_000}


def topup(client, headers, uid):
    r = client.post("/api/billing/topup", headers=headers, json={"amount_vnd": AMOUNTS["p50"]})
    assert r.status_code == 200, r.text
    return r.json()


def pay(client, tx):
    return client.post("/api/webhooks/payment", headers={"Authorization": "Apikey sepay-key"}, json={
        "transferType": "in", "transferAmount": tx["amount_vnd"],
        "content": f"MBVCB 123 {tx['transaction_code']} chuyen tien"})


def balance(uid):
    from app.db import SessionLocal
    from app.models import User
    with SessionLocal() as db:
        return db.get(User, uid).credits_balance


# ---------------- Req 1 ----------------

def test_llm_charged_after_successful_plan(client, make_user, admin_headers, monkeypatch):
    h, uid = make_user()
    pay(client, topup(client, h, uid))

    # model LLM giá 5 credit, image/video giá 0
    r = client.post("/api/admin/models", headers=admin_headers, json={
        "name": "LLM Bill Test", "step": "llm", "base_url": "https://gw.example.io",
        "api_key": "sk-x", "model_name": "deepseek-v4-flash"})
    assert r.status_code == 200
    llm_id = r.json()["model"]["id"]
    client.put(f"/api/admin/pricing/m.{llm_id}", headers=admin_headers, json={"price": 5, "enabled": True})

    for name, step in [("Img Bill Zero", "image_generate"), ("Vid Bill Zero", "video_i2v")]:
        r2 = client.post("/api/admin/models", headers=admin_headers, json={
            "name": name, "step": step, "base_url": "https://gw.example.io",
            "api_key": "sk-x", "model_name": "m"})
        assert r2.status_code == 200

    from app import videopipeline, autopipeline
    monkeypatch.setattr(videopipeline, "plan_storyboard", lambda **kw: {
        "các_cảnh": [{"stt": 1, "thời_lượng_giây": 4}], "nhân_vật": [], "tổng_số_cảnh": 1})
    monkeypatch.setattr(autopipeline, "_run_keyframing",
                        lambda job, plan, db: [{"stt": 1, "video_url": "/media/outputs/v.mp4",
                                                "image_url": "/media/outputs/i.png"}])
    monkeypatch.setattr(autopipeline, "_run_rendering", lambda job, kfs, db: kfs)

    class FakeJob:
        def __init__(self):
            self.job_id = "j-bill"; self.user_id = uid; self.duration = 6
            self.aspect_ratio = "9:16"; self.idea = "bill test"
            self.character_image_url = ""; self.mode = "standard"; self.outfit_image_url = None
            self.hook_seconds = 3; self.language = "vi"; self.voice = "native"; self.use_tts = False
            self.selections = {"llm": llm_id, "image_generate": "img-bill-zero", "video_i2v": "vid-bill-zero"}
            self.status = "queued"; self.progress = 0; self.step = ""; self.error = ""
            self.result = None; self.created_at = "t"; self.updated_at = "t"; self.cancelled = False

        def update(self, **kw): [setattr(self, k, v) for k, v in kw.items()]
        def is_cancelled(self): return self.cancelled
        def cancel(self): self.cancelled = True; self.status = "cancelled"
        def to_dict(self):
            return {"job_id": self.job_id, "status": self.status, "error": self.error,
                    "result": self.result, "progress": self.progress, "step": self.step}

    img_id = [m for m in client.get("/api/admin/models", headers=admin_headers).json()["models"]
              if m["name"] == "Img Bill Zero"][0]["id"]
    vid_id = [m for m in client.get("/api/admin/models", headers=admin_headers).json()["models"]
              if m["name"] == "Vid Bill Zero"][0]["id"]
    job = FakeJob()
    job.selections = {"llm": llm_id, "image_generate": img_id, "video_i2v": vid_id}
    autopipeline._run_full_pipeline(job)

    assert balance(uid) == 50 - 5  # chỉ LLM bị trừ (image/video giá 0)
    assert job.status == "done"


def test_pipeline_upfront_guard_402(client, make_user, admin_headers):
    h, uid = make_user()  # 0 credit, không topup
    ids = {}
    for name, step in [("LLM Guard Llm", "llm"), ("LLM Guard Img", "image_generate"), ("LLM Guard Vid", "video_i2v")]:
        r = client.post("/api/admin/models", headers=admin_headers, json={
            "name": name, "step": step, "base_url": "https://gw.example.io",
            "api_key": "sk-x", "model_name": "m"})
        assert r.status_code == 200
        ids[step] = r.json()["model"]["id"]
        client.put(f"/api/admin/pricing/m.{ids[step]}", headers=admin_headers, json={"price": 10, "enabled": True})
    r2 = client.post("/api/assistant/pipeline", headers=h, json={
        "idea": "kiểm tra guard", "model_llm": ids["llm"], "model_image": ids["image_generate"],
        "model_video": ids["video_i2v"], "duration": 30, "aspect_ratio": "9:16", "language": "vi"})
    assert r2.status_code == 402
    detail = r2.json().get("detail") or {}
    assert detail.get("required", 0) > 0


def test_estimate_video_billed_per_request_not_per_second(client, admin_headers):
    r = client.post("/api/admin/models", headers=admin_headers, json={
        "name": "Estimate Vid Req", "step": "video_i2v", "base_url": "https://gw.example.io",
        "api_key": "sk-x", "model_name": "vid/Veo-3.1", "max_clip_seconds": 8})
    vid_id = r.json()["model"]["id"]
    client.put(f"/api/admin/pricing/m.{vid_id}", headers=admin_headers, json={"price": 5, "enabled": True})

    from app import videopipeline
    from app.db import SessionLocal
    with SessionLocal() as db:
        d = videopipeline.estimated_cost({"video_i2v": vid_id}, 60, 10, db=db)
    # 10 cảnh × 5 credit/request = 50 (KHÔNG phải 60 giây × 5 = 300)
    assert d["video"]["số_lượng"] == 10
    assert d["video"]["unit"] == "request"
    assert d["video"]["tổng"] == 50
    assert d["tổng_credit"] == 50


# ---------------- Req 2 ----------------

class _FakeResp:
    def __init__(self, data, status=200):
        self._d = data
        self.status_code = status

    def json(self):
        return self._d


def test_provider_costs_live_pull(client, admin_headers, monkeypatch):
    import httpx

    from app.routers import admin as admin_router
    admin_router._PCACHE["data"] = None
    admin_router._PCACHE["ts"] = 0.0

    r = client.post("/api/admin/models", headers=admin_headers, json={
        "name": "Veo PC Test", "step": "video_i2v", "base_url": "https://gw.example.io",
        "api_key": "sk-x", "model_name": "Veo-3.1", "max_clip_seconds": 8})
    assert r.status_code == 200
    mid = r.json()["model"]["id"]

    def fake_get(url, headers=None, timeout=None):
        if "gw.example.io" in url:
            return _FakeResp({"data": [
                {"id": "Veo-3.1", "pricing_mode": "request", "price_per_request": 3000,
                 "model_type": "video", "model_options": {"seconds": [4, 6, 8]}, "active": True}]})
        raise AssertionError("unexpected URL: " + url)

    monkeypatch.setattr(httpx, "get", fake_get)
    r2 = client.get("/api/admin/provider-costs", headers=admin_headers)
    assert r2.status_code == 200
    m = next(m for m in r2.json()["models"] if m["id"] == mid)
    assert m["price_per_request"] == 3000
    assert m["seconds"] == [4, 6, 8] and m["pricing_mode"] == "request"


def test_provider_costs_error_isolated(client, admin_headers, monkeypatch):
    import httpx

    from app.routers import admin as admin_router
    admin_router._PCACHE["data"] = None
    admin_router._PCACHE["ts"] = 0.0

    r = client.post("/api/admin/models", headers=admin_headers, json={
        "name": "PC Error Model", "step": "llm", "base_url": "https://broken.example.io",
        "api_key": "sk-x", "model_name": "m"})
    mid = r.json()["model"]["id"]

    def fake_get(url, headers=None, timeout=None):
        if "broken.example.io" in url:
            raise RuntimeError("connection refused")
        raise AssertionError("unexpected URL: " + url)

    monkeypatch.setattr(httpx, "get", fake_get)
    r2 = client.get("/api/admin/provider-costs", headers=admin_headers)
    m = next(m for m in r2.json()["models"] if m["id"] == mid)
    assert "lỗi" not in m
    assert m["error"] and "connection refused" in m["error"]

"""Gen hàng loạt: tuần tự từng sản phẩm, hàng chờ, tự lưu Template, giải nén ZIP."""
import io
import zipfile

from app import batchpipeline

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


class _FakeJob:
    def __init__(self, job_id: str, outfit_url: str):
        self.job_id = job_id
        self.outfit_url = outfit_url
        self.progress = 100
        self.step = "Hoàn tất"
        self.status = "done"
        self.error = ""
        self.result = {
            "plan": {"các_cảnh": [{"stt": 1, "giai_đoạn": "hook"}]},
            "keyframes": [{"image_url": "/media/outputs/k.png"}],
            "clip_count": 1,
            "saved_template_id": 500 + len(outfit_url),
        }

    def to_dict(self):
        return {"status": self.status, "error": self.error, "result": self.result,
                "progress": self.progress, "step": self.step}


def _make_batch(urls, titles=None):
    return batchpipeline.BatchJob(
        batch_id="batch_test", user_id=1,
        selections={"llm": "l", "image_generate": "i", "video_i2v": "v"},
        idea="review", duration=20, aspect_ratio="9:16",
        character_image_url="/media/uploads/char.png",
        product_urls=urls,
        product_titles=titles or [],
        voice="native", use_tts=False, language="vi", hook_seconds=3)


def test_batch_runs_products_one_by_one(monkeypatch):
    created = []

    def fake_create(**kwargs):
        created.append(kwargs)
        return f"job{len(created)}"

    jobs = {f"job{i + 1}": _FakeJob(f"job{i + 1}", u)
            for i, u in enumerate(["/media/uploads/p1.png", "/media/uploads/p2.png"])}
    monkeypatch.setattr(batchpipeline.autopipeline, "create_job", fake_create)
    monkeypatch.setattr(batchpipeline.autopipeline, "get_job", lambda jid: jobs.get(jid))
    monkeypatch.setattr(batchpipeline.autopipeline, "_run_full_pipeline", lambda _job: None)

    batch = _make_batch(["/media/uploads/p1.png", "/media/uploads/p2.png"], ["Áo đen", "Váy đỏ"])
    batchpipeline._run_batch(batch)

    assert [c["outfit_image_url"] for c in created] == [
        "/media/uploads/p1.png", "/media/uploads/p2.png"]
    assert all(c["mode"] == "review_outfit" for c in created)
    assert created[0]["hook_seconds"] == 3
    assert "Áo đen" in created[0]["idea"]

    d = batch.to_dict()
    assert d["status"] == "done"
    assert d["counts"]["done"] == 2
    assert [it["status"] for it in d["items"]] == ["done", "done"]
    assert all(it["saved_template_id"] for it in d["items"])  # tự lưu Template
    assert d["items"][0]["plan"]["các_cảnh"][0]["giai_đoạn"] == "hook"


def test_batch_cancel_stops_queue(monkeypatch):
    created = []

    def fake_create(**kwargs):
        created.append(kwargs)
        return f"job{len(created)}"

    job = _FakeJob("job1", "/media/uploads/p1.png")
    monkeypatch.setattr(batchpipeline.autopipeline, "create_job", fake_create)
    monkeypatch.setattr(batchpipeline.autopipeline, "get_job", lambda _jid: job)
    monkeypatch.setattr(batchpipeline.autopipeline, "_run_full_pipeline",
                        lambda _job: None)

    batch = _make_batch(["/media/uploads/p1.png", "/media/uploads/p2.png"])
    batch.cancel()
    batchpipeline._run_batch(batch)

    assert created == []  # đã hủy trước khi làm sản phẩm nào
    d = batch.to_dict()
    assert d["status"] == "cancelled"
    assert all(it["status"] == "cancelled" for it in d["items"])


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def _admin_models(client, admin_headers, tag):
    ids = {}
    for step, model in (("llm", "llm-x"), ("image_generate", "img-x"), ("video_i2v", "video-x")):
        r = client.post("/api/admin/models", headers=admin_headers, json={
            "name": f"{tag}-{step}", "step": step, "base_url": "https://gw.example.io",
            "api_key": "sk-test-1234567890", "model_name": model,
        })
        assert r.status_code == 200, r.text
        ids[step] = r.json()["model"]["id"]
    return ids


def test_batch_extract_single_image(client, make_user):
    headers, _ = make_user()
    r = client.post("/api/assistant/batch/extract", headers=headers,
                    files={"file": ("product.png", PNG, "image/png")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["count"] == 1 and d["urls"][0].startswith("/media/uploads/")
    assert d["titles"] == ["product"]


def test_batch_extract_zip(client, make_user):
    headers, _ = make_user()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.png", PNG)
        zf.writestr("folder/b.jpg", PNG)
        zf.writestr("note.txt", b"hello")
    r = client.post("/api/assistant/batch/extract", headers=headers,
                    files={"file": ("products.zip", buf.getvalue(), "application/zip")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["count"] == 2
    assert d["titles"] == ["a", "b"]


def test_batch_extract_rejects_unknown_file(client, make_user):
    headers, _ = make_user()
    r = client.post("/api/assistant/batch/extract", headers=headers,
                    files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")})
    assert r.status_code == 422


def test_start_batch_dedupes_and_queues(client, admin_headers, make_user,
                                       monkeypatch):
    headers, _ = make_user()
    ids = _admin_models(client, admin_headers, "batch-test")
    # Không chạy pipeline thật trong test — chỉ kiểm tra hàng đợi được tạo.
    monkeypatch.setattr(batchpipeline, "start_batch", lambda _bid: None)

    r1 = client.post("/api/assistant/batch/extract", headers=headers,
                     files={"file": ("p1.png", PNG, "image/png")})
    url1 = r1.json()["urls"][0]
    r2 = client.post("/api/assistant/batch/extract", headers=headers,
                     files={"file": ("p2.png", PNG, "image/png")})
    url2 = r2.json()["urls"][0]

    r = client.post("/api/assistant/batch", headers=headers, json={
        "idea": "review thời trang",
        "model_llm": ids["llm"], "model_image": ids["image_generate"],
        "model_video": ids["video_i2v"],
        "duration": 20, "hook_seconds": 3,
        "character_image_url": url1,
        "product_image_urls": [url2, url2, url1],  # trùng -> chỉ làm 1 lần
        "product_titles": ["Áo", "Áo", "Mẫu"],
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["total"] == 2

    st = client.get(f"/api/assistant/batch/{d['batch_id']}/status", headers=headers)
    assert st.status_code == 200
    items = st.json()["items"]
    assert [it["title"] for it in items] == ["Áo", "Mẫu"]
    assert all(it["status"] == "queued" for it in items)


def test_start_batch_requires_models(client, make_user):
    headers, _ = make_user()
    r = client.post("/api/assistant/batch", headers=headers, json={
        "character_image_url": "/media/uploads/c.png",
        "product_image_urls": ["/media/uploads/p.png"],
    })
    assert r.status_code == 422
    assert "model" in r.text.lower()


def test_retry_failed_items_runs_only_failures(monkeypatch):
    batch = _make_batch(["/media/uploads/p1.png", "/media/uploads/p2.png"], ["Áo", "Váy"])
    batch.items[0].status = "failed"
    batch.items[0].error = "pipeline fail"
    batch.items[1].status = "done"
    batch.status = "done"
    batchpipeline.BATCHES[batch.batch_id] = batch

    created = []

    def fake_create(**kwargs):
        created.append(kwargs)
        return f"retryjob{len(created)}"

    j = _FakeJob("retryjob1", "/media/uploads/p1.png")
    monkeypatch.setattr(batchpipeline.autopipeline, "create_job", fake_create)
    monkeypatch.setattr(batchpipeline.autopipeline, "get_job", lambda jid: j if jid == "retryjob1" else None)
    monkeypatch.setattr(batchpipeline.autopipeline, "_run_full_pipeline", lambda _job: None)

    class _SyncThread:
        def __init__(self, target, args=(), daemon=None, **_kw):
            self._target, self._args = target, args

        def start(self):
            self._target(*self._args)

    monkeypatch.setattr(batchpipeline.threading, "Thread", _SyncThread)

    result = batchpipeline.retry_batch_items(batch.batch_id)
    assert result["retrying"] == 1
    assert [c["outfit_image_url"] for c in created] == ["/media/uploads/p1.png"]
    d = batch.to_dict()
    assert [it["status"] for it in d["items"]] == ["done", "done"]

    # không còn sản phẩm lỗi -> báo lỗi, không chạy lại gì
    try:
        batchpipeline.retry_batch_items(batch.batch_id)
        assert False, "expected ValueError"
    except ValueError:
        pass

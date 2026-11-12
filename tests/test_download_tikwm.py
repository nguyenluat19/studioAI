"""TiKWM fallback: TikTok/Douyin video không watermark + post ảnh (slides) — không gọi mạng thật."""
import httpx
import pytest

from app.config import settings
from app.routers import videotools


class FakeResp:
    def __init__(self, status_code=200, payload=None, content=b"", ctype="image/jpeg"):
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.headers = {"content-type": ctype}
        self.text = ""

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(f"HTTP {self.status_code}", request=None, response=None)


class FakeClient:
    TIKWM_DATA: dict = {}

    def __init__(self, *a, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, data=None, **kw):
        assert "tikwm.com" in url
        return FakeResp(200, {"code": 0, "msg": "success", "data": FakeClient.TIKWM_DATA})

    def get(self, url, **kw):
        payload = b"\xff\xd8\xff" + b"x" * 2048 if ("mp4" in url or "video" in url) else b"\xff\xd8\xff" + b"imgdata"
        return FakeResp(200, content=payload, ctype="video/mp4" if "mp4" in url else "image/jpeg")

    def stream(self, method, url, **kw):
        payload = b"\x00" * 2048
        resp = FakeResp(200, content=payload, ctype="video/mp4")
        resp.headers = {"content-type": "video/mp4", "content-length": str(len(payload))}

        class _StreamCM:
            def __enter__(self):
                return resp

            def __exit__(self, *a):
                return False

        resp.iter_bytes = lambda chunk_size=262144: [payload]
        return _StreamCM()


@pytest.fixture()
def tikwm(monkeypatch):
    FakeClient.TIKWM_DATA = {}
    monkeypatch.setattr(httpx, "Client", FakeClient)
    settings.outputs_dir.mkdir(parents=True, exist_ok=True)
    return FakeClient


def test_video_post_downloads_and_returns_video_kind(tikwm, tmp_path):
    tikwm.TIKWM_DATA = {"play": "https://tikwm.com/x/abc.mp4", "title": "Clip test",
                        "duration": 10, "cover": "https://tikwm.com/c.jpg"}
    dest = settings.outputs_dir / "test_video_dl.mp4"
    info = videotools._download_tiktok_tikwm("https://www.tiktok.com/@scout2015/video/6718335390845095173", dest)
    assert info and info["kind"] == "video"
    assert dest.exists() and dest.stat().st_size > 1000


def test_photo_post_downloads_all_images(tikwm):
    tikwm.TIKWM_DATA = {"title": "Bộ ảnh test", "cover": "https://tikwm.com/cover.jpg",
                        "images": ["https://tikwm.com/img1.jpg", "https://tikwm.com/img2.webp",
                                   "https://tikwm.com/img3.png"]}
    dest = settings.outputs_dir / "test_photo_dl.mp4"
    info = videotools._download_tiktok_tikwm("https://www.tiktok.com/@x/photo/123", dest)
    assert info and info["kind"] == "images"
    assert len(info["images"]) == 3
    assert all(u.startswith("/media/outputs/") for u in info["images"])
    from app.media import resolve
    for u in info["images"]:
        p = resolve(u)
        assert p is not None and p.exists()


def test_tikwm_failure_returns_none_so_yt_dlp_fallback_runs(tikwm):
    tikwm.TIKWM_DATA = {}   # code != 0 path via empty data won't happen; simulate exception
    import httpx as _hx

    class BrokenClient(FakeClient):
        def post(self, url, data=None, **kw):
            raise _hx.ConnectError("network down")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(_hx, "Client", BrokenClient)
    dest = settings.outputs_dir / "test_fail_dl.mp4"
    assert videotools._download_tiktok_tikwm("https://www.tiktok.com/@x/video/1", dest) is None
    monkeypatch.undo()

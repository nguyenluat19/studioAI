"""Voice upload/clone storage: upload -> /media/voices mount -> list -> delete.

Clone thật (engine TTS sinh giọng từ mẫu) chưa có — các endpoint này chỉ
lưu/quản lý mẫu giọng người dùng.
"""
import io


def _wav(n=2048):
    # minimal RIFF header + payload so size > 1000 bytes
    return io.BytesIO(b"RIFF" + (n).to_bytes(4, "little") + b"WAVEfmt " + b"\x00" * (n - 12))


def test_voice_upload_list_delete_roundtrip(client, make_user):
    h, _ = make_user()
    up = client.post("/api/assistant/voice-upload", headers=h,
                     files={"file": ("sample.wav", _wav(), "audio/wav")})
    assert up.status_code == 200, up.text
    d = up.json()
    assert d["url"].startswith("/media/voices/")
    assert d["voice_id"]

    # /media/voices phải được mount (trước đây 404)
    r = client.get(d["url"])
    assert r.status_code == 200

    lst = client.get("/api/assistant/voices-cloned", headers=h)
    assert lst.status_code == 200
    assert [v["id"] for v in lst.json()["voices"]] == [d["voice_id"]]

    # không lộ metadata (id, user_id) ra static
    assert client.get(f"/media/voices/{d['voice_id']}.json").status_code == 404

    # xoá bằng delete mới
    r = client.delete(f"/api/assistant/voices-cloned/{d['voice_id']}", headers=h)
    assert r.status_code == 200
    assert client.get("/api/assistant/voices-cloned", headers=h).json()["voices"] == []
    assert client.get(d["url"]).status_code == 404


def test_voice_upload_rejects_bad_extension(client, make_user):
    h, _ = make_user()
    up = client.post("/api/assistant/voice-upload", headers=h,
                     files={"file": ("evil.txt", io.BytesIO(b"x" * 2000), "text/plain")})
    assert up.status_code == 422


def test_voice_upload_rejects_tiny_file(client, make_user):
    h, _ = make_user()
    up = client.post("/api/assistant/voice-upload", headers=h,
                     files={"file": ("tiny.mp3", io.BytesIO(b"IM" * 100), "audio/mpeg")})
    assert up.status_code == 422


def test_voice_upload_saves_sample_without_elevenlabs(client, make_user):
    """Không có ELEVENLABS_API_KEY: upload chỉ lưu mẫu, không clone, response vẫn OK."""
    import app.tts as tts_mod
    assert tts_mod.elevenlabs_enabled() is False  # conftest không đặt key
    h, _ = make_user()
    up = client.post("/api/assistant/voice-upload", headers=h,
                     files={"file": ("sample.wav", _wav(), "audio/wav")})
    assert up.status_code == 200
    d = up.json()
    assert d["provider"] == "none"


def test_voice_upload_clones_with_elevenlabs_key(monkeypatch, client, make_user):
    """Có key + clone giả: meta lưu provider=elevenlabs, voice_value=el:<id>; xoá giọng xoá cả clone."""
    import app.tts as tts_mod
    monkeypatch.setattr(tts_mod.settings, "elevenlabs_api_key", "fake-key")
    calls = {}

    def fake_clone(name, samples):
        calls["clone"] = (name, [p.name for p in samples])
        return "el-clone-123"

    def fake_delete(voice_id):
        calls["delete_el"] = voice_id

    monkeypatch.setattr(tts_mod, "clone_voice", fake_clone)
    monkeypatch.setattr(tts_mod, "delete_elevenlabs_voice", fake_delete)

    h, _ = make_user()
    up = client.post("/api/assistant/voice-upload", headers=h,
                     files={"file": ("sample.wav", _wav(), "audio/wav")})
    assert up.status_code == 200
    d = up.json()
    assert d["provider"] == "elevenlabs"
    assert calls["clone"][0].startswith("Voice ")
    assert len(calls["clone"][1]) == 1

    lst = client.get("/api/assistant/voices-cloned", headers=h).json()["voices"]
    assert lst[0]["provider"] == "elevenlabs"
    assert lst[0]["provider_voice_id"] == "el-clone-123"
    assert lst[0]["voice_value"] == "el:el-clone-123"

    assert client.delete(f"/api/assistant/voices-cloned/{d['voice_id']}", headers=h).status_code == 200
    assert calls["delete_el"] == "el-clone-123"


def test_gen_tts_dispatches_elevenlabs_clone(monkeypatch, tmp_path):
    """gen_tts với voice 'el:<id>' phải đi vào gen_clone_tts (không gọi edge-tts)."""
    import app.tts as tts_mod
    dest = tmp_path / "out.mp3"

    def fake_clone(text, dest, *, voice_id, timeout=300):
        dest.write_bytes(b"ID3" + b"\x00" * 50)
        return dest

    monkeypatch.setattr(tts_mod, "gen_clone_tts", fake_clone)
    monkeypatch.setattr(tts_mod, "_synthesize", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not call edge-tts")))

    out = tts_mod.gen_tts("Xin chào.", dest, voice="el:el-clone-123")
    assert out == dest and dest.exists()


def test_delete_voice_requires_owner(client, make_user):
    h1, _ = make_user()
    h2, _ = make_user()
    up = client.post("/api/assistant/voice-upload", headers=h1,
                     files={"file": ("s.wav", _wav(), "audio/wav")})
    assert up.status_code == 200
    vid = up.json()["voice_id"]
    # user khác không xoá được
    assert client.delete(f"/api/assistant/voices-cloned/{vid}", headers=h2).status_code == 404
    # không xoá được id không tồn tại
    assert client.delete(f"/api/assistant/voices-cloned/deadbeef", headers=h1).status_code == 404
    assert client.delete(f"/api/assistant/voices-cloned/{vid}", headers=h1).status_code == 200

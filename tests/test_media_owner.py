

def test_resolve_rejects_traversal_and_supports_owner_scope(tmp_path, monkeypatch):
    from app import media
    from app.config import settings

    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    own = tmp_path / "uploads" / "u7" / "own.png"
    other = tmp_path / "uploads" / "u8" / "other.png"
    public_root = tmp_path / "outputs" / "shared.mp4"
    secret = tmp_path / "app.db"
    for p in (own, other, public_root, secret):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"data")

    assert media.resolve("/media/uploads/u7/own.png", 7) == own.resolve()
    assert media.resolve("/media/uploads/u8/other.png", 7) is None
    assert media.resolve("/media/outputs/shared.mp4", 7) is None
    assert media.resolve("/media/../app.db", 7) is None
    assert media.resolve("/media/uploads/u8/other.png") == other.resolve()

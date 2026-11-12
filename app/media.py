"""Safe mapping between public /media URLs and files under STORAGE_DIR."""
from pathlib import Path

from .config import settings


def voice_meta_dir() -> Path:
    """Voice sample metadata lives outside the public /media/voices mount."""
    d = settings.storage_dir / "voices_meta"
    d.mkdir(parents=True, exist_ok=True)
    return d


def user_dir(kind: str, user_id: int | str) -> Path:
    """Per-account folder under STORAGE_DIR (uploads/outputs/voices/...).

    Mỗi tài khoản có dữ liệu riêng ở `<kind>/u<id>/` — không trộn lẫn file giữa các user.
    URL tương ứng tự có dạng /media/<kind>/u<id>/<file>.
    """
    uid = str(int(user_id))
    d = settings.storage_dir / kind / f"u{uid}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def user_outputs_dir(user_id: int | str) -> Path:
    return user_dir("outputs", user_id)


def user_uploads_dir(user_id: int | str) -> Path:
    return user_dir("uploads", user_id)


def user_voices_dir(user_id: int | str) -> Path:
    return user_dir("voices", user_id)


def owner_dir_for_generation(gen_id: int) -> Path:
    """Outputs folder of the owner of a generation (for worker/render paths that only get gen_id)."""
    from .db import SessionLocal
    from .models import GenerationHistory
    try:
        with SessionLocal() as db:
            gen = db.get(GenerationHistory, gen_id)
            uid = gen.user_id if gen is not None else 0
    except Exception:
        uid = 0
    return user_dir("outputs", uid)


def url_for(path: Path) -> str:
    return "/media/" + path.resolve().relative_to(settings.storage_dir).as_posix()


def _under_any_root(path: Path, roots: tuple[Path, ...]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def resolve(url: str, user_id: int | None = None) -> Path | None:
    """Resolve a public media URL, optionally requiring ownership of user-scoped files."""
    if not url or not url.startswith("/media/"):
        return None
    p = (settings.storage_dir / url[len("/media/"):]).resolve()
    roots = (settings.uploads_dir.resolve(), settings.outputs_dir.resolve(), settings.voices_dir.resolve())
    if not _under_any_root(p, roots) or not p.is_file():
        return None
    if user_id is not None:
        if not _under_any_root(p, tuple((root / f"u{int(user_id)}").resolve() for root in roots)):
            return None
    return p

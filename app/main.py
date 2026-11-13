from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import SessionLocal, get_db
from .maintenance import Sweeper
from . import landing
from . import legal
from . import pricing
from .migrate import upgrade_db
from .models import SharedVideoLibrary, User
from .routers import admin, assistant, auth, billing, chat, generate, templates, videotools
from . import featurebilling as featurebilling_mod
from .security import hash_password

STATIC = Path(__file__).resolve().parent.parent / "static"


def check_production_settings() -> None:
    """In APP_ENV=production refuse to start with the built-in secret or no admin password."""
    if settings.app_env != "production":
        return
    problems = []
    if settings.secret_key in ("dev-secret-change-me", "change-me-to-a-long-random-string") or len(settings.secret_key) < 32:
        problems.append("SECRET_KEY must be a random string of at least 32 characters")
    if not settings.admin_password or settings.admin_password.startswith("change-me"):
        problems.append("ADMIN_PASSWORD must be set to a real password")
    if problems:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))


AI_TEMPLATES = [
    {"title": "Video AI từ mô tả (MiniMax-H3)", "category": "full",
     "schema": {"ai_video": True, "layers": []}},
    {"title": "Nhảy theo ảnh nhân vật (MiniMax-H3 + MimicMotion)", "category": "full",
     "schema": {"ai_video": True, "dance": True, "motion_transfer": True, "layers": []}},
]


def seed_ai_templates(db) -> None:
    """Built-in templates for the AI flows, published under the first admin. Idempotent."""
    admin = db.scalar(select(User).where(User.role == "admin").order_by(User.id))
    if not admin:
        return
    for t in AI_TEMPLATES:
        if not db.scalar(select(SharedVideoLibrary.id).where(SharedVideoLibrary.title == t["title"])):
            db.add(SharedVideoLibrary(title=t["title"], category=t["category"], template_schema=t["schema"],
                                      status="publish", creator_id=admin.id))
    db.commit()


def init() -> None:
    check_production_settings()
    for d in (settings.storage_dir, settings.uploads_dir, settings.outputs_dir):
        d.mkdir(parents=True, exist_ok=True)
    upgrade_db()
    with SessionLocal() as db:
        if settings.admin_password and not db.scalar(select(User).where(User.role == "admin")):
            db.add(User(username=settings.admin_username, email=settings.admin_email.lower(),
                        password_hash=hash_password(settings.admin_password), role="admin"))
            db.commit()
        pricing.seed(db)
        featurebilling_mod.seed(db)
        from . import adminmodels
        adminmodels.sync(db)
        featurebilling_mod.list_policies(db)   # load models admin đã thêm qua UI vào registry cache
        seed_ai_templates(db)
        from . import autopipeline
        autopipeline.recover_interrupted_jobs()   # job dở khi restart -> đánh failed để user thấy


@asynccontextmanager
async def lifespan(_: FastAPI):
    init()
    sweeper = Sweeper()
    sweeper.start()
    yield
    sweeper.stop()


# docs_url=None: /docs là trang TÀI LIỆU của sản phẩm (nay chuyển về /#docs);
# nếu để mặc định, FastAPI gắn Swagger UI vào /docs và người dùng thấy giao diện API.
app = FastAPI(title="Video Template SaaS", lifespan=lifespan, docs_url=None, redoc_url=None)
for r in (auth, templates, generate, billing, admin, assistant, videotools, chat):
    app.include_router(r.router)

# Mount only uploads/outputs/voices — never the storage root (it holds the SQLite DB).
for _d in (settings.uploads_dir, settings.outputs_dir, settings.voices_dir):
    _d.mkdir(parents=True, exist_ok=True)
    app.mount(f"/media/{_d.name}", StaticFiles(directory=_d), name=f"media-{_d.name}")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False, response_class=HTMLResponse)
def index(db: Session = Depends(get_db)):
    """Trang chủ công khai (landing + nav). Tool nằm ở /dashboard."""
    from . import support as support_mod
    return HTMLResponse(landing.render(support=support_mod.get_links(db)),
                        headers={"Cache-Control": "public, max-age=300"})


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    """Ứng dụng (SPA): đăng nhập + bảng điều khiển."""
    return FileResponse(STATIC / "index.html")


@app.get("/pricing", include_in_schema=False, response_class=HTMLResponse)
def pricing_page(db: Session = Depends(get_db)):
    """Bảng giá công khai — đọc đúng giá admin đặt trong tab Bảng giá."""
    from . import support as support_mod
    return HTMLResponse(landing.render_pricing(db, support=support_mod.get_links(db)),
                        headers={"Cache-Control": "public, max-age=300"})


@app.get("/docs", include_in_schema=False)
def docs_page():
    """Trang hub riêng đã loại bỏ (trùng với mục Tài liệu & chính sách ở trang chủ) → về /#docs."""
    return RedirectResponse("/#docs", status_code=301)


@app.get("/welcome", include_in_schema=False)
def welcome():
    """Cũ rồi → về trang chủ, mục Tài liệu & chính sách."""
    return RedirectResponse("/#docs", status_code=301)


def _legal_response(slug: str, db: Session):
    from . import support as support_mod
    html_text = legal.render(slug, support=support_mod.get_links(db))
    if html_text is None:
        raise HTTPException(404, "Trang không tồn tại")
    return HTMLResponse(html_text, headers={"Cache-Control": "public, max-age=300"})


def _make_legal_route(slug: str):
    def _route(db: Session = Depends(get_db)):
        return _legal_response(slug, db)
    return _route


for _slug in legal.all_routes():
    app.add_api_route(f"/{_slug}", _make_legal_route(_slug), methods=["GET"],
                      include_in_schema=False, response_class=HTMLResponse)


@app.get("/api/health")
def health():
    return {"ok": True}

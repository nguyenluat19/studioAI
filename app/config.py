"""Environment-driven settings (reads ./.env if present)."""
import os
import re
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    # utf-8 + errors="replace": file .env lỡ tay lưu ký tự lạ cũng không làm sập app khi khởi động.
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv(Path(__file__).resolve().parent.parent / ".env")

ENV_FILE = Path(os.environ.get("APP_ENV_FILE",
                               str(Path(__file__).resolve().parent.parent / ".env")))


def env_upsert(key: str, value: str) -> None:
    """Set KEY=value in the .env file (and the live environ); empty value removes the line."""
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    out, found = [], False
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and "=" in s and s.split("=", 1)[0].strip() == key:
            found = True
            if value:
                out.append(f"{key}={value}")
        else:
            out.append(line)
    if not found and value:
        out.append(f"{key}={value}")
    text = "\n".join(out).rstrip("\n") + "\n" if out else ""
    ENV_FILE.write_text(text, encoding="utf-8")
    if value:
        os.environ[key] = value
    else:
        os.environ.pop(key, None)


def model_key_env(model_id: str) -> str:
    """Env var name holding the API key of an admin-added model, e.g. MODEL_VEO_3_API_KEY."""
    slug = re.sub(r"[^A-Z0-9]+", "_", model_id.upper()).strip("_")
    return f"MODEL_{slug}_API_KEY"


def _f(name: str, default: str) -> str:
    return os.environ.get(name, default)


class Settings:
    def __init__(self) -> None:
        self.app_env = _f("APP_ENV", "dev")
        self.allow_private_model_urls = _f("ALLOW_PRIVATE_MODEL_URLS", "0") == "1"
        self.database_url = _f("DATABASE_URL", "sqlite:///./storage/app.db")
        self.secret_key = _f("SECRET_KEY", "dev-secret-change-me")
        self.storage_dir = Path(_f("STORAGE_DIR", "./storage")).resolve()
        self.admin_username = _f("ADMIN_USERNAME", "admin")
        self.admin_email = _f("ADMIN_EMAIL", "admin@example.com")
        self.admin_password = _f("ADMIN_PASSWORD", "")

        self.fast_cost = float(_f("FAST_RENDER_COST", "1"))
        self.heavy_cost = float(_f("HEAVY_RENDER_COST", "10"))

        self.vilao_base_url = _f("VILAO_BASE_URL", "https://api.vilao.ai/v1").rstrip("/")
        self.vilao_api_key = _f("VILAO_API_KEY", "")
        self.vilao_image_size = _f("VILAO_IMAGE_SIZE", "1024x1024")

        self.bank_bin = _f("BANK_BIN", "vcb")
        self.bank_account_no = _f("BANK_ACCOUNT_NO", "0000000000")
        self.bank_account_name = _f("BANK_ACCOUNT_NAME", "")
        self.sepay_api_key = _f("SEPAY_API_KEY", "")
        self.casso_secure_token = _f("CASSO_SECURE_TOKEN", "")

        # QR / top-up lifetime. A pending transaction older than this becomes `failed`.
        self.tx_ttl_seconds = int(_f("TX_TTL_SECONDS", "300"))
        # Money that arrives after expiry: 0 = log it for admin review, 1 = credit it anyway.
        self.late_payment_autocredit = _f("LATE_PAYMENT_AUTOCREDIT", "0") == "1"

        # Stuck-job reaper (seconds). Jobs older than this are failed and refunded.
        self.fast_timeout = int(_f("FAST_TIMEOUT_SECONDS", "600"))
        self.heavy_timeout = int(_f("HEAVY_TIMEOUT_SECONDS", "5400"))        # while processing
        self.heavy_queue_timeout = int(_f("HEAVY_QUEUE_TIMEOUT_SECONDS", "21600"))  # while waiting in queue
        self.sweep_interval = int(_f("SWEEP_INTERVAL_SECONDS", "30"))

        # Abuse limits
        self.login_max_failures = int(_f("LOGIN_MAX_FAILURES", "8"))          # per ip+username / 10 min
        self.register_per_hour = int(_f("REGISTER_PER_HOUR", "20"))           # per ip
        # --- SMS xác minh số điện thoại khi đăng ký (ESMS.vn) ---
        # REQUIRE_PHONE_VERIFICATION=1 -> bắt buộc SĐT + OTP. Hiện đang TẮT (tạm thời ẩn
        # tính năng xác minh SĐT khỏi cả dự án) nên đăng ký không cần số điện thoại.
        self.require_phone_verification = _f("REQUIRE_PHONE_VERIFICATION", "0") == "1"
        self.esms_api_key = _f("ESMS_API_KEY", "").strip()
        self.esms_api_secret = _f("ESMS_API_SECRET", "").strip()
        self.esms_brandname = _f("ESMS_BRANDNAME", "STUDIOAI").strip()
        self.esms_content = _f("ESMS_CONTENT", "Ma xac minh dang ky StudioAI la {code}").strip()

        # --- Hugging Face API (Whisper & Translation) ---
        self.huggingface_api_key = _f("HUGGINGFACE_API_KEY", "")

        # --- ElevenLabs (voice clone THẬT — upload mẫu -> voice_id -> TTS qua el:<voice_id>) ---
        self.elevenlabs_api_key = _f("ELEVENLABS_API_KEY", "")

        # --- MiniMax-H3 video generation (separate from the Inkstone key) ---
        self.minimax_api_key = _f("MINIMAX_API_KEY", "")
        self.minimax_base_url = _f("MINIMAX_BASE_URL", "https://api.xah.io").rstrip("/")
        self.minimax_model = _f("MINIMAX_MODEL", "MiniMax-H3")
        self.minimax_create_path = _f("MINIMAX_CREATE_PATH", "/v2/video_generation")
        # {task_id} is substituted; if this path 404s the client also tries the alternatives in minimax.py
        self.minimax_query_path = _f("MINIMAX_QUERY_PATH", "/v2/query/video_generation/{task_id}")
        self.minimax_poll = float(_f("MINIMAX_POLL_SECONDS", "3"))
        self.minimax_max_wait = float(_f("MINIMAX_MAX_WAIT_SECONDS", "1200"))
        self.minimax_extra = _f("MINIMAX_EXTRA_PARAMS", "")        # JSON merged into the create request
        self.ai_timeout = int(_f("AI_TIMEOUT_SECONDS", "1800"))              # processing
        self.ai_queue_timeout = int(_f("AI_QUEUE_TIMEOUT_SECONDS", "3600"))  # waiting in queue

        # --- Giới hạn dung lượng tải MXH (MB) — vượt thì báo "Không hỗ trợ" trước khi tải ---
        self.download_max_mb = int(_f("DOWNLOAD_MAX_MB", "200"))

        # --- Dịch & Phụ đề: model Whisper. Rỗng = tự chọn theo quality trong request
        #     (accurate=medium). Đặt WHISPER_MODEL để ép một model cụ thể. ---
        self.whisper_model = _f("WHISPER_MODEL", "").strip()
        self.whisper_vad = _f("WHISPER_VAD", "1") == "1"

        # --- Hỗ trợ người dùng: liên kết Zalo/Facebook/Telegram, email; chat AI ---
        self.site_name = _f("SITE_NAME", "StudioAI")
        self.support_zalo_url = _f("SUPPORT_ZALO_URL", "").strip()
        self.support_facebook_url = _f("SUPPORT_FACEBOOK_URL", "").strip()
        self.support_telegram_url = _f("SUPPORT_TELEGRAM_URL", "").strip()
        self.support_email = _f("SUPPORT_EMAIL", "support@studioai.id.vn").strip()
        self.chat_credit_cost = float(_f("CHAT_CREDIT_COST", "0"))  # 0 = chat hỗ trợ miễn phí

        self.redis_url = _f("REDIS_URL", "redis://localhost:6379/0")
        self.celery_eager = _f("CELERY_ALWAYS_EAGER", "0") == "1"
        self.mimicmotion_dir = Path(_f("MIMICMOTION_DIR", "./vendor/MimicMotion")).resolve()
        self.mimicmotion_python = _f("MIMICMOTION_PYTHON", "python3")
        # Defaults mirror MimicMotion's configs/test.yaml (HF id is auto-downloaded on first run).
        self.mimicmotion_base_model = _f("MIMICMOTION_BASE_MODEL",
                                         "stabilityai/stable-video-diffusion-img2vid-xt-1-1")
        self.mimicmotion_ckpt = _f("MIMICMOTION_CKPT", "models/MimicMotion_1-1.pth")
        self.mimicmotion_num_frames = int(_f("MIMICMOTION_NUM_FRAMES", "72"))

    @property
    def uploads_dir(self) -> Path:
        return self.storage_dir / "uploads"

    @property
    def outputs_dir(self) -> Path:
        return self.storage_dir / "outputs"

    @property
    def voices_dir(self) -> Path:
        return self.storage_dir / "voices"


settings = Settings()

# Top-up: the user types any amount >= the admin-set minimum (default 20.000đ); these are only shortcut buttons.
QUICK_TOPUP_AMOUNTS = [20_000, 50_000, 100_000, 200_000, 500_000]
DEFAULT_MIN_TOPUP_VND = 20_000
MAX_TOPUP_VND = 50_000_000   # sanity cap against typos (one extra zero)


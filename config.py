"""
Centralised runtime configuration.

Every knob the application needs is read from the environment (or `.env`) exactly once
here, validated, and exposed as attributes on `Config`.  Nothing else in the codebase
should call `os.getenv` for application settings.
"""
import os
import secrets
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_list(name: str, default: str = "") -> list:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _read_git_version(base) -> str:
    """Short commit of the checked-out code + its date, read straight from .git (works on the VPS
    without shelling out). Falls back to 'unknown'. Shown in /api/health and the admin header so a
    stale deploy is obvious at a glance."""
    try:
        import datetime as _dt
        git = base / ".git"
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref = head.split(" ", 1)[1].strip()
            ref_file = git / ref
            if ref_file.exists():
                sha = ref_file.read_text(encoding="utf-8").strip()
            else:
                sha = ""
                packed = git / "packed-refs"
                if packed.exists():
                    for line in packed.read_text(encoding="utf-8").splitlines():
                        if line.strip().endswith(ref):
                            sha = line.split()[0]
                            break
        else:
            sha = head
        when = ""
        log = git / "logs" / "HEAD"
        if log.exists():
            last = log.read_text(encoding="utf-8", errors="ignore").strip().splitlines()[-1]
            parts = last.split("\t")[0].split()
            for i, tok in enumerate(parts):
                if tok.isdigit() and len(tok) == 10 and i + 1 < len(parts):
                    when = _dt.datetime.utcfromtimestamp(int(tok)).strftime("%Y-%m-%d %H:%M UTC")
                    break
        return (sha[:7] if sha else "unknown") + (f" ({when})" if when else "")
    except Exception:  # noqa: BLE001
        return "unknown"


class Config:
    APP_VERSION: str = _read_git_version(BASE_DIR)

    # --- Runtime mode -------------------------------------------------------
    APP_ENV: str = os.getenv("APP_ENV", "development").strip().lower()
    IS_PROD: bool = APP_ENV == "production"
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = _env_int("PORT", 5000)
    SECRET_KEY: str = os.getenv("SECRET_KEY") or secrets.token_hex(32)

    # --- Persistence --------------------------------------------------------
    # Default: local SQLite file. Set DATABASE_URL=postgresql+psycopg://... for Postgres.
    DATABASE_URL: str = os.getenv("DATABASE_URL") or f"sqlite:///{BASE_DIR / 'vending_bot.db'}"

    # --- Security -----------------------------------------------------------
    # OPTIONAL. If set, every /api/admin/* request must send it as
    # `X-Admin-Token: <key>` (or `Authorization: Bearer <key>`).
    # If left empty (the default), the admin dashboard is open - no key needed.
    ADMIN_API_KEY: str = os.getenv("ADMIN_API_KEY", "").strip()
    # Optional shared secret for the Evolution webhook (`?token=` query or `apikey` header).
    EVOLUTION_WEBHOOK_SECRET: str = os.getenv("EVOLUTION_WEBHOOK_SECRET", "").strip()
    CORS_ORIGINS: list = _env_list("CORS_ORIGINS", "*")
    MAX_CONTENT_LENGTH: int = _env_int("MAX_CONTENT_LENGTH", 1 * 1024 * 1024)  # 1 MB
    TRUST_PROXY: bool = _env_bool("TRUST_PROXY", False)

    # --- Rate limiting (in-process sliding window) --------------------------
    RATE_LIMIT_CHAT_PER_MIN: int = _env_int("RATE_LIMIT_CHAT_PER_MIN", 30)
    RATE_LIMIT_ADMIN_LOGIN_PER_MIN: int = _env_int("RATE_LIMIT_ADMIN_LOGIN_PER_MIN", 10)
    RATE_LIMIT_WEBHOOK_PER_MIN: int = _env_int("RATE_LIMIT_WEBHOOK_PER_MIN", 120)

    # --- Business rules -----------------------------------------------------
    MAX_CLAIM_QUANTITY: int = _env_int("MAX_CLAIM_QUANTITY", 10)
    # Used-link protection: Google can't be asked whether a Gemini link is consumed (login wall),
    # so when a buyer reports "link used" we flag it and hand out a replacement for free.
    # Logged-in headless-browser checker for Google One / Gemini links (see google_checker.py).
    GOOGLE_CHECKER_DIR: Path = Path(os.getenv("GOOGLE_CHECKER_DIR") or (Path(os.getenv("AGENT_WORKSPACE_DIR") or (BASE_DIR / "agent_workspace")) / "google_checker"))
    GOOGLE_CHECKER_MAX_PER_HOUR: int = _env_int("GOOGLE_CHECKER_MAX_PER_HOUR", 40)
    GOOGLE_CHECKER_TIMEOUT_SECONDS: int = _env_int("GOOGLE_CHECKER_TIMEOUT_SECONDS", 20)
    GOOGLE_CHECKER_CACHE_SECONDS: int = _env_int("GOOGLE_CHECKER_CACHE_SECONDS", 600)
    GOOGLE_CHECKER_DOWN_COOLDOWN_SECONDS: int = _env_int("GOOGLE_CHECKER_DOWN_COOLDOWN_SECONDS", 600)
    # Admin Test/Verify use their own hourly budget so they can never starve live sales of checks.
    GOOGLE_CHECKER_PROBE_MAX_PER_HOUR: int = _env_int("GOOGLE_CHECKER_PROBE_MAX_PER_HOUR", 15)
    # A sale waits at most this long for a busy browser, then hands the link out unverified.
    GOOGLE_CHECKER_LOCK_WAIT_SECONDS: int = _env_int("GOOGLE_CHECKER_LOCK_WAIT_SECONDS", 8)
    # Total wall-clock a single claim may spend verifying links (several used links in a row).
    GOOGLE_CHECKER_CLAIM_BUDGET_SECONDS: int = _env_int("GOOGLE_CHECKER_CLAIM_BUDGET_SECONDS", 45)
    AUTO_REPLACE_USED_LINKS: bool = _env_bool("AUTO_REPLACE_USED_LINKS", True)
    REPLACEMENT_WINDOW_HOURS: int = _env_int("REPLACEMENT_WINDOW_HOURS", 72)   # after delivery
    MAX_REPLACEMENTS_PER_LINK: int = _env_int("MAX_REPLACEMENTS_PER_LINK", 1)
    MAX_MESSAGE_LENGTH: int = _env_int("MAX_MESSAGE_LENGTH", 2000)
    RESELLER_MAX_FAILED_ATTEMPTS: int = _env_int("RESELLER_MAX_FAILED_ATTEMPTS", 5)
    RESELLER_LOCKOUT_MINUTES: int = _env_int("RESELLER_LOCKOUT_MINUTES", 15)
    PENDING_ORDER_TTL_HOURS: int = _env_int("PENDING_ORDER_TTL_HOURS", 24)

    # --- Deep Agent / LLM ---------------------------------------------------
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "").strip()
    OPENAI_MODEL_NAME: str = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini").strip()
    LLM_TIMEOUT_SECONDS: int = _env_int("LLM_TIMEOUT_SECONDS", 60)
    LLM_MAX_RETRIES: int = _env_int("LLM_MAX_RETRIES", 2)
    AGENT_RECURSION_LIMIT: int = _env_int("AGENT_RECURSION_LIMIT", 30)
    CHAT_HISTORY_WINDOW: int = _env_int("CHAT_HISTORY_WINDOW", 20)
    AGENT_WORKSPACE_DIR: Path = Path(os.getenv("AGENT_WORKSPACE_DIR") or (BASE_DIR / "agent_workspace"))

    # --- Supplier: m00nshots instant store (auto-buy digital products) ------
    # The bot buys a product from this supplier on demand and delivers the returned credentials.
    MOONSHOTS_API_URL: str = os.getenv("MOONSHOTS_API_URL", "https://instant.m00nshots.store/api/v1").strip()
    MOONSHOTS_API_KEY: str = os.getenv("MOONSHOTS_API_KEY", "").strip()   # UI key overrides this
    MOONSHOTS_TIMEOUT_SECONDS: int = _env_int("MOONSHOTS_TIMEOUT_SECONDS", 30)
    MOONSHOTS_MAX_AUTOBUY_QTY: int = _env_int("MOONSHOTS_MAX_AUTOBUY_QTY", 10)   # applies to every supplier
    # Supplier #2: Loot Paglu (INR prices, X-API-Key header). UI key overrides env.
    LOOTPAGLU_API_URL: str = os.getenv("LOOTPAGLU_API_URL", "https://lootpaglu.in").strip()
    LOOTPAGLU_API_KEY: str = os.getenv("LOOTPAGLU_API_KEY", "").strip()
    LOOTPAGLU_TIMEOUT_SECONDS: int = _env_int("LOOTPAGLU_TIMEOUT_SECONDS", 30)

    # --- WhatsApp / Evolution -----------------------------------------------
    EVOLUTION_API_URL: str = os.getenv("EVOLUTION_API_URL", "http://localhost:8080").strip()
    EVOLUTION_API_KEY: str = os.getenv("EVOLUTION_API_KEY", "").strip()
    EVOLUTION_INSTANCE_NAME: str = os.getenv("EVOLUTION_INSTANCE_NAME", "VendingBot").strip()
    WEBHOOK_WORKERS: int = _env_int("WEBHOOK_WORKERS", 4)

    # --- Payments -----------------------------------------------------------
    ADMIN_UPI_ID: str = os.getenv("ADMIN_UPI_ID", "resellerpay@upi").strip()
    ADMIN_UPI_NAME: str = os.getenv("ADMIN_UPI_NAME", "Digital Vending Admin").strip()
    RESELLER_CREDIT_RATE_INR: float = float(os.getenv("RESELLER_CREDIT_RATE_INR", "150") or 150)

    # --- Logging ------------------------------------------------------------
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_FILE: str = os.getenv("LOG_FILE", "").strip()  # empty = stdout only


def validate_config() -> None:
    """
    Fail fast on unsafe production settings; be forgiving in development.
    Called once at application start-up.
    """
    problems = []

    # The admin dashboard is open by default (no key). Setting ADMIN_API_KEY is optional;
    # if set, it is enforced. We only warn - never block - when it is empty.
    if not Config.ADMIN_API_KEY:
        logger.warning("ADMIN_API_KEY not set - the admin dashboard is OPEN (no login required).")

    if Config.IS_PROD:
        if Config.CORS_ORIGINS == ["*"]:
            problems.append("CORS_ORIGINS must list explicit origins in production (not '*').")
        if not os.getenv("SECRET_KEY"):
            problems.append("SECRET_KEY must be set in production.")

    if Config.MAX_CLAIM_QUANTITY < 1:
        problems.append("MAX_CLAIM_QUANTITY must be >= 1.")

    if problems:
        message = "Invalid configuration:\n  - " + "\n  - ".join(problems)
        if Config.IS_PROD:
            raise RuntimeError(message)
        logger.warning(message)


def configure_logging() -> None:
    """Console (+ optional rotating file) logging with a consistent format."""
    from logging.handlers import RotatingFileHandler

    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers = [logging.StreamHandler()]
    if Config.LOG_FILE:
        Path(Config.LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(Config.LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"))
    logging.basicConfig(level=getattr(logging, Config.LOG_LEVEL, logging.INFO), format=fmt, handlers=handlers, force=True)
    # Quieten noisy libraries
    for noisy in ("httpx", "httpcore", "openai", "urllib3", "werkzeug"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

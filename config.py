"""Central configuration. Values come from environment variables (.env file locally)."""
import os
import secrets
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Everything that must survive restarts (database + uploads) lives under DATA_DIR.
DATA_DIR = Path(os.environ.get("DATA_DIR") or (BASE_DIR / "data")).resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_SUBDIRS = ("profile", "projects", "certificates", "resumes")
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _secret_key():
    """Use SECRET_KEY from the environment, otherwise generate one once and keep it on disk."""
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    key_file = DATA_DIR / "secret_key.txt"
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32))
    return key_file.read_text().strip()


class Config:
    SECRET_KEY = _secret_key()
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or f"sqlite:///{(DATA_DIR / 'portfolio.db').as_posix()}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Sessions / cookies
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("COOKIE_SECURE", False)  # set true when served over HTTPS
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.environ.get("SESSION_HOURS", "8")))
    REMEMBER_COOKIE_DURATION = timedelta(hours=8)

    # Uploads (per-file limits are enforced in utils.py)
    MAX_CONTENT_LENGTH = 30 * 1024 * 1024
    MAX_IMAGE_BYTES = 5 * 1024 * 1024
    MAX_PDF_BYTES = 10 * 1024 * 1024

    # CSRF / rate limiting
    WTF_CSRF_TIME_LIMIT = None
    RATELIMIT_STORAGE_URI = "memory://"
    RATELIMIT_ENABLED = _bool("RATELIMIT_ENABLED", True)
    RATELIMIT_HEADERS_ENABLED = False

    # Admin setup
    ADMIN_SETUP_KEY = os.environ.get("ADMIN_SETUP_KEY", "")

    # Email (Resend)
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
    RESEND_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "Portfolio <onboarding@resend.dev>")
    CONTACT_TO_EMAIL = os.environ.get("CONTACT_TO_EMAIL", "rubansamuel2007@gmail.com")

    # GitHub
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
    GITHUB_CACHE_SECONDS = int(os.environ.get("GITHUB_CACHE_SECONDS", "600"))

    # Display timezone for admin timestamps (minutes from UTC; India = 330)
    TIMEZONE_OFFSET_MIN = int(os.environ.get("TIMEZONE_OFFSET_MIN", "330"))

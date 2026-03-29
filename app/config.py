"""Samba Fête — Configuration classes."""
import os
import secrets


class Config:
    """Base configuration."""

    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    FLASK_ENV = os.environ.get("FLASK_ENV", "development")
    FLASK_DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"
    PORT = int(os.environ.get("PORT", 5000))

    # Session
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = FLASK_ENV == "production"

    # Database — SQLAlchemy
    DATABASE_URL = os.environ.get("DATABASE_URL", "")
    SQLITE_DB_PATH = os.environ.get("SQLITE_DB_PATH", "")

    # SQLAlchemy connection
    # Render provides postgres:// but SQLAlchemy 2.x needs postgresql://
    _db_url = DATABASE_URL.replace("postgres://", "postgresql://", 1) if DATABASE_URL else ""
    if _db_url.startswith("postgresql://"):
        SQLALCHEMY_DATABASE_URI = _db_url
    else:
        _db_path = SQLITE_DB_PATH or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "samba_fete.db"
        )
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{_db_path}"

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


class TestingConfig(Config):
    TESTING = True
    DEBUG = False
    WTF_CSRF_ENABLED = False


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}

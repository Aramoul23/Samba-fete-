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

    # Database
    DATABASE_URL = os.environ.get("DATABASE_URL", "")
    SQLITE_DB_PATH = os.environ.get("SQLITE_DB_PATH", "")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}

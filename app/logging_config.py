"""Samba Fête — Structured logging configuration.

JSON-formatted logs for production, human-readable for dev.
"""
import logging
import json
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Structured JSON log output for production."""

    def format(self, record):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        # Add extra fields
        for key in ("user_id", "endpoint", "method", "ip", "event_id"):
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)
        return json.dumps(log_entry, ensure_ascii=False)


class PlainFormatter(logging.Formatter):
    """Human-readable logs for development."""

    FORMAT = "%(asctime)s %(levelname)-8s %(name)s:%(funcName)s:%(lineno)d — %(message)s"

    def __init__(self):
        super().__init__(fmt=self.FORMAT, datefmt="%Y-%m-%d %H:%M:%S")


def setup_logging(app):
    """Configure logging based on environment."""
    log_level = getattr(logging, app.config.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
    is_production = app.config.get("FLASK_ENV") == "production"

    # Root logger
    root = logging.getLogger()
    root.setLevel(log_level)

    # Remove default handlers
    root.handlers.clear()

    # Console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter() if is_production else PlainFormatter())
    root.addHandler(handler)

    # File handler (rotating)
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        "app.log", maxBytes=10 * 1024 * 1024, backupCount=5
    )
    file_handler.setFormatter(JSONFormatter() if is_production else PlainFormatter())
    root.addHandler(file_handler)

    # Quiet noisy loggers
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    app.logger.info("Logging initialized (level=%s, production=%s)", log_level, is_production)

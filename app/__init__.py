"""Samba Fête — Application factory.

Creates and configures the Flask app using the factory pattern.
Blueprint registration happens here.
"""
import logging
import os
import secrets
from datetime import datetime

from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager

from app.config import config_by_name
from app.db import close_db_connection
from models import get_user_by_id, init_db

logger = logging.getLogger(__name__)

# ── Extensions (initialized here, bound to app in create_app) ────────
limiter = Limiter(key_func=get_remote_address, default_limits=[], storage_uri="memory://")
login_manager = LoginManager()


def create_app(config_name=None):
    """Application factory.

    Args:
        config_name: 'development' | 'production' | None (auto-detect from FLASK_ENV)

    Returns:
        Configured Flask application.
    """
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    config_class = config_by_name.get(config_name, config_by_name["default"])

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="../static",
    )
    app.config.from_object(config_class)

    # ── Secret key fallback ──────────────────────────────────────────
    if not os.environ.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = secrets.token_hex(32)
        logger.warning(
            "SECRET_KEY not set — using random key (sessions will not persist across restarts)"
        )

    # ── Extensions ───────────────────────────────────────────────────
    limiter.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Veuillez vous connecter pour accéder à cette page."
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id):
        return get_user_by_id(user_id)

    # ── Database teardown ────────────────────────────────────────────
    app.teardown_appcontext(close_db_connection)

    # ── Jinja filters ────────────────────────────────────────────────
    from utils import format_da

    def date_only(value):
        if value is None:
            return "N/A"
        if isinstance(value, str):
            return value[:10]
        try:
            return value.strftime("%Y-%m-%d")
        except (AttributeError, TypeError):
            return str(value)[:10]

    def datetime_display(value):
        if value is None:
            return "N/A"
        if isinstance(value, str):
            return value[:16].replace(" ", " à ")
        try:
            return value.strftime("%Y-%m-%d à %H:%M")
        except (AttributeError, TypeError):
            return str(value)[:16]

    app.jinja_env.filters["format_da"] = format_da
    app.jinja_env.filters["date_only"] = date_only
    app.jinja_env.filters["datetime_display"] = datetime_display

    @app.context_processor
    def inject_year():
        return {"current_year": datetime.now().year}

    # ── CSRF Protection ──────────────────────────────────────────────
    from flask import flash, redirect, request as req, session

    def generate_csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(32)
        return session["csrf_token"]

    @app.context_processor
    def inject_csrf_token():
        return {"csrf_token": generate_csrf_token}

    @app.before_request
    def csrf_protect():
        if req.method == "POST":
            if req.endpoint and req.endpoint.startswith("auth."):
                return  # auth routes handle their own CSRF
            token = req.form.get("csrf_token") or req.headers.get("X-CSRF-Token")
            session_token = session.get("csrf_token")
            if not token or not session_token or token != session_token:
                logger.warning(
                    "CSRF token mismatch from %s on %s", req.remote_addr, req.endpoint
                )
                flash("Session expirée ou invalide. Veuillez réessayer.", "danger")
                return redirect(req.url)

    # ── Blueprints ───────────────────────────────────────────────────
    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp)

    from app.bookings import bp as bookings_bp
    app.register_blueprint(bookings_bp)

    from app.finance import bp as finance_bp
    app.register_blueprint(finance_bp)

    from app.clients import bp as clients_bp
    app.register_blueprint(clients_bp)

    from app.settings import bp as settings_bp
    app.register_blueprint(settings_bp)

    # ── Error handlers ───────────────────────────────────────────────
    @app.errorhandler(429)
    def rate_limit_exceeded(e):
        from flask import flash, render_template as rt
        flash("Trop de tentatives. Veuillez patienter une minute.", "danger")
        return rt("login.html"), 429

    @app.errorhandler(500)
    def internal_error(e):
        import traceback
        error_trace = traceback.format_exc()
        logger.error("500 Error: %s\n%s", str(e), error_trace)
        return (
            f'<html><body style="font-family:monospace;padding:40px;background:#1a1a2e;color:#eee">'
            f'<h1 style="color:#e74c3c">500 Error</h1>'
            f'<pre style="background:#16213e;padding:20px;border-radius:8px;overflow-x:auto">'
            f'{error_trace}</pre></body></html>',
            500,
        )

    # ── Database init ────────────────────────────────────────────────
    init_db()
    _ensure_default_data()

    return app


def _ensure_default_data():
    """Seed default venues and settings if missing."""
    from models import get_db, get_setting, set_setting

    logger.info("Initializing default data...")
    db = get_db()

    DEFAULT_VENUES = [
        {"name": "Grande Salle", "capacity_men": 200, "capacity_women": 200},
        {"name": "Salle VIP", "capacity_men": 80, "capacity_women": 80},
        {"name": "Salle de Conférence", "capacity_men": 50, "capacity_women": 50},
    ]

    try:
        venue_count = db.execute("SELECT COUNT(*) as c FROM venues").fetchone()["c"]
        if venue_count == 0:
            for v in DEFAULT_VENUES:
                db.execute(
                    "INSERT INTO venues (name, capacity_men, capacity_women, is_active) VALUES (?, ?, ?, 1)",
                    (v["name"], v["capacity_men"], v["capacity_women"]),
                )
            db.commit()

        settings = db.execute(
            "SELECT key FROM settings WHERE key IN ('hall_name', 'currency', 'deposit_min')"
        ).fetchall()
        existing_keys = {s["key"] for s in settings}

        if "hall_name" not in existing_keys:
            set_setting("hall_name", "Samba Fête")
        if "currency" not in existing_keys:
            set_setting("currency", "DA")
        if "deposit_min" not in existing_keys:
            set_setting("deposit_min", "20000")

        logger.info("Default data check complete.")
    finally:
        db.close()

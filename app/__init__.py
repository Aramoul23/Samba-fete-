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
from flask_migrate import Migrate

from app.config import config_by_name
from app.db import close_db_connection

logger = logging.getLogger(__name__)

# ── Extensions (initialized here, bound to app in create_app) ────────
from app.models import db as sqlalchemy_db

limiter = Limiter(key_func=get_remote_address, default_limits=[], storage_uri="memory://")
login_manager = LoginManager()
migrate = Migrate()


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
    sqlalchemy_db.init_app(app)
    migrate.init_app(app, sqlalchemy_db)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Veuillez vous connecter pour accéder à cette page."
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return db.session.get(User, int(user_id))

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
        return rt("auth/login.html"), 429

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
    with app.app_context():
        from app.models import User, Venue, Setting
        sqlalchemy_db.create_all()
        _seed_default_data_sqlalchemy()

    return app


def _seed_default_data_sqlalchemy():
    """Seed default venues and settings using SQLAlchemy."""
    from app.models import User, Venue, Setting, db

    # Default venues
    if Venue.query.count() == 0:
        for name, cap_m, cap_w in [
            ("Grande Salle", 200, 200),
            ("Salle VIP", 80, 80),
            ("Salle de Conférence", 50, 50),
        ]:
            db.session.add(Venue(name=name, capacity_men=cap_m, capacity_women=cap_w))
        db.session.commit()

    # Default settings
    for key, default in [("hall_name", "Samba Fête"), ("currency", "DA"), ("deposit_min", "20000")]:
        if not Setting.query.get(key):
            db.session.add(Setting(key=key, value=default))
    db.session.commit()

    # Default admin user
    if User.query.count() == 0:
        admin_pw = os.environ.get("ADMIN_PASSWORD", "Ramsys2020$")
        admin = User(username="admin", role="admin")
        admin.set_password(admin_pw)
        db.session.add(admin)
        db.session.commit()
        logger.warning(
            "Default admin user created (password: %s) — change it or set ADMIN_PASSWORD",
            admin_pw,
        )

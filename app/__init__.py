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
from flask_wtf.csrf import CSRFProtect

from app.config import config_by_name
from app.db import close_db_connection
from app.logging_config import setup_logging
from app.middleware import register_error_handlers, register_health_check

logger = logging.getLogger(__name__)

# ── Extensions (initialized here, bound to app in create_app) ────────
from app.models import db as sqlalchemy_db

limiter = Limiter(key_func=get_remote_address, default_limits=[], storage_uri="memory://")
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()


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

    # ── Secret key validation ────────────────────────────────────────
    _secret = os.environ.get("SECRET_KEY")
    if not _secret:
        if app.config.get("FLASK_ENV") == "production":
            raise RuntimeError(
                "FATAL: SECRET_KEY must be set in production. "
                "Generate one with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
            )
        _secret = secrets.token_hex(32)
        logger.warning(
            "SECRET_KEY not set — using random key (sessions will not persist across restarts)"
        )
    app.config["SECRET_KEY"] = _secret

    # ── Logging ──────────────────────────────────────────────────────
    setup_logging(app)

    # ── Extensions ───────────────────────────────────────────────────
    limiter.init_app(app)
    sqlalchemy_db.init_app(app)
    migrate.init_app(app, sqlalchemy_db)
    csrf.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Veuillez vous connecter pour accéder à cette page."
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return sqlalchemy_db.session.get(User, int(user_id))

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

    # ── Error handlers & health check ────────────────────────────────
    register_error_handlers(app)
    register_health_check(app)

    # ── Database init ────────────────────────────────────────────────
    with app.app_context():
        sqlalchemy_db.create_all()
        _seed_default_data()

    return app


# WSGI entry point — allows `gunicorn app:app` (Railway/Render default)
app = create_app()


def _seed_default_data():
    """Seed default venues, settings, and generate random admin password."""
    from app.models import User, Venue, Setting, db
    import string

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
        if not db.session.get(Setting, key):
            db.session.add(Setting(key=key, value=default))
    db.session.commit()

    # Default admin user with RANDOM password
    if User.query.count() == 0:
        admin_pw = os.environ.get("ADMIN_PASSWORD")
        if not admin_pw:
            # Generate a secure random password
            alphabet = string.ascii_letters + string.digits + "!@#$%"
            admin_pw = ''.join(secrets.choice(alphabet) for _ in range(16))

        admin = User(username="admin", role="admin")
        admin.set_password(admin_pw)
        db.session.add(admin)
        db.session.commit()

        # Log the password ONCE (first run only)
        logger.warning("DEFAULT ADMIN CREATED — Username: admin | Password: %s — CHANGE IMMEDIATELY", admin_pw)

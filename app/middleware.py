"""Samba Fête — Error handling middleware and health check.

Global exception handler + /health endpoint for monitoring.
"""
import logging
import traceback
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from sqlalchemy import text

from app.models import db

logger = logging.getLogger(__name__)


def register_error_handlers(app: Flask):
    """Register global error handlers."""

    @app.errorhandler(400)
    def bad_request(e):
        logger.warning("400 Bad Request: %s %s", request.method, request.path)
        if request.accept_mimetypes.accept_json:
            return jsonify(error="Bad request", message=str(e)), 400
        return "Bad request", 400

    @app.errorhandler(403)
    def forbidden(e):
        logger.warning("403 Forbidden: %s %s from %s", request.method, request.path, request.remote_addr)
        if request.accept_mimetypes.accept_json:
            return jsonify(error="Forbidden"), 403
        return "Forbidden", 403

    @app.errorhandler(404)
    def not_found(e):
        if request.accept_mimetypes.accept_json:
            return jsonify(error="Not found", path=request.path), 404
        return "Not found", 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        if request.accept_mimetypes.accept_json:
            return jsonify(error="Method not allowed"), 405
        return "Method not allowed", 405

    @app.errorhandler(429)
    def rate_limit_exceeded(e):
        logger.warning("429 Rate limit: %s from %s", request.path, request.remote_addr)
        if request.accept_mimetypes.accept_json:
            return jsonify(error="Rate limit exceeded", retry_after=60), 429
        from flask import flash, render_template
        flash("Trop de tentatives. Veuillez patienter.", "danger")
        return render_template("auth/login.html"), 429

    @app.errorhandler(500)
    def internal_error(e):
        error_id = datetime.now().strftime("%Y%m%d%H%M%S")
        logger.error(
            "500 Internal Error [%s]: %s %s\n%s",
            error_id, request.method, request.path, traceback.format_exc(),
            extra={"endpoint": request.endpoint, "ip": request.remote_addr},
        )
        if app.config.get("FLASK_ENV") == "production":
            if request.accept_mimetypes.accept_json:
                return jsonify(error="Internal server error", error_id=error_id), 500
            return f"Error {error_id}", 500
        # Dev mode: show traceback
        return (
            f'<html><body style="font-family:monospace;padding:40px;background:#1a1a2e;color:#eee">'
            f'<h1 style="color:#e74c3c">500 Error [{error_id}]</h1>'
            f'<pre style="background:#16213e;padding:20px;border-radius:8px;overflow-x:auto">'
            f'{traceback.format_exc()}</pre></body></html>',
            500,
        )

    @app.errorhandler(Exception)
    def unhandled_exception(e):
        """Catch-all for any unhandled exception."""
        error_id = datetime.now().strftime("%Y%m%d%H%M%S")
        logger.critical(
            "Unhandled Exception [%s]: %s\n%s",
            error_id, str(e), traceback.format_exc(),
        )
        if request.accept_mimetypes.accept_json:
            return jsonify(error="Internal server error", error_id=error_id), 500
        return f"Error {error_id}", 500


def register_health_check(app: Flask):
    """Register /health endpoint for load balancers and monitoring."""

    @app.route("/health")
    def health_check():
        """Health check — verifies app is running and DB is reachable."""
        health = {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": app.config.get("APP_VERSION", "1.0.0"),
        }

        # Database check (optional — don't fail if DB isn't ready yet)
        try:
            db.session.execute(text("SELECT 1"))
            health["database"] = "ok"
        except Exception as e:
            health["database"] = f"error: {str(e)[:100]}"
            # Don't mark as degraded — app can still serve static/login

        return jsonify(health), 200

    @app.route("/health/ready")
    def health_ready():
        """Readiness probe — returns 200 when app is ready to serve traffic."""
        from app.models import db
        try:
            db.session.execute(text("SELECT 1"))
            return jsonify(ready=True), 200
        except Exception:
            return jsonify(ready=False), 503

    @app.route("/health/live")
    def health_live():
        """Liveness probe — returns 200 if the process is alive."""
        return jsonify(alive=True), 200

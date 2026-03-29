"""Samba Fête — Auth decorators.

Reusable role-based access control decorators.
"""
from functools import wraps

from flask import flash, redirect, url_for
from flask_login import current_user, login_required as _flask_login_required


def admin_required(f):
    """Restrict route to admin users only.

    Usage:
        @bp.route("/admin-only")
        @login_required
        @admin_required
        def secret():
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            flash("Accès réservé aux administrateurs", "danger")
            return redirect(url_for("finance.dashboard"))
        return f(*args, **kwargs)
    return decorated

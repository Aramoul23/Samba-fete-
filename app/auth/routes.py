"""Samba Fête — Auth routes.

Login, logout, user management (admin only).
Blueprint prefix: /auth  (but login/logout also mapped at root for compat).
"""
import logging
from urllib.parse import urlparse

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from app.auth.decorators import admin_required
from app.db import get_db_connection
from models import (
    create_user,
    delete_user,
    get_all_users,
    get_user_by_username,
    update_user,
)

logger = logging.getLogger(__name__)

bp = Blueprint("auth", __name__, template_folder="../templates")


# ─── Login / Logout ──────────────────────────────────────────────────

@bp.route("/login", methods=["GET", "POST"])
def login():
    """Gère la connexion et l'authentification des utilisateurs."""
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = get_user_by_username(username)
        if user and user.check_password(password):
            if not user.is_active:
                flash("Ce compte est désactivé", "danger")
                return render_template("login.html")
            login_user(user, remember=True)
            logger.info("Successful login: %s", user.username)
            next_page = request.args.get("next")
            if next_page:
                parsed = urlparse(next_page)
                if parsed.netloc and parsed.netloc != request.host:
                    next_page = None  # reject external redirect
            flash(f"Bienvenue, {user.username}!", "success")
            return redirect(next_page or url_for("index"))
        else:
            flash("Nom d'utilisateur ou mot de passe incorrect", "danger")

    return render_template("login.html")


@bp.route("/logout")
@login_required
def logout():
    """Déconnecte l'utilisateur actuel."""
    logger.info("User logged out: %s", current_user.username)
    logout_user()
    flash("Vous avez été déconnecté", "info")
    return redirect(url_for("auth.login"))


# ─── Register (placeholder for future) ──────────────────────────────

@bp.route("/register", methods=["GET", "POST"])
def register():
    """Inscription — à implémenter (admin-created accounts for now)."""
    flash("L'inscription est réservée aux administrateurs. Contactez votre admin.", "info")
    return redirect(url_for("auth.login"))


# ─── Password Reset (placeholder for future) ────────────────────────

@bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    """Réinitialisation du mot de passe — à implémenter."""
    flash("Contactez votre administrateur pour réinitialiser votre mot de passe.", "info")
    return redirect(url_for("auth.login"))


# ─── User Management (Admin Only) ────────────────────────────────────

@bp.route("/parametres/utilisateurs", methods=["GET"])
@login_required
@admin_required
def users():
    """Affiche la gestion des utilisateurs."""
    users_list = get_all_users()
    return render_template("users.html", users=users_list, current_user=current_user)


@bp.route("/parametres/utilisateurs/ajouter", methods=["POST"])
@login_required
@admin_required
def add_user():
    """Ajoute un nouvel utilisateur."""
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    role = request.form.get("role", "manager")

    if not username or not password:
        flash("Nom d'utilisateur et mot de passe requis", "danger")
        return redirect(url_for("auth.users"))

    if role not in ("admin", "manager"):
        flash("Rôle invalide", "danger")
        return redirect(url_for("auth.users"))

    existing = get_user_by_username(username)
    if existing:
        flash(f"Le nom d'utilisateur '{username}' existe déjà", "danger")
        return redirect(url_for("auth.users"))

    create_user(username, password, role)
    flash(f"Utilisateur '{username}' créé avec succès", "success")
    return redirect(url_for("auth.users"))


@bp.route("/parametres/utilisateurs/<int:user_id>/modifier", methods=["POST"])
@login_required
@admin_required
def edit_user(user_id):
    """Modifie un utilisateur existant."""
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    role = request.form.get("role", "manager")
    is_active = request.form.get("is_active", "1") == "1"

    if not username:
        flash("Le nom d'utilisateur est requis", "danger")
        return redirect(url_for("auth.users"))

    if role not in ("admin", "manager"):
        flash("Rôle invalide", "danger")
        return redirect(url_for("auth.users"))

    existing = get_user_by_username(username)
    if existing and existing.id != user_id:
        flash(f"Le nom d'utilisateur '{username}' est déjà utilisé", "danger")
        return redirect(url_for("auth.users"))

    update_user(
        user_id,
        username=username,
        password=password if password else None,
        role=role,
        is_active=is_active,
    )
    flash("Utilisateur mis à jour", "success")
    return redirect(url_for("auth.users"))


@bp.route("/parametres/utilisateurs/<int:user_id>/supprimer", methods=["POST"])
@login_required
@admin_required
def delete_user_route(user_id):
    """Supprime un utilisateur."""
    if user_id == current_user.id:
        flash("Vous ne pouvez pas supprimer votre propre compte", "danger")
        return redirect(url_for("auth.users"))

    delete_user(user_id)
    flash("Utilisateur supprimé", "success")
    return redirect(url_for("auth.users"))

"""Samba Fête — Auth routes (SQLAlchemy ORM)."""
import logging
from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.auth.decorators import admin_required
from app.models import db, User

logger = logging.getLogger(__name__)
bp = Blueprint("auth", __name__, template_folder="../templates")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("finance.dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.get_by_username(username)
        if user and user.check_password(password):
            if not user.is_active:
                flash("Ce compte est désactivé", "danger")
                return render_template("auth/login.html")
            login_user(user, remember=True)
            logger.info("Successful login: %s", user.username)
            next_page = request.args.get("next")
            if next_page:
                parsed = urlparse(next_page)
                if parsed.netloc and parsed.netloc != request.host:
                    next_page = None
            flash(f"Bienvenue, {user.username}!", "success")
            return redirect(next_page or url_for("finance.dashboard"))
        else:
            flash("Nom d'utilisateur ou mot de passe incorrect", "danger")
    return render_template("auth/login.html")


@bp.route("/logout")
@login_required
def logout():
    logger.info("User logged out: %s", current_user.username)
    logout_user()
    flash("Vous avez été déconnecté", "info")
    return redirect(url_for("auth.login"))


@bp.route("/register", methods=["GET", "POST"])
def register():
    flash("L'inscription est réservée aux administrateurs.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    flash("Contactez votre administrateur.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/parametres/utilisateurs", methods=["GET"])
@login_required
@admin_required
def users():
    return render_template("auth/users.html", users=User.get_all_ordered(), current_user=current_user)


@bp.route("/parametres/utilisateurs/ajouter", methods=["POST"])
@login_required
@admin_required
def add_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    role = request.form.get("role", "manager")

    if not username or not password:
        flash("Nom d'utilisateur et mot de passe requis", "danger")
        return redirect(url_for("auth.users"))
    if role not in ("admin", "manager"):
        flash("Rôle invalide", "danger")
        return redirect(url_for("auth.users"))
    if User.get_by_username(username):
        flash(f"'{username}' existe déjà", "danger")
        return redirect(url_for("auth.users"))

    try:
        user = User(username=username, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash(f"Utilisateur '{username}' créé", "success")
    except Exception:
        db.session.rollback()
        flash("Erreur lors de la création.", "danger")
    return redirect(url_for("auth.users"))


@bp.route("/parametres/utilisateurs/<int:user_id>/modifier", methods=["POST"])
@login_required
@admin_required
def edit_user(user_id):
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

    existing = User.get_by_username(username)
    if existing and existing.id != user_id:
        flash(f"'{username}' est déjà utilisé", "danger")
        return redirect(url_for("auth.users"))

    try:
        user = User.query.get_or_404(user_id)
        user.username = username
        user.role = role
        user.is_active = 1 if is_active else 0
        if password:
            user.set_password(password)
        db.session.commit()
        flash("Utilisateur mis à jour", "success")
    except Exception:
        db.session.rollback()
        flash("Erreur lors de la mise à jour.", "danger")
    return redirect(url_for("auth.users"))


@bp.route("/parametres/utilisateurs/<int:user_id>/supprimer", methods=["POST"])
@login_required
@admin_required
def delete_user_route(user_id):
    if user_id == current_user.id:
        flash("Vous ne pouvez pas supprimer votre propre compte", "danger")
        return redirect(url_for("auth.users"))
    try:
        user = User.query.get_or_404(user_id)
        db.session.delete(user)
        db.session.commit()
        flash("Utilisateur supprimé", "success")
    except Exception:
        db.session.rollback()
        flash("Erreur lors de la suppression.", "danger")
    return redirect(url_for("auth.users"))

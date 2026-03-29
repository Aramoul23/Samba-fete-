"""Samba Fête — Auth routes (with WTForms validation + CSRF)."""
import logging
from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from flask_limiter import RateLimitExceeded

from app.auth.decorators import admin_required
from app.models import db, User
from app.forms import LoginForm, UserForm, UserEditForm
from app import limiter

logger = logging.getLogger(__name__)
bp = Blueprint("auth", __name__, template_folder="../templates")


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def login():
    form = LoginForm()
    if current_user.is_authenticated:
        return redirect(url_for("finance.dashboard"))

    if form.validate_on_submit():
        user = User.get_by_username(form.username.data.strip())
        if user and user.check_password(form.password.data):
            if not user.is_active:
                flash("Ce compte est désactivé", "danger")
                return render_template("auth/login.html", form=form)
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

    return render_template("auth/login.html", form=form)


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
    form = UserForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        if User.get_by_username(username):
            flash(f"'{username}' existe déjà", "danger")
            return redirect(url_for("auth.users"))

        try:
            user = User(username=username, role=form.role.data)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash(f"Utilisateur '{username}' créé", "success")
        except Exception:
            db.session.rollback()
            flash("Erreur lors de la création.", "danger")
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{error}", "danger")
    return redirect(url_for("auth.users"))


@bp.route("/parametres/utilisateurs/<int:user_id>/modifier", methods=["POST"])
@login_required
@admin_required
def edit_user(user_id):
    form = UserEditForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        existing = User.get_by_username(username)
        if existing and existing.id != user_id:
            flash(f"'{username}' est déjà utilisé", "danger")
            return redirect(url_for("auth.users"))

        try:
            user = User.query.get_or_404(user_id)
            user.username = username
            user.role = form.role.data
            user.is_active = 1 if form.is_active.data else 0
            if form.password.data:
                user.set_password(form.password.data)
            db.session.commit()
            flash("Utilisateur mis à jour", "success")
        except Exception:
            db.session.rollback()
            flash("Erreur lors de la mise à jour.", "danger")
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{error}", "danger")
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

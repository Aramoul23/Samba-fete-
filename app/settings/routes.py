"""Samba Fête — Settings blueprint."""
import logging

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required
from models import get_setting, set_setting

from app.db import get_db_connection

logger = logging.getLogger(__name__)
bp = Blueprint("settings", __name__, template_folder="../templates")


@bp.route("/parametres", methods=["GET", "POST"])
@login_required
def settings():
    """Page de paramètres."""
    db = get_db_connection()
    if request.method == "POST":
        for venue_id in request.form.getlist("venue_id"):
            cap_m = request.form.get(f"capacity_men_{venue_id}", 0, type=int)
            cap_w = request.form.get(f"capacity_women_{venue_id}", 0, type=int)
            db.execute(
                "UPDATE venues SET capacity_men=?, capacity_women=? WHERE id=?",
                (cap_m, cap_w, venue_id),
            )
        set_setting("deposit_min", str(request.form.get("deposit_min", 0, type=float)))
        set_setting("hall_name", request.form.get("hall_name", "Samba Fête"))
        set_setting("currency", request.form.get("currency", "DA"))

        new_name = request.form.get("new_venue_name", "").strip()
        if new_name:
            db.execute(
                "INSERT INTO venues (name, capacity_men, capacity_women) VALUES (?,?,?)",
                (new_name, request.form.get("new_venue_cap_m", 0, type=int),
                 request.form.get("new_venue_cap_w", 0, type=int)),
            )
        db.commit()
        flash("Paramètres enregistrés!", "success")

    venues = db.execute("SELECT * FROM venues ORDER BY id").fetchall()
    return render_template(
        "settings/settings.html", venues=venues,
        deposit_min=get_setting("deposit_min", "20000"),
        hall_name=get_setting("hall_name", "Samba Fête"),
        currency=get_setting("currency", "DA"),
    )


@bp.route("/parametres/lieu/<int:venue_id>/supprimer", methods=["POST"])
@login_required
def delete_venue(venue_id):
    """Supprime un lieu s'il n'a pas d'événements."""
    db = get_db_connection()
    count = db.execute(
        "SELECT COUNT(*) as c FROM events WHERE venue_id=?", (venue_id,)
    ).fetchone()["c"]
    if count > 0:
        flash("Impossible de supprimer: ce lieu a des événements", "danger")
    else:
        db.execute("DELETE FROM venues WHERE id=?", (venue_id,))
        db.commit()
        flash("Lieu supprimé", "success")
    return redirect(url_for("settings.settings"))

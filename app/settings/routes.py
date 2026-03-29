"""Samba Fête — Settings blueprint (SQLAlchemy ORM)."""
import logging
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.models import db, Venue, Setting

logger = logging.getLogger(__name__)
bp = Blueprint("settings", __name__, template_folder="../templates")


@bp.route("/parametres", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        for vid in request.form.getlist("venue_id"):
            v = Venue.query.get(int(vid))
            if v:
                v.capacity_men = request.form.get(f"capacity_men_{vid}", 0, type=int)
                v.capacity_women = request.form.get(f"capacity_women_{vid}", 0, type=int)
        Setting.set("deposit_min", str(request.form.get("deposit_min", 0, type=float)))
        Setting.set("hall_name", request.form.get("hall_name", "Samba Fête"))
        Setting.set("currency", request.form.get("currency", "DA"))
        new_name = request.form.get("new_venue_name", "").strip()
        if new_name:
            db.session.add(Venue(name=new_name, capacity_men=request.form.get("new_venue_cap_m", 0, type=int),
                                 capacity_women=request.form.get("new_venue_cap_w", 0, type=int)))
        db.session.commit()
        flash("Paramètres enregistrés!", "success")

    return render_template("settings/settings.html", venues=Venue.query.order_by(Venue.id).all(),
                           deposit_min=Setting.get("deposit_min", "20000"),
                           hall_name=Setting.get("hall_name", "Samba Fête"),
                           currency=Setting.get("currency", "DA"))


@bp.route("/parametres/lieu/<int:venue_id>/supprimer", methods=["POST"])
@login_required
def delete_venue(venue_id):
    v = Venue.query.get_or_404(venue_id)
    if v.events.count() > 0:
        flash("Impossible de supprimer: ce lieu a des événements", "danger")
    else:
        db.session.delete(v); db.session.commit(); flash("Lieu supprimé", "success")
    return redirect(url_for("settings.settings"))

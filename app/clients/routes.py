"""Samba Fête — Clients blueprint."""
import logging

from flask import (
    Blueprint, flash, redirect, render_template, request, url_for,
)
from flask_login import login_required

from app.db import get_db_connection

logger = logging.getLogger(__name__)
bp = Blueprint("clients", __name__, template_folder="../templates")


@bp.route("/clients")
@login_required
def client_list():
    """Liste des clients avec recherche."""
    db = get_db_connection()
    search = request.args.get("q", "").strip()
    query = (
        "SELECT c.*, "
        "(SELECT COUNT(*) FROM events WHERE client_id=c.id) as event_count, "
        "(SELECT COALESCE(SUM(CASE WHEN p.is_refunded=0 THEN p.amount ELSE 0 END),0) "
        "FROM payments p JOIN events e ON p.event_id=e.id WHERE e.client_id=c.id) as total_paid, "
        "(SELECT COALESCE(SUM(e.total_amount),0) FROM events e WHERE e.client_id=c.id) as total_owed "
        "FROM clients c WHERE 1=1"
    )
    params = []
    if search:
        query += " AND (c.name LIKE ? OR c.phone LIKE ? OR c.email LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    query += " ORDER BY c.created_at DESC"
    clients = db.execute(query, params).fetchall()
    return render_template("client_list.html", clients=clients, search=search)


@bp.route("/client/<int:client_id>")
@login_required
def client_detail(client_id):
    """Détails d'un client avec historique."""
    db = get_db_connection()
    client = db.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
    if not client:
        flash("Client introuvable", "danger")
        return redirect(url_for("clients.client_list"))

    events = db.execute(
        "SELECT e.*, v.name as venue_name FROM events e "
        "JOIN venues v ON e.venue_id=v.id WHERE e.client_id=? ORDER BY e.event_date DESC",
        (client_id,),
    ).fetchall()

    total_owed = db.execute(
        "SELECT COALESCE(SUM(total_amount),0) as s FROM events WHERE client_id=?",
        (client_id,),
    ).fetchone()["s"]

    total_paid = db.execute(
        "SELECT COALESCE(SUM(CASE WHEN p.is_refunded=0 THEN p.amount ELSE 0 END),0) as s "
        "FROM payments p JOIN events e ON p.event_id=e.id WHERE e.client_id=?",
        (client_id,),
    ).fetchone()["s"]

    all_payments = db.execute(
        "SELECT p.*, e.title as event_title, e.id as event_id "
        "FROM payments p JOIN events e ON p.event_id=e.id "
        "WHERE e.client_id=? ORDER BY p.payment_date DESC",
        (client_id,),
    ).fetchall()

    # Batch financials per event
    event_financials = {}
    event_ids = [ev["id"] for ev in events]
    if event_ids:
        ph = ",".join("?" * len(event_ids))
        rev_map = {r["event_id"]: float(r["total"]) for r in db.execute(
            f"SELECT event_id, COALESCE(SUM(amount),0) as total FROM event_lines "
            f"WHERE event_id IN ({ph}) AND is_cost=0 GROUP BY event_id", event_ids,
        ).fetchall()}
        cost_map = {r["event_id"]: float(r["total"]) for r in db.execute(
            f"SELECT event_id, COALESCE(SUM(amount),0) as total FROM event_lines "
            f"WHERE event_id IN ({ph}) AND is_cost=1 GROUP BY event_id", event_ids,
        ).fetchall()}
        paid_map = {r["event_id"]: float(r["total"]) for r in db.execute(
            f"SELECT event_id, COALESCE(SUM(amount),0) as total FROM payments "
            f"WHERE event_id IN ({ph}) AND is_refunded=0 GROUP BY event_id", event_ids,
        ).fetchall()}
        for ev in events:
            eid = ev["id"]
            r = rev_map.get(eid, 0.0)
            c = cost_map.get(eid, 0.0)
            p = paid_map.get(eid, 0.0)
            event_financials[eid] = {
                "revenue": r, "costs": c, "profit": r - c,
                "paid": p, "remaining": round(float(ev["total_amount"]) - p, 2),
            }

    return render_template(
        "client_detail.html",
        client=client, events=events,
        total_owed=total_owed, total_paid=total_paid,
        all_payments=all_payments, event_financials=event_financials,
    )

"""Samba Fête — Clients blueprint (SQLAlchemy ORM)."""
import logging
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import func, or_

from app.models import db, Client, Event, EventLine, Payment

logger = logging.getLogger(__name__)
bp = Blueprint("clients", __name__, template_folder="../templates")


@bp.route("/clients")
@login_required
def client_list():
    search = request.args.get("q", "").strip()
    q = Client.query
    if search:
        q = q.filter(or_(Client.name.ilike(f"%{search}%"), Client.phone.ilike(f"%{search}%"), Client.email.ilike(f"%{search}%")))
    return render_template("clients/client_list.html", clients=q.order_by(Client.created_at.desc()).all(), search=search)


@bp.route("/client/<int:client_id>")
@login_required
def client_detail(client_id):
    client = Client.query.get_or_404(client_id)
    events = Event.query.filter_by(client_id=client_id).order_by(Event.event_date.desc()).all()
    total_owed = sum(e.total_amount for e in events)
    total_paid = sum(p.amount for e in events for p in e.payments if not p.is_refunded)
    all_payments = Payment.query.join(Event).filter(Event.client_id == client_id).order_by(Payment.payment_date.desc()).all()

    event_financials = {}
    for ev in events:
        rev = db.session.query(func.coalesce(func.sum(EventLine.amount), 0)).filter(EventLine.event_id == ev.id, EventLine.is_cost == 0).scalar()
        cst = db.session.query(func.coalesce(func.sum(EventLine.amount), 0)).filter(EventLine.event_id == ev.id, EventLine.is_cost == 1).scalar()
        paid = ev.total_paid
        event_financials[ev.id] = {"revenue": float(rev), "costs": float(cst), "profit": float(rev) - float(cst), "paid": paid, "remaining": ev.remaining}

    return render_template("clients/client_detail.html", client=client, events=events,
                           total_owed=total_owed, total_paid=total_paid, all_payments=all_payments,
                           event_financials=event_financials)

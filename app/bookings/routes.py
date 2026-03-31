"""Samba Fête — Booking routes (SQLAlchemy ORM).

All event/booking CRUD, calendar, payments, status transitions,
contracts, receipts, and the quick-payment page.
"""
import calendar as _calendar
import json
import logging
from datetime import date, datetime, timedelta
from urllib.parse import urlparse

from flask import (
    Blueprint,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import or_, func

from app.models import db, Event, Client, EventLine, Payment, Expense, Venue
from app.bookings.helpers import (
    ALL_STATUSES,
    EVENT_STATUSES,
    EVENT_TYPES,
    MONTH_NAMES_FR,
    STATUS_TRANSITIONS,
    TIME_SLOTS,
)

logger = logging.getLogger(__name__)
bp = Blueprint("bookings", __name__, template_folder="../templates")


# ─── Helpers ─────────────────────────────────────────────────────────

def _is_admin():
    return current_user.is_authenticated and current_user.role == "admin"


def validate_event_date(event_date, event_id=0):
    """Check for double-bookings. Returns list of error strings."""
    if not event_date:
        return []
    conflict = Event.query.filter(
        Event.event_date == event_date,
        Event.status.in_(["confirmé", "en attente"]),
        Event.id != (event_id or 0),
    ).first()
    if not conflict:
        return []
    venue_label = f" ({conflict.venue.name})" if conflict.venue else ""
    if conflict.status == "confirmé":
        return [f"⛔ Date réservée! '{conflict.title}' le {event_date}{venue_label} — 🔒 verrouillée"]
    return [f"⚠️ '{conflict.title}' en attente pour le {event_date}{venue_label}"]


def insert_service_lines(event_id, form_data):
    """Insert service lines from form data."""
    # Location (always if price > 0)
    price = form_data.get("price_location", 0, type=float)
    if price > 0:
        db.session.add(EventLine(event_id=event_id, description="Location de la salle", amount=price))

    # Checkbox-driven services
    from app.bookings.helpers import DEFAULT_SERVICES
    for key, name, _ in DEFAULT_SERVICES:
        if key == "location":
            continue
        if not form_data.get(f"service_{key}"):
            continue
        price = form_data.get(f"price_{key}", 0, type=float)
        if price > 0:
            db.session.add(EventLine(event_id=event_id, description=name, amount=price))

    # Autre
    if form_data.get("service_autre"):
        price = form_data.get("price_autre", 0, type=float)
        name = form_data.get("autre_name", "").strip() or "Autre"
        if price > 0:
            db.session.add(EventLine(event_id=event_id, description=name, amount=price))

    # Free-form lines
    for i, desc in enumerate(form_data.getlist("line_desc[]")):
        if desc.strip():
            amount = float(form_data.getlist("line_amount[]")[i]) if i < len(form_data.getlist("line_amount[]")) else 0
            is_cost = 1 if str(i) in form_data.getlist("line_is_cost[]") else 0
            db.session.add(EventLine(event_id=event_id, description=desc.strip(), amount=amount, is_cost=is_cost))


def check_pending_events():
    """Events 'en attente' > 48h in next 30 days."""
    threshold = (datetime.now() - timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")
    future = (date.today() + timedelta(days=30)).isoformat()
    today = date.today().isoformat()
    return Event.query.filter(
        Event.status == "en attente",
        Event.event_date.between(today, future),
        Event.created_at < threshold,
    ).all()


# ─── Calendar ────────────────────────────────────────────────────────
@bp.route("/calendrier")
@login_required
def calendar_view():
    year = request.args.get("year", date.today().year, type=int)
    month = request.args.get("month", date.today().month, type=int)
    first = f"{year}-{month:02d}-01"
    last = f"{year + 1}-01-01" if month == 12 else f"{year}-{month + 1:02d}-01"
    venue_filter = request.args.get("venue", type=int)

    # Load events for ±2 months so FullCalendar nav doesn't need page reload
    from datetime import datetime as dt
    center = dt(year, month, 1)
    range_start = (center - timedelta(days=62)).replace(day=1).strftime("%Y-%m-%d")
    range_end_month = month + 3 if month <= 9 else (month + 3) % 12 or 12
    range_end_year = year if month <= 9 else year + 1
    range_end = f"{range_end_year}-{range_end_month:02d}-01"

    q = Event.query.filter(
        Event.event_date >= range_start, Event.event_date < range_end,
        Event.status != "annulé",
    ).order_by(Event.event_date)
    if venue_filter:
        q = q.filter(or_(Event.venue_id == venue_filter, Event.venue_id2 == venue_filter))

    events = q.all()
    booked_dict = {}
    date_status_map = {}
    date_url_map = {}
    for ev in events:
        booked_dict.setdefault(ev.event_date, []).append(ev)
        d = str(ev.event_date)[:10]
        if ev.event_date and ev.status:
            date_status_map[d] = ev.status
            date_url_map[d] = url_for("bookings.event_detail", event_id=ev.id)

    return render_template(
        "bookings/calendar.html",
        year=year, month=month, month_name=MONTH_NAMES_FR[month],
        weeks=_calendar.Calendar(firstweekday=0).monthdayscalendar(year, month),
        booked_dict=booked_dict,
        today_str=date.today().isoformat(),
        venues=Venue.query.filter_by(is_active=1).all(),
        time_slots=TIME_SLOTS, venue_filter=venue_filter or "",
        pending_needs_attention=check_pending_events(),
        date_status_map=json.dumps(date_status_map),
        date_url_map=json.dumps(date_url_map),
    )


# ─── Event List ──────────────────────────────────────────────────────
@bp.route("/evenements")
@login_required
def event_list():
    status_filter = request.args.get("status", "")
    search = request.args.get("q", "").strip()

    q = Event.query.join(Client).join(Venue, Event.venue_id == Venue.id)
    if status_filter:
        q = q.filter(Event.status == status_filter)
    if search:
        q = q.filter(or_(Event.title.ilike(f"%{search}%"), Client.name.ilike(f"%{search}%")))
    events = q.order_by(Event.event_date.desc()).all()

    return render_template(
        "bookings/list.html", events=events,
        statuses=ALL_STATUSES, status_filter=status_filter, search=search,
    )


# ─── Create / Edit Event ────────────────────────────────────────────
@bp.route("/evenement/nouveau", methods=["GET", "POST"])
@bp.route("/evenement/<int:event_id>/modifier", methods=["GET", "POST"])
@login_required
def event_form(event_id=None):
    event = db.session.get(Event, event_id) if event_id else None
    client = db.session.get(Client, event.client_id) if event else None
    event_lines = []
    custom_lines = []

    if event:
        from app.bookings.helpers import PREDEFINED_NAMES
        event_lines = [ln for ln in event.service_lines.all() if ln.description in PREDEFINED_NAMES]
        custom_lines = [ln for ln in event.service_lines.all() if ln.description not in PREDEFINED_NAMES]

    venues = Venue.query.filter_by(is_active=1).all()

    if request.method == "POST":
        data = request.form
        title = data.get("title", "").strip()
        client_name = data.get("client_name", "").strip()
        client_phone = data.get("client_phone", "").strip()
        client_phone2 = data.get("client_phone2", "").strip()
        client_email = data.get("client_email", "").strip()
        client_address = data.get("client_address", "").strip()
        venue_id = data.get("venue_id", type=int)
        venue_id2 = data.get("venue_id2", type=int)
        event_type = data.get("event_type", "Mariage")
        event_date_val = data.get("event_date")
        time_slot = data.get("time_slot", "Soirée")
        guests_men = data.get("guests_men", 0, type=int)
        guests_women = data.get("guests_women", 0, type=int)
        status = data.get("status", "en attente") if not event_id else data.get("status", event.status)
        notes = data.get("notes", "").strip()
        total_amount = data.get("total_amount", 0, type=float)
        deposit_required = data.get("deposit_required", 0, type=float)

        # Validation
        errors = []
        if not title: errors.append("Le titre est requis")
        if not client_name: errors.append("Le nom du client est requis")
        if not client_phone: errors.append("Le téléphone est requis")
        if not event_date_val: errors.append("La date est requise")
        if not venue_id: errors.append("Le lieu est requis")

        # One-event-per-day enforcement (regardless of venue or status)
        if event_date_val:
            date_conflict = Event.query.filter(
                Event.event_date == event_date_val,
                Event.id != (event_id or 0),
            ).first()
            if date_conflict:
                flash("Cette date est déjà réservée", "danger")
                return redirect(request.referrer or url_for("bookings.event_list"))

        errors.extend(validate_event_date(event_date_val, event_id or 0))

        if errors:
            for e in errors: flash(e, "danger")
            return render_template(
                "bookings/create.html" if not event_id else "bookings/edit.html",
                event=event, client=client, event_lines=event_lines, custom_lines=custom_lines,
                venues=venues, time_slots=TIME_SLOTS, event_types=EVENT_TYPES,
                statuses=EVENT_STATUSES, event_id=event_id,
            )

        # Upsert client
        if client:
            client.name, client.phone, client.phone2, client.email, client.address = (
                client_name, client_phone, client_phone2, client_email, client_address
            )
        else:
            client = Client(name=client_name, phone=client_phone, phone2=client_phone2,
                            email=client_email, address=client_address)
            db.session.add(client)
            db.session.flush()

        now = datetime.now()
        if event:
            event.title, event.client_id, event.venue_id, event.venue_id2 = title, client.id, venue_id, venue_id2
            event.event_type, event.event_date, event.time_slot = event_type, event_date_val, time_slot
            event.guests_men, event.guests_women, event.status = guests_men, guests_women, status
            event.notes, event.total_amount, event.deposit_required, event.updated_at = notes, total_amount, deposit_required, now
            EventLine.query.filter_by(event_id=event.id).delete()
            event_id = event.id
        else:
            event = Event(title=title, client_id=client.id, venue_id=venue_id, venue_id2=venue_id2,
                          event_type=event_type, event_date=event_date_val, time_slot=time_slot,
                          guests_men=guests_men, guests_women=guests_women, status=status,
                          notes=notes, total_amount=total_amount, deposit_required=deposit_required,
                          created_at=now, updated_at=now)
            db.session.add(event)
            db.session.flush()
            event_id = event.id
            # Auto deposit (only on create)
            if deposit_required and deposit_required > 0:
                db.session.add(Payment(event_id=event_id, amount=deposit_required,
                                       payment_type="avance", method="espèces", payment_date=now))

        # Service lines
        insert_service_lines(event_id, data)
        db.session.commit()
        flash("Événement créé avec succès!", "success")
        return redirect(url_for("bookings.event_detail", event_id=event_id))

    template = "bookings/create.html" if not event_id else "bookings/edit.html"

    # For edit: show current status + allowed transitions
    edit_statuses = EVENT_STATUSES
    if event:
        current = event.status
        allowed_next = STATUS_TRANSITIONS.get(current, [])
        edit_statuses = [current] + [s for s in allowed_next if s != current]

    # Build date maps for mini calendar
    from datetime import datetime as dt
    _now = date.today()
    range_start_dt = (dt(_now.year, _now.month, 1) - timedelta(days=62)).replace(day=1)
    range_end_month = (_now.month + 3) % 12 or 12
    range_end_year = _now.year + (1 if _now.month + 3 > 12 else 0)
    range_end_str = f"{range_end_year}-{range_end_month:02d}-01"
    cal_events = Event.query.filter(
        Event.event_date >= range_start_dt, Event.event_date < range_end_str,
        Event.status != "annulé",
    ).all()
    mini_date_status_map = {}
    mini_date_url_map = {}
    for ev in cal_events:
        d = str(ev.event_date)[:10]
        if ev.event_date and ev.status:
            mini_date_status_map[d] = ev.status
            mini_date_url_map[d] = url_for("bookings.event_detail", event_id=ev.id)

    return render_template(
        template, event=event, client=client, event_lines=event_lines,
        custom_lines=custom_lines, venues=venues, time_slots=TIME_SLOTS,
        event_types=EVENT_TYPES, statuses=edit_statuses, event_id=event_id,
        all_statuses=ALL_STATUSES,
        date_status_map=json.dumps(mini_date_status_map),
        date_url_map=json.dumps(mini_date_url_map),
    )


# ─── Event Detail ────────────────────────────────────────────────────
@bp.route("/evenement/<int:event_id>")
@login_required
def event_detail(event_id):
    event = Event.query.get_or_404(event_id)

    total_paid = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.event_id == event_id, Payment.is_refunded == 0).scalar()
    total_refunded = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.event_id == event_id, Payment.is_refunded == 1).scalar()
    total_revenue = db.session.query(func.coalesce(func.sum(EventLine.amount), 0)).filter(
        EventLine.event_id == event_id, EventLine.is_cost == 0).scalar()
    total_costs = db.session.query(func.coalesce(func.sum(EventLine.amount), 0)).filter(
        EventLine.event_id == event_id, EventLine.is_cost == 1).scalar()
    total_expenses = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.event_id == event_id).scalar()
    deposit = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.event_id == event_id, Payment.payment_type == "dépôt", Payment.is_refunded == 0).scalar()

    profit = float(total_revenue) - float(total_costs)
    adjusted_profit = round(profit - float(total_expenses), 2)

    needs_confirmation = False
    if event.status == "en attente" and event.created_at:
        created = event.created_at if isinstance(event.created_at, datetime) else datetime.strptime(str(event.created_at)[:19], "%Y-%m-%d %H:%M:%S")
        if (datetime.now() - created) > timedelta(hours=48):
            needs_confirmation = True

    allowed_next = STATUS_TRANSITIONS.get(event.status, [])

    return render_template(
        "bookings/view.html", event=event,
        event_lines=event.service_lines.all(), payments=event.payments.order_by(Payment.payment_date.desc()).all(),
        total_paid=total_paid, deposit=deposit, total_refunded=total_refunded,
        total_revenue=total_revenue, total_costs=total_costs, profit=profit,
        needs_confirmation=needs_confirmation, statuses=allowed_next,
        event_expenses=event.expenses.order_by(Expense.expense_date.desc()).all(),
        total_expenses=float(total_expenses), adjusted_profit=adjusted_profit,
        today_str=date.today().isoformat(),
    )


# ─── Add Payment ─────────────────────────────────────────────────────
@bp.route("/evenement/<int:event_id>/paiement", methods=["POST"])
@login_required
def add_payment(event_id):
    data = request.form
    try:
        event = Event.query.get_or_404(event_id)
        amount = data.get("amount", 0, type=float)

        if amount <= 0:
            flash("Montant invalide", "danger")
            return redirect(url_for("bookings.event_detail", event_id=event_id))
        if event.status == "annulé":
            flash("Impossible d'encaisser sur un événement annulé", "danger")
            return redirect(url_for("bookings.event_detail", event_id=event_id))

        remaining = event.remaining
        if remaining <= 0:
            flash("Cet événement est déjà soldé!", "warning")
            return redirect(url_for("bookings.event_detail", event_id=event_id))
        if amount > remaining:
            flash(f"Le montant ({amount:,.0f} DA) dépasse le reste ({remaining:,.0f} DA).", "danger")
            return redirect(url_for("bookings.event_detail", event_id=event_id))

        payment = Payment(
            event_id=event_id, amount=amount,
            method=data.get("method", "espèces"),
            payment_type=data.get("payment_type", "dépôt").lower(),
            reference=data.get("reference", "").strip(),
            notes=data.get("notes", "").strip(),
        )
        db.session.add(payment)

        new_total = float(event.total_paid) + amount
        if new_total >= float(event.total_amount) and event.status == "en attente":
            event.status = "confirmé"
            logger.info("Event %d auto-confirmed (fully paid)", event_id)

        db.session.commit()
        flash("Paiement enregistré — soldé! ✓" if new_total >= event.total_amount
              else f"Paiement enregistré! Reste: {event.total_amount - new_total:,.0f} DA", "success")
    except Exception:
        db.session.rollback()
        logger.exception("Failed to add payment for event %s", event_id)
        flash("Erreur lors de l'enregistrement du paiement.", "danger")

    next_url = data.get("next") or request.args.get("next")
    if next_url:
        parsed = urlparse(next_url)
        if not parsed.netloc or parsed.netloc == request.host:
            return redirect(next_url)
    return redirect(url_for("bookings.event_detail", event_id=event_id))


# ─── Refund Payment ──────────────────────────────────────────────────
@bp.route("/evenement/<int:event_id>/paiement/<int:payment_id>/rembourser", methods=["POST"])
@login_required
def refund_payment(event_id, payment_id):
    try:
        payment = Payment.query.get_or_404(payment_id)
        if payment.is_refunded:
            flash("Ce paiement a déjà été remboursé", "warning")
        else:
            reason = request.form.get("refund_reason", "").strip()
            payment.is_refunded = 1
            payment.notes = (payment.notes or "") + f" [REMBOURSÉ: {reason}]" if reason else " [REMBOURSÉ]"
            db.session.commit()
            flash("Paiement marqué comme remboursé", "success")
    except Exception:
        db.session.rollback()
        flash("Erreur lors du remboursement.", "danger")
    return redirect(url_for("bookings.event_detail", event_id=event_id))


# ─── Update Status ───────────────────────────────────────────────────
@bp.route("/evenement/<int:event_id>/statut", methods=["POST"])
@login_required
def update_event_status(event_id):
    try:
        event = Event.query.get_or_404(event_id)
        new_status = request.form.get("status", "")

        if new_status not in ALL_STATUSES:
            flash("Statut invalide", "danger")
            return redirect(url_for("bookings.event_detail", event_id=event_id))

        if event.status in STATUS_TRANSITIONS and new_status not in STATUS_TRANSITIONS.get(event.status, []):
            flash(f"⚠️ Transition non autorisée: '{event.status}' → '{new_status}'", "danger")
            return redirect(url_for("bookings.event_detail", event_id=event_id))

        if new_status == "changé de date":
            new_date = request.form.get("new_date", "").strip()
            if new_date:
                # One-event-per-day enforcement
                date_conflict = Event.query.filter(
                    Event.event_date == new_date,
                    Event.id != event_id,
                ).first()
                if date_conflict:
                    flash("Cette date est déjà réservée", "danger")
                    return redirect(url_for("bookings.event_detail", event_id=event_id))
                event.event_date = new_date
                flash(f"Date changée à {new_date}.", "success")

        event.status = new_status
        event.updated_at = datetime.now()
        db.session.commit()
        flash({"confirmé": "Événement confirmé!", "terminé": "Marqué terminé", "annulé": "Événement annulé"}.get(new_status, "Statut mis à jour"), "success")
    except Exception:
        db.session.rollback()
        flash("Erreur lors de la mise à jour du statut.", "danger")
    return redirect(url_for("bookings.event_detail", event_id=event_id))


# ─── Delete Event ────────────────────────────────────────────────────
@bp.route("/evenement/<int:event_id>/supprimer", methods=["POST"])
@login_required
def delete_event(event_id):
    if not _is_admin():
        flash("Seuls les administrateurs peuvent supprimer", "danger")
        return redirect(url_for("bookings.event_detail", event_id=event_id))
    try:
        event = Event.query.get_or_404(event_id)
        db.session.delete(event)  # cascade handles lines, payments, expenses
        db.session.commit()
        flash("Événement supprimé", "success")
    except Exception:
        db.session.rollback()
        flash("Erreur lors de la suppression.", "danger")
    return redirect(url_for("finance.dashboard"))


# ─── Event Expense ───────────────────────────────────────────────────
@bp.route("/evenement/<int:event_id>/depense", methods=["POST"])
@login_required
def add_event_expense(event_id):
    try:
        expense_date = request.form.get("expense_date", date.today().isoformat())
        added = 0
        for cat_key, cat_name, default in [("serveurs", "Serveurs", 15000), ("nettoyeurs", "Nettoyeurs", 8000), ("securite", "Sécurité", 10000)]:
            if request.form.get(f"cat_{cat_key}"):
                amount = request.form.get(f"amount_{cat_key}", default, type=float)
                if amount > 0:
                    db.session.add(Expense(event_id=event_id, category=cat_name, description=cat_name, amount=amount, expense_date=expense_date))
                    added += 1
        if request.form.get("cat_autre"):
            name = request.form.get("autre_name", "").strip() or "Autre"
            amount = request.form.get("amount_autre", 0, type=float)
            if amount > 0:
                db.session.add(Expense(event_id=event_id, category="Autre", description=f"Autre: {name}", amount=amount, expense_date=expense_date))
                added += 1
        if added:
            db.session.commit()
            flash(f"{added} dépense(s) enregistrée(s)!", "success")
        else:
            flash("Sélectionnez au moins une catégorie", "warning")
    except Exception:
        db.session.rollback()
        flash("Erreur lors de l'enregistrement.", "danger")
    return redirect(url_for("bookings.event_detail", event_id=event_id))


# ─── Contract PDF ────────────────────────────────────────────────────
@bp.route("/evenement/<int:event_id>/contrat")
@login_required
def generate_contract(event_id):
    from contract_generator import generate_contract_pdf
    try:
        event = Event.query.get_or_404(event_id)
        payments = Payment.query.filter_by(event_id=event_id, is_refunded=0).order_by(Payment.payment_date.desc()).all()
        total_paid = event.total_paid
        lines = event.service_lines.all()

        # PDF generators expect dict-like objects — convert ORM to dict
        pdf_bytes = generate_contract_pdf(
            _event_to_dict(event), [_payment_to_dict(p) for p in payments],
            total_paid, [_line_to_dict(ln) for ln in lines]
        )
        resp = make_response(pdf_bytes)
        resp.headers["Content-Type"] = "application/pdf"
        resp.headers["Content-Disposition"] = f"inline; filename=contrat_{event.title.replace(' ', '_')[:30]}_{event_id}.pdf"
        return resp
    except Exception as e:
        logger.error("Contract error: %s", e)
        flash(f"Erreur: {str(e)}", "danger")
        return redirect(url_for("bookings.event_detail", event_id=event_id))


# ─── Receipt ─────────────────────────────────────────────────────────
@bp.route("/evenement/<int:event_id>/recu/<int:payment_id>")
@login_required
def generate_receipt(event_id, payment_id):
    from receipt_generator import generate_receipt_pdf
    try:
        event = Event.query.get_or_404(event_id)
        payment = Payment.query.get_or_404(payment_id)
        if payment.event_id != event_id:
            flash("Paiement introuvable pour cet événement", "danger")
            return redirect(url_for("bookings.event_detail", event_id=event_id))
        date_str = str(payment.payment_date)[:19]
        total_before = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
            Payment.event_id == event_id, Payment.payment_date < date_str, Payment.is_refunded == 0
        ).scalar()
        total_after = float(total_before) + float(payment.amount)
        remaining = round(float(event.total_amount) - total_after, 2)
        receipt_no = f"{date_str[:4]}-{payment_id:04d}"

        pdf_bytes = generate_receipt_pdf(
            _event_to_dict(event), _payment_to_dict(payment),
            total_before, total_after, remaining, receipt_no
        )
        resp = make_response(pdf_bytes)
        resp.headers["Content-Type"] = "application/pdf"
        resp.headers["Content-Disposition"] = f"inline; filename=recu_{payment_id}.pdf"
        return resp
    except Exception as e:
        logger.error("Receipt error: %s", e)
        flash(f"Erreur: {str(e)}", "danger")
        return redirect(url_for("bookings.event_detail", event_id=event_id))


# ─── Quick Payment ───────────────────────────────────────────────────
@bp.route("/paiement-rapide", methods=["GET", "POST"])
@login_required
def quick_payment():
    search = request.args.get("q", "").strip()
    selected_client_id = request.args.get("client_id", type=int)
    selected_event_id = request.args.get("event_id", type=int)

    clients = []
    if search:
        clients = Client.query.filter(
            or_(Client.name.ilike(f"%{search}%"), Client.phone.ilike(f"%{search}%"))
        ).order_by(Client.name).limit(20).all()

    selected_client = db.session.get(Client, selected_client_id) if selected_client_id else None
    client_events = []
    if selected_client:
        client_events = Event.query.filter(
            Event.client_id == selected_client_id,
            Event.status.notin_(["annulé", "terminé"])
        ).order_by(Event.event_date).all()

    selected_event = db.session.get(Event, selected_event_id) if selected_event_id else None
    event_payments = []
    event_financials = None
    if selected_event:
        event_payments = Payment.query.filter_by(event_id=selected_event_id).order_by(Payment.payment_date.desc()).all()
        tp = selected_event.total_paid
        event_financials = {
            "total": selected_event.total_amount,
            "paid": tp,
            "remaining": selected_event.remaining,
            "refunded": db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
                Payment.event_id == selected_event_id, Payment.is_refunded == 1).scalar(),
        }

    return render_template(
        "bookings/quick_payment.html",
        search=search, clients=clients,
        selected_client_id=selected_client_id, selected_client=selected_client,
        client_events=client_events, selected_event_id=selected_event_id,
        selected_event=selected_event, event_payments=event_payments,
        event_financials=event_financials, today_str=date.today().isoformat(),
    )


# ─── API ─────────────────────────────────────────────────────────────
@bp.route("/api/calendar-events")
@login_required
def api_calendar_events():
    include_cancelled = request.args.get("include_cancelled", "").lower() == "true"

    # Support both FullCalendar's start/end and manual year/month params
    start_param = request.args.get("start", "")
    end_param = request.args.get("end", "")

    if start_param and end_param:
        # FullCalendar sends start/end as ISO dates
        first = start_param[:10]
        last = end_param[:10]
    else:
        year = request.args.get("year", date.today().year, type=int)
        month = request.args.get("month", date.today().month, type=int)
        first = f"{year}-{month:02d}-01"
        last = f"{year + 1}-01-01" if month == 12 else f"{year}-{month + 1:02d}-01"

    q = Event.query.join(Client).filter(
        Event.event_date >= first, Event.event_date < last
    )
    if not include_cancelled:
        q = q.filter(Event.status != "annulé")
    events = q.order_by(Event.event_date).all()

    colors = {
        "confirmé": "#06d6a0",
        "en attente": "#ffd166",
        "annulé": "#ef476f",
        "changé de date": "#118ab2",
        "terminé": "#8d99ae",
    }
    return jsonify([{
        "id": e.id, "title": f"{e.title} — {e.time_slot or ''}",
        "start": str(e.event_date)[:10] if e.event_date else None,
        "url": url_for("bookings.event_detail", event_id=e.id),
        "backgroundColor": colors.get(e.status, "#6C63FF"),
        "borderColor": colors.get(e.status, "#6C63FF"),
        "extendedProps": {
            "status": e.status,
            "client_name": e.client.name,
            "venue_name": e.venue.name,
            "venue2_name": e.venue2.name if e.venue2 else "",
        },
    } for e in events])


# ─── Dict converters (for PDF generators that expect dicts) ──────────
def _event_to_dict(e):
    return {c.name: getattr(e, c.name) for c in e.__table__.columns} | {
        "client_name": e.client.name, "phone": e.client.phone, "phone2": e.client.phone2,
        "email": e.client.email, "address": e.client.address,
        "venue_name": e.venue.name, "capacity_men": e.venue.capacity_men,
        "capacity_women": e.venue.capacity_women,
        "venue2_name": e.venue2.name if e.venue2 else "",
    }

def _payment_to_dict(p):
    return {c.name: getattr(p, c.name) for c in p.__table__.columns}

def _line_to_dict(ln):
    return {c.name: getattr(ln, c.name) for c in ln.__table__.columns}

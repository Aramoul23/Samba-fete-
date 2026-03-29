"""Samba Fête — Booking routes.

All event/booking CRUD, calendar, payments, status transitions,
contracts, receipts, and the quick-payment page.
"""
import calendar as _calendar
import logging
from datetime import date, datetime, timedelta

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

from app.auth.decorators import admin_required
from app.db import get_db_connection
from app.bookings.helpers import (
    EVENT_STATUSES,
    EVENT_TYPES,
    MONTH_NAMES_FR,
    PAYMENT_METHODS,
    PREDEFINED_NAMES,
    TIME_SLOTS,
    check_pending_events,
    insert_service_lines,
    validate_event_date,
)

logger = logging.getLogger(__name__)

bp = Blueprint("bookings", __name__, template_folder="../templates")

# ─── Database error helper ───────────────────────────────────────────
try:
    import psycopg2
    import sqlite3
    DatabaseError = (sqlite3.Error, psycopg2.Error)
except ImportError:
    import sqlite3
    DatabaseError = (sqlite3.Error,)


# ─── Role helpers (lightweight, avoid circular imports) ───────────────
def _is_admin():
    return current_user.is_authenticated and current_user.role == "admin"


# ─── Calendar ────────────────────────────────────────────────────────
@bp.route("/calendrier")
@login_required
def calendar_view():
    """Affiche le calendrier des événements."""
    db = get_db_connection()
    year = request.args.get("year", date.today().year, type=int)
    month = request.args.get("month", date.today().month, type=int)

    first = f"{year}-{month:02d}-01"
    last = f"{year + 1}-01-01" if month == 12 else f"{year}-{month + 1:02d}-01"

    venue_filter = request.args.get("venue", type=int)

    query = (
        "SELECT id, event_date, time_slot, title, status FROM events "
        "WHERE event_date >= ? AND event_date < ? AND status != 'annulé'"
    )
    params = [first, last]

    if venue_filter:
        query += " AND (venue_id = ? OR venue_id2 = ?)"
        params.extend([venue_filter, venue_filter])

    query += " ORDER BY event_date"
    booked = db.execute(query, params).fetchall()

    booked_dict = {}
    for b in booked:
        booked_dict.setdefault(b["event_date"], []).append(b)

    weeks = _calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)
    venues = db.execute("SELECT * FROM venues WHERE is_active=1").fetchall()

    return render_template(
        "bookings/calendar.html",
        year=year,
        month=month,
        month_name=MONTH_NAMES_FR[month],
        weeks=weeks,
        booked_dict=booked_dict,
        today_str=date.today().isoformat(),
        venues=venues,
        time_slots=TIME_SLOTS,
        venue_filter=venue_filter or "",
        pending_needs_attention=check_pending_events(db),
    )


# ─── Event List ──────────────────────────────────────────────────────
@bp.route("/evenements")
@login_required
def event_list():
    """Liste filtrable des événements."""
    db = get_db_connection()
    status_filter = request.args.get("status", "")
    search = request.args.get("q", "").strip()

    query = (
        "SELECT e.*, c.name as client_name, v.name as venue_name, "
        "COALESCE((SELECT SUM(p.amount) FROM payments p "
        "  WHERE p.event_id=e.id AND p.is_refunded=0), 0) as total_paid "
        "FROM events e "
        "JOIN clients c ON e.client_id=c.id "
        "JOIN venues v ON e.venue_id=v.id WHERE 1=1"
    )
    params = []

    if status_filter:
        query += " AND e.status=?"
        params.append(status_filter)
    if search:
        query += " AND (e.title LIKE ? OR c.name LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])

    query += " ORDER BY e.event_date DESC"
    events = db.execute(query, params).fetchall()

    return render_template(
        "bookings/list.html",
        events=events,
        statuses=EVENT_STATUSES,
        status_filter=status_filter,
        search=search,
    )


# ─── Create / Edit Event ────────────────────────────────────────────
@bp.route("/evenement/nouveau", methods=["GET", "POST"])
@bp.route("/evenement/<int:event_id>/modifier", methods=["GET", "POST"])
@login_required
def event_form(event_id=None):
    """Formulaire de création ou modification d'un événement."""
    db = get_db_connection()
    event = None
    client = None
    event_lines = []
    custom_lines = []

    if event_id:
        event = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if not event:
            flash("Événement introuvable", "danger")
            return redirect(url_for("finance.dashboard"))
        client = db.execute(
            "SELECT * FROM clients WHERE id=?", (event["client_id"],)
        ).fetchone()
        all_lines = db.execute(
            "SELECT * FROM event_lines WHERE event_id=?", (event_id,)
        ).fetchall()
        for line in all_lines:
            if line["description"] in PREDEFINED_NAMES:
                event_lines.append(line)
            else:
                custom_lines.append(line)

    venues = db.execute("SELECT * FROM venues WHERE is_active=1").fetchall()

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
        event_date = data.get("event_date")
        time_slot = data.get("time_slot", "Soirée")
        guests_men = data.get("guests_men", 0, type=int)
        guests_women = data.get("guests_women", 0, type=int)
        status = (
            data.get("status", "en attente")
            if not event_id
            else data.get("status", event["status"])
        )
        notes = data.get("notes", "").strip()
        total_amount = data.get("total_amount", 0, type=float)
        deposit_required = data.get("deposit_required", 0, type=float)

        # ── Validation ───────────────────────────────────────────────
        errors = []
        if not title:
            errors.append("Le titre est requis")
        if not client_name:
            errors.append("Le nom du client est requis")
        if not client_phone:
            errors.append("Le téléphone est requis")
        if not event_date:
            errors.append("La date est requise")
        if not venue_id:
            errors.append("Le lieu est requis")
        errors.extend(validate_event_date(db, event_date, event_id or 0))

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "bookings/create.html" if not event_id else "bookings/edit.html",
                event=event, client=client,
                event_lines=event_lines, custom_lines=custom_lines,
                venues=venues, time_slots=TIME_SLOTS,
                event_types=EVENT_TYPES, statuses=EVENT_STATUSES,
                event_id=event_id,
            )

        # ── Upsert client ────────────────────────────────────────────
        if client:
            db.execute(
                "UPDATE clients SET name=?, phone=?, phone2=?, email=?, address=? WHERE id=?",
                (client_name, client_phone, client_phone2, client_email,
                 client_address, client["id"]),
            )
            client_id = client["id"]
        else:
            cur = db.execute(
                "INSERT INTO clients (name, phone, phone2, email, address) VALUES (?,?,?,?,?)",
                (client_name, client_phone, client_phone2, client_email, client_address),
            )
            client_id = cur.lastrowid

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # ── Upsert event ─────────────────────────────────────────────
        if event:
            db.execute(
                "UPDATE events SET title=?, client_id=?, venue_id=?, venue_id2=?, "
                "event_type=?, event_date=?, time_slot=?, guests_men=?, guests_women=?, "
                "status=?, notes=?, total_amount=?, deposit_required=?, updated_at=? "
                "WHERE id=?",
                (title, client_id, venue_id, venue_id2, event_type, event_date,
                 time_slot, guests_men, guests_women, status, notes,
                 total_amount, deposit_required, now_str, event_id),
            )
            db.execute("DELETE FROM event_lines WHERE event_id=?", (event_id,))
        else:
            cur = db.execute(
                "INSERT INTO events (title, client_id, venue_id, venue_id2, "
                "event_type, event_date, time_slot, guests_men, guests_women, "
                "status, notes, total_amount, deposit_required, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (title, client_id, venue_id, venue_id2, event_type, event_date,
                 time_slot, guests_men, guests_women, status, notes,
                 total_amount, deposit_required, now_str, now_str),
            )
            event_id = cur.lastrowid

        # ── Auto-create deposit payment ──────────────────────────────
        if deposit_required and deposit_required > 0:
            db.execute(
                "INSERT INTO payments (event_id, amount, payment_type, method, payment_date) "
                "VALUES (?, ?, 'avance', 'espèces', ?)",
                (event_id, deposit_required, now_str),
            )

        # ── Service lines (DRY helper) ───────────────────────────────
        insert_service_lines(db, event_id, data)

        db.commit()
        flash("Événement créé avec succès! Vous pouvez maintenant encaisser un paiement.", "success")
        return redirect(url_for("bookings.event_detail", event_id=event_id))

    template = "bookings/create.html" if not event_id else "bookings/edit.html"
    return render_template(
        template, event=event, client=client,
        event_lines=event_lines, custom_lines=custom_lines,
        venues=venues, time_slots=TIME_SLOTS,
        event_types=EVENT_TYPES, statuses=EVENT_STATUSES,
        event_id=event_id,
    )


# ─── Event Detail ────────────────────────────────────────────────────
@bp.route("/evenement/<int:event_id>")
@login_required
def event_detail(event_id):
    """Détails d'un événement avec finances."""
    db = get_db_connection()
    event = db.execute(
        "SELECT e.*, c.name as client_name, c.id as client_id, c.phone, "
        "c.phone2, c.email, c.address, "
        "v.name as venue_name, v.capacity_men, v.capacity_women, "
        "v2.name as venue2_name FROM events e "
        "JOIN clients c ON e.client_id=c.id "
        "JOIN venues v ON e.venue_id=v.id "
        "LEFT JOIN venues v2 ON e.venue_id2=v2.id "
        "WHERE e.id=?",
        (event_id,),
    ).fetchone()

    if not event:
        flash("Événement introuvable", "danger")
        return redirect(url_for("finance.dashboard"))

    event_lines = db.execute(
        "SELECT * FROM event_lines WHERE event_id=?", (event_id,)
    ).fetchall()
    payments = db.execute(
        "SELECT * FROM payments WHERE event_id=? ORDER BY payment_date DESC",
        (event_id,),
    ).fetchall()

    total_paid = db.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM payments "
        "WHERE event_id=? AND is_refunded=0", (event_id,),
    ).fetchone()["s"]

    total_refunded = db.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM payments "
        "WHERE event_id=? AND is_refunded=1", (event_id,),
    ).fetchone()["s"]

    deposit = db.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM payments "
        "WHERE event_id=? AND payment_type='dépôt' AND is_refunded=0",
        (event_id,),
    ).fetchone()["s"]

    total_revenue = db.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM event_lines "
        "WHERE event_id=? AND is_cost=0", (event_id,),
    ).fetchone()["s"]

    total_costs = db.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM event_lines "
        "WHERE event_id=? AND is_cost=1", (event_id,),
    ).fetchone()["s"]

    profit = float(total_revenue) - float(total_costs)

    event_expenses = db.execute(
        "SELECT * FROM expenses WHERE event_id=? ORDER BY expense_date DESC",
        (event_id,),
    ).fetchall()
    total_expenses = db.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM expenses WHERE event_id=?",
        (event_id,),
    ).fetchone()["s"]

    adjusted_profit = round(profit - float(total_expenses), 2)

    needs_confirmation = False
    if event["status"] == "en attente":
        try:
            created_at = event["created_at"]
            if created_at:
                if isinstance(created_at, str):
                    created = datetime.strptime(created_at[:19], "%Y-%m-%d %H:%M:%S")
                else:
                    created = created_at
                if (datetime.now() - created) > timedelta(hours=48):
                    needs_confirmation = True
        except (ValueError, TypeError, KeyError):
            pass

    return render_template(
        "bookings/view.html",
        event=event, event_lines=event_lines, payments=payments,
        total_paid=total_paid, deposit=deposit,
        total_refunded=total_refunded,
        total_revenue=total_revenue, total_costs=total_costs,
        profit=profit, needs_confirmation=needs_confirmation,
        statuses=EVENT_STATUSES,
        event_expenses=event_expenses,
        total_expenses=float(total_expenses),
        adjusted_profit=adjusted_profit,
        today_str=date.today().isoformat(),
    )


# ─── Add Payment ─────────────────────────────────────────────────────
@bp.route("/evenement/<int:event_id>/paiement", methods=["POST"])
@login_required
def add_payment(event_id):
    """Enregistre un paiement avec validation anti-dépassement."""
    data = request.form
    try:
        db = get_db_connection()
        amount = data.get("amount", 0, type=float)
        method = data.get("method", "espèces")
        payment_type = data.get("payment_type", "dépôt").lower()
        reference = data.get("reference", "").strip()
        notes = data.get("notes", "").strip()

        if amount <= 0:
            flash("Montant invalide", "danger")
            return redirect(url_for("bookings.event_detail", event_id=event_id))

        event = db.execute(
            "SELECT total_amount, status FROM events WHERE id=?", (event_id,)
        ).fetchone()
        if not event:
            flash("Événement introuvable", "danger")
            return redirect(url_for("finance.dashboard"))
        if event["status"] == "annulé":
            flash("Impossible d'encaisser sur un événement annulé", "danger")
            return redirect(url_for("bookings.event_detail", event_id=event_id))

        total_paid = db.execute(
            "SELECT COALESCE(SUM(amount), 0) as s FROM payments "
            "WHERE event_id=? AND is_refunded=0", (event_id,),
        ).fetchone()["s"]
        remaining = float(event["total_amount"]) - float(total_paid)

        if remaining <= 0:
            flash("Cet événement est déjà soldé!", "warning")
            return redirect(url_for("bookings.event_detail", event_id=event_id))
        if amount > remaining:
            flash(
                f"Le montant ({amount:,.0f} DA) dépasse le reste à payer "
                f"({remaining:,.0f} DA). Maximum autorisé: {remaining:,.0f} DA.",
                "danger",
            )
            return redirect(url_for("bookings.event_detail", event_id=event_id))

        db.execute(
            "INSERT INTO payments (event_id, amount, method, payment_type, reference, notes) "
            "VALUES (?,?,?,?,?,?)",
            (event_id, amount, method, payment_type, reference, notes),
        )

        new_total_paid = float(total_paid) + amount
        if new_total_paid >= float(event["total_amount"]):
            if event["status"] == "en attente":
                db.execute("UPDATE events SET status='confirmé' WHERE id=?", (event_id,))
                logger.info("Event %d auto-confirmed (fully paid)", event_id)

        db.commit()
        logger.info("Payment added: %.2f DA for event %d", amount, event_id)

        if new_total_paid >= float(event["total_amount"]):
            flash("Paiement enregistré — événement soldé! ✓", "success")
        else:
            reste = float(event["total_amount"]) - new_total_paid
            flash(f"Paiement enregistré! Reste: {reste:,.0f} DA", "success")

    except (DatabaseError, ValueError):
        db.rollback()
        logger.exception("Failed to add payment for event %s", event_id)
        flash("Une erreur est survenue lors de l'enregistrement du paiement.", "danger")

    next_url = data.get("next") or request.args.get("next")
    if next_url:
        from urllib.parse import urlparse
        parsed = urlparse(next_url)
        if not parsed.netloc or parsed.netloc == request.host:
            return redirect(next_url)
    return redirect(url_for("bookings.event_detail", event_id=event_id))


# ─── Refund Payment ──────────────────────────────────────────────────
@bp.route("/evenement/<int:event_id>/paiement/<int:payment_id>/rembourser", methods=["POST"])
@login_required
def refund_payment(event_id, payment_id):
    """Marquer un paiement comme remboursé (piste d'audit — jamais supprimé)."""
    try:
        db = get_db_connection()
        reason = request.form.get("refund_reason", "").strip()

        payment = db.execute(
            "SELECT * FROM payments WHERE id=? AND event_id=?", (payment_id, event_id)
        ).fetchone()

        if not payment:
            flash("Paiement introuvable", "danger")
        elif payment["is_refunded"]:
            flash("Ce paiement a déjà été remboursé", "warning")
        else:
            existing_notes = payment.get("notes", "") or ""
            refund_note = f" [REMBOURSÉ: {reason}]" if reason else " [REMBOURSÉ]"
            db.execute(
                "UPDATE payments SET is_refunded=1, notes=? WHERE id=?",
                (existing_notes + refund_note, payment_id),
            )
            db.commit()
            flash("Paiement marqué comme remboursé", "success")
    except DatabaseError:
        db.rollback()
        logger.exception("Failed to refund payment %s for event %s", payment_id, event_id)
        flash("Une erreur est survenue lors du remboursement.", "danger")
    return redirect(url_for("bookings.event_detail", event_id=event_id))


# ─── Update Status ───────────────────────────────────────────────────
@bp.route("/evenement/<int:event_id>/statut", methods=["POST"])
@login_required
def update_event_status(event_id):
    """Mise à jour du statut avec validation des transitions."""
    try:
        db = get_db_connection()
        new_status = request.form.get("status", "")
        new_date = request.form.get("new_date", "").strip()

        if new_status not in EVENT_STATUSES:
            flash("Statut invalide", "danger")
            return redirect(url_for("bookings.event_detail", event_id=event_id))

        current_event = db.execute(
            "SELECT status FROM events WHERE id = ?", (event_id,)
        ).fetchone()
        if not current_event:
            flash("Événement introuvable", "danger")
            return redirect(url_for("bookings.event_detail", event_id=event_id))

        current_status = current_event["status"]
        allowed_transitions = {
            "confirmé": ["annulé", "changé de date"],
            "en attente": ["confirmé", "annulé"],
            "annulé": [],
            "terminé": [],
            "changé de date": ["confirmé", "annulé"],
        }

        if (current_status in allowed_transitions
                and new_status not in allowed_transitions.get(current_status, [])):
            flash(
                f"⚠️ Transition non autorisée: Impossible de passer de "
                f"'{current_status}' à '{new_status}'.",
                "danger",
            )
            return redirect(url_for("bookings.event_detail", event_id=event_id))

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if new_status == "changé de date" and new_date:
            db.execute(
                "UPDATE events SET status=?, event_date=?, updated_at=? WHERE id=?",
                (new_status, new_date, now_str, event_id),
            )
            flash(f"Date changée à {new_date}. Statut mis à jour.", "success")
        else:
            db.execute(
                "UPDATE events SET status=?, updated_at=? WHERE id=?",
                (new_status, now_str, event_id),
            )
            msgs = {
                "confirmé": "Événement confirmé!",
                "en attente": "Statut remis à 'en attente'",
                "terminé": "Événement marqué comme terminé",
                "annulé": "Événement annulé",
            }
            flash(msgs.get(new_status, "Statut mis à jour"), "success")

        db.commit()
    except DatabaseError:
        db.rollback()
        logger.exception("Failed to update status for event %s", event_id)
        flash("Une erreur est survenue lors de la mise à jour du statut.", "danger")
    return redirect(url_for("bookings.event_detail", event_id=event_id))


# ─── Delete Event ────────────────────────────────────────────────────
@bp.route("/evenement/<int:event_id>/supprimer", methods=["POST"])
@login_required
def delete_event(event_id):
    """Supprime un événement et toutes ses données (admin uniquement)."""
    if not _is_admin():
        flash("Seuls les administrateurs peuvent supprimer des événements", "danger")
        return redirect(url_for("bookings.event_detail", event_id=event_id))
    try:
        db = get_db_connection()
        db.execute("DELETE FROM event_lines WHERE event_id=?", (event_id,))
        db.execute("DELETE FROM payments WHERE event_id=?", (event_id,))
        db.execute("DELETE FROM expenses WHERE event_id=?", (event_id,))
        db.execute("DELETE FROM events WHERE id=?", (event_id,))
        db.commit()
        logger.info("Event deleted: %d", event_id)
        flash("Événement supprimé", "success")
    except DatabaseError:
        db.rollback()
        logger.exception("Failed to delete event %s", event_id)
        flash("Une erreur est survenue lors de la suppression.", "danger")
    return redirect(url_for("finance.dashboard"))


# ─── Event Expense ───────────────────────────────────────────────────
@bp.route("/evenement/<int:event_id>/depense", methods=["POST"])
@login_required
def add_event_expense(event_id):
    """Ajoute des dépenses liées à un événement (multi-catégories)."""
    try:
        db = get_db_connection()
        expense_date = request.form.get("expense_date", date.today().isoformat())
        categories_added = 0

        for cat_key, cat_name, default_price in [
            ("serveurs", "Serveurs", 15000),
            ("nettoyeurs", "Nettoyeurs", 8000),
            ("securite", "Sécurité", 10000),
        ]:
            if request.form.get(f"cat_{cat_key}"):
                amount = request.form.get(f"amount_{cat_key}", default_price, type=float)
                if amount > 0:
                    db.execute(
                        "INSERT INTO expenses (expense_date, category, description, "
                        "amount, event_id, method) VALUES (?, ?, ?, ?, ?, ?)",
                        (expense_date, cat_name, cat_name, amount, event_id, "espèces"),
                    )
                    categories_added += 1

        if request.form.get("cat_autre"):
            autre_name = request.form.get("autre_name", "").strip() or "Autre"
            autre_amount = request.form.get("amount_autre", 0, type=float)
            if autre_amount > 0:
                db.execute(
                    "INSERT INTO expenses (expense_date, category, description, "
                    "amount, event_id, method) VALUES (?, ?, ?, ?, ?, ?)",
                    (expense_date, "Autre", f"Autre: {autre_name}",
                     autre_amount, event_id, "espèces"),
                )
                categories_added += 1

        if categories_added > 0:
            db.commit()
            flash(f"{categories_added} dépense(s) enregistrée(s)!", "success")
        else:
            flash("Sélectionnez au moins une catégorie avec un montant", "warning")
    except (DatabaseError, ValueError):
        db.rollback()
        logger.exception("Failed to add expense for event %s", event_id)
        flash("Une erreur est survenue lors de l'enregistrement de la dépense.", "danger")
    return redirect(url_for("bookings.event_detail", event_id=event_id))


# ─── Contract PDF ────────────────────────────────────────────────────
@bp.route("/evenement/<int:event_id>/contrat")
@login_required
def generate_contract(event_id):
    """Génère le PDF du contrat."""
    from contract_generator import generate_contract_pdf
    try:
        db = get_db_connection()
        event = db.execute(
            "SELECT e.*, c.name as client_name, c.phone, c.phone2, c.email, c.address, "
            "v.name as venue_name, v.capacity_men, v.capacity_women, "
            "v2.name as venue2_name FROM events e "
            "JOIN clients c ON e.client_id=c.id "
            "JOIN venues v ON e.venue_id=v.id "
            "LEFT JOIN venues v2 ON e.venue_id2=v2.id "
            "WHERE e.id=?", (event_id,),
        ).fetchone()

        if not event:
            flash("Événement introuvable", "danger")
            return redirect(url_for("finance.dashboard"))

        payments = db.execute(
            "SELECT * FROM payments WHERE event_id=? AND is_refunded=0 "
            "ORDER BY payment_date DESC", (event_id,),
        ).fetchall()
        total_paid = db.execute(
            "SELECT COALESCE(SUM(amount),0) as s FROM payments "
            "WHERE event_id=? AND is_refunded=0", (event_id,),
        ).fetchone()["s"]
        event_lines = db.execute(
            "SELECT * FROM event_lines WHERE event_id=?", (event_id,),
        ).fetchall()

        pdf_bytes = generate_contract_pdf(event, payments, total_paid, event_lines)
        response = make_response(pdf_bytes)
        response.headers["Content-Type"] = "application/pdf"
        safe_title = event["title"].replace(" ", "_")[:30]
        response.headers["Content-Disposition"] = (
            f"inline; filename=contrat_{safe_title}_{event_id}.pdf"
        )
        return response
    except Exception as e:
        logger.error("Contract generation error: %s", e)
        flash(f"Erreur lors de la génération du contrat: {str(e)}", "danger")
        return redirect(url_for("bookings.event_detail", event_id=event_id))


# ─── Receipt ─────────────────────────────────────────────────────────
@bp.route("/evenement/<int:event_id>/recu/<int:payment_id>")
@login_required
def generate_receipt(event_id, payment_id):
    """Génère le PDF du reçu pour un paiement."""
    from receipt_generator import generate_receipt_pdf
    db = get_db_connection()
    event = db.execute(
        "SELECT e.*, c.name as client_name, c.phone, c.address, "
        "v.name as venue_name FROM events e "
        "JOIN clients c ON e.client_id=c.id "
        "JOIN venues v ON e.venue_id=v.id "
        "WHERE e.id=?", (event_id,),
    ).fetchone()

    if not event:
        flash("Événement introuvable", "danger")
        return redirect(url_for("finance.dashboard"))

    payment = db.execute(
        "SELECT * FROM payments WHERE id=? AND event_id=?", (payment_id, event_id)
    ).fetchone()
    if not payment:
        flash("Paiement introuvable", "danger")
        return redirect(url_for("bookings.event_detail", event_id=event_id))

    date_str = str(payment["payment_date"])[:19]
    total_paid_before = db.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM payments "
        "WHERE event_id=? AND payment_date < ? AND is_refunded=0",
        (event_id, date_str),
    ).fetchone()["s"]
    total_paid_after = float(total_paid_before) + float(payment["amount"])
    remaining = round(float(event["total_amount"]) - total_paid_after, 2)
    receipt_no = f"{date_str[:4]}-{payment_id:04d}"

    try:
        pdf_bytes = generate_receipt_pdf(
            event, payment, total_paid_before, total_paid_after, remaining, receipt_no
        )
        response = make_response(pdf_bytes)
        response.headers["Content-Type"] = "application/pdf"
        safe_title = event["client_name"].replace(" ", "_")[:20]
        response.headers["Content-Disposition"] = (
            f"inline; filename=recu_{safe_title}_{payment_id}.pdf"
        )
        return response
    except Exception as e:
        logger.error("Receipt generation error: %s", e)
        flash(f"Erreur lors de la génération du reçu: {str(e)}", "danger")
        return redirect(url_for("bookings.event_detail", event_id=event_id))


# ─── Quick Payment (Walk-In) ────────────────────────────────────────
@bp.route("/paiement-rapide", methods=["GET", "POST"])
@login_required
def quick_payment():
    """Paiement rapide : recherche client → voir événements → encaisser."""
    db = get_db_connection()
    search = request.args.get("q", "").strip()
    selected_client_id = request.args.get("client_id", type=int)
    selected_event_id = request.args.get("event_id", type=int)

    clients = []
    client_events = []
    selected_client = None
    selected_event = None
    event_payments = []
    event_financials = None

    if search:
        clients = db.execute(
            "SELECT c.*, "
            "(SELECT COUNT(*) FROM events WHERE client_id=c.id "
            "  AND status NOT IN ('annulé','terminé')) as active_events, "
            "(SELECT COALESCE(SUM(e.total_amount),0) FROM events e "
            "  WHERE e.client_id=c.id AND e.status NOT IN ('annulé','terminé')) as total_owed "
            "FROM clients c WHERE c.name LIKE ? OR c.phone LIKE ? "
            "ORDER BY c.name LIMIT 20",
            (f"%{search}%", f"%{search}%"),
        ).fetchall()

    if selected_client_id:
        selected_client = db.execute(
            "SELECT * FROM clients WHERE id=?", (selected_client_id,)
        ).fetchone()
        if selected_client:
            client_events = db.execute(
                "SELECT e.*, v.name as venue_name, "
                "COALESCE((SELECT SUM(p.amount) FROM payments p "
                "  WHERE p.event_id=e.id AND p.is_refunded=0), 0) as total_paid "
                "FROM events e JOIN venues v ON e.venue_id=v.id "
                "WHERE e.client_id=? AND e.status NOT IN ('annulé','terminé') "
                "ORDER BY e.event_date ASC",
                (selected_client_id,),
            ).fetchall()

    if selected_event_id:
        selected_event = db.execute(
            "SELECT e.*, c.name as client_name, c.phone, v.name as venue_name "
            "FROM events e JOIN clients c ON e.client_id=c.id "
            "JOIN venues v ON e.venue_id=v.id WHERE e.id=?",
            (selected_event_id,),
        ).fetchone()
        if selected_event:
            event_payments = db.execute(
                "SELECT * FROM payments WHERE event_id=? ORDER BY payment_date DESC",
                (selected_event_id,),
            ).fetchall()
            pay_stats = db.execute(
                "SELECT "
                "COALESCE(SUM(CASE WHEN is_refunded=0 THEN amount ELSE 0 END), 0) as tp, "
                "COALESCE(SUM(CASE WHEN is_refunded=1 THEN amount ELSE 0 END), 0) as tr "
                "FROM payments WHERE event_id=?",
                (selected_event_id,),
            ).fetchone()
            total_paid = float(pay_stats["tp"])
            event_total = float(selected_event["total_amount"])
            event_financials = {
                "total": event_total,
                "paid": total_paid,
                "remaining": round(event_total - total_paid, 2),
                "refunded": float(pay_stats["tr"]),
            }

    return render_template(
        "bookings/quick_payment.html",
        search=search, clients=clients,
        selected_client_id=selected_client_id,
        selected_client=selected_client,
        client_events=client_events,
        selected_event_id=selected_event_id,
        selected_event=selected_event,
        event_payments=event_payments,
        event_financials=event_financials,
        today_str=date.today().isoformat(),
    )


# ─── API: Calendar Events (JSON) ────────────────────────────────────
@bp.route("/api/calendar-events")
@login_required
def api_calendar_events():
    """Événements du calendrier au format JSON."""
    db = get_db_connection()
    year = request.args.get("year", date.today().year, type=int)
    month = request.args.get("month", date.today().month, type=int)

    first = f"{year}-{month:02d}-01"
    last = f"{year + 1}-01-01" if month == 12 else f"{year}-{month + 1:02d}-01"

    events = db.execute(
        "SELECT e.id, e.title, e.event_date, e.time_slot, e.status, "
        "c.name as client_name, v.name as venue_name, "
        "COALESCE(v2.name, '') as venue2_name "
        "FROM events e "
        "JOIN clients c ON e.client_id=c.id "
        "JOIN venues v ON e.venue_id=v.id "
        "LEFT JOIN venues v2 ON e.venue_id2=v2.id "
        "WHERE e.event_date >= ? AND e.event_date < ? AND e.status != 'annulé' "
        "ORDER BY e.event_date",
        (first, last),
    ).fetchall()

    return jsonify(events)

"""Samba Fête — Booking service.

Business logic for event CRUD, payments, status transitions.
Routes call these functions instead of doing raw DB work.
"""
import logging
import math
from datetime import datetime, date, timedelta

from sqlalchemy import func

from app.models import db, Event, Client, EventLine, Payment, Expense, AuditLog

logger = logging.getLogger(__name__)


def _audit(action, user=None, entity_type=None, entity_id=None, details=None):
    """Helper to create audit log entry."""
    try:
        AuditLog.log(action, user=user, entity_type=entity_type,
                     entity_id=entity_id, details=details)
    except Exception:
        pass  # Don't let audit failures break the main operation


class BookingService:
    """Encapsulates all booking/event business logic."""

    # ── Status transition rules ──────────────────────────────────────
    ALLOWED_TRANSITIONS = {
        "confirmé": ["annulé", "changé de date"],
        "en attente": ["confirmé", "annulé"],
        "annulé": [],
        "terminé": [],
        "changé de date": ["confirmé", "annulé"],
    }

    @staticmethod
    def validate_status_transition(current, new):
        """Check if a status transition is allowed. Returns error string or None."""
        if current not in BookingService.ALLOWED_TRANSITIONS:
            return None
        if new not in BookingService.ALLOWED_TRANSITIONS.get(current, []):
            return f"Transition non autorisée: '{current}' → '{new}'"
        return None

    @staticmethod
    def validate_date_conflict(event_date, exclude_id=0):
        """Check for double-bookings. Returns error list."""
        if not event_date:
            return []
        conflict = Event.query.filter(
            Event.event_date == event_date,
            Event.status.in_(["confirmé", "en attente"]),
            Event.id != (exclude_id or 0),
        ).first()
        if not conflict:
            return []
        label = f" ({conflict.venue.name})" if conflict.venue else ""
        if conflict.status == "confirmé":
            return [f"⛔ Date réservée: '{conflict.title}' le {event_date}{label}"]
        return [f"⚠️ '{conflict.title}' en attente pour le {event_date}{label}"]

    @staticmethod
    def create_event(data, client_id=None):
        """Create a new event with optional client creation. Returns (event, errors).

        NOTE: No auto-deposit payment is created. The deposit_required field is
        stored as a reference amount only. Users must explicitly record payments.
        """
        errors = []
        title = data.get("title", "").strip()
        if not title:
            errors.append("Le titre est requis")

        event_date = data.get("event_date")
        if not event_date:
            errors.append("La date est requise")

        venue_id = data.get("venue_id", type=int)
        if not venue_id:
            errors.append("Le lieu est requis")

        errors.extend(BookingService.validate_date_conflict(event_date))

        if errors:
            return None, errors

        # Upsert client
        if not client_id:
            client = Client(
                name=data.get("client_name", "").strip(),
                phone=data.get("client_phone", "").strip(),
                phone2=data.get("client_phone2", "").strip(),
                email=data.get("client_email", "").strip(),
                address=data.get("client_address", "").strip(),
            )
            db.session.add(client)
            db.session.flush()
            client_id = client.id

        now = datetime.now()
        event = Event(
            title=title, client_id=client_id,
            venue_id=venue_id, venue_id2=data.get("venue_id2", type=int),
            event_type=data.get("event_type", "Mariage"),
            event_date=event_date,
            time_slot=data.get("time_slot", "Soirée"),
            guests_men=data.get("guests_men", 0, type=int),
            guests_women=data.get("guests_women", 0, type=int),
            status="en attente",
            notes=data.get("notes", "").strip(),
            total_amount=data.get("total_amount", 0, type=float),
            deposit_required=data.get("deposit_required", 0, type=float),
            created_at=now, updated_at=now,
        )
        db.session.add(event)
        db.session.flush()

        _audit("event.create", entity_type="event", entity_id=event.id,
               details=f"title={title}, amount={event.total_amount}")
        db.session.commit()
        return event, []

    @staticmethod
    def add_payment(event_id, amount, method="espèces", payment_type="acompte",
                    reference="", notes="", payment_date=None):
        """Record a payment. Returns (payment, error_message).

        Uses pre-computed remaining to avoid stale-read race condition on
        auto-confirm: remaining is calculated BEFORE the payment is added
        to the session, so we can reliably check if this payment settles
        the balance.
        """
        # ── Validate amount ──────────────────────────────────────────
        if not isinstance(amount, (int, float)) or math.isnan(amount) or math.isinf(amount):
            return None, "Montant invalide — veuillez entrer un nombre valide"
        if amount <= 0:
            return None, "Montant invalide"

        event = Event.query.get_or_404(event_id)

        if event.status == "annulé":
            return None, "Impossible d'encaisser sur un événement annulé"

        # Get current paid total via a reliable DB aggregate (not the ORM property)
        current_paid = float(db.session.query(
            func.coalesce(func.sum(Payment.amount), 0)
        ).filter(
            Payment.event_id == event_id, Payment.is_refunded == 0
        ).scalar())

        remaining = round(float(event.total_amount) - current_paid, 2)
        if remaining <= 0:
            return None, "Cet événement est déjà soldé"
        if amount > remaining:
            return None, f"Le montant ({amount:,.0f} DA) dépasse le reste ({remaining:,.0f} DA)"

        # Calculate remaining AFTER this payment (before adding to session)
        remaining_after = round(remaining - amount, 2)

        payment = Payment(
            event_id=event_id, amount=amount, method=method,
            payment_type=payment_type, reference=reference, notes=notes,
            payment_date=payment_date or datetime.now(),
        )
        db.session.add(payment)

        # Auto-confirm when fully paid (using pre-computed value, not ORM property)
        if remaining_after <= 0 and event.status == "en attente":
            event.status = "confirmé"
            logger.info("Event %d auto-confirmed (fully paid)", event_id)

        _audit("payment.create", entity_type="payment", entity_id=payment.id,
               details=f"event_id={event_id}, amount={amount}, method={method}")
        db.session.commit()

        return payment, None

    @staticmethod
    def change_status(event_id, new_status, new_date=None):
        """Change event status with validation. Returns error or None."""
        event = Event.query.get_or_404(event_id)

        error = BookingService.validate_status_transition(event.status, new_status)
        if error:
            return error

        if new_status == "changé de date" and new_date:
            event.event_date = new_date

        event.status = new_status
        event.updated_at = datetime.now()
        _audit("event.status_change", entity_type="event", entity_id=event_id,
               details=f"from={event.status}, to={new_status}")
        db.session.commit()
        return None

    @staticmethod
    def delete_event(event_id):
        """Delete event and all related data via cascade. Returns error or None."""
        event = Event.query.get_or_404(event_id)
        try:
            _audit("event.delete", entity_type="event", entity_id=event_id,
                   details=f"title={event.title}, amount={event.total_amount}")
            db.session.delete(event)
            db.session.commit()
            return None
        except Exception as e:
            db.session.rollback()
            logger.exception("Failed to delete event %s", event_id)
            return str(e)

    @staticmethod
    def get_financials(event_id):
        """Get complete financial summary for an event."""
        revenue = db.session.query(func.coalesce(func.sum(EventLine.amount), 0)).filter(
            EventLine.event_id == event_id, EventLine.is_cost == 0).scalar()
        costs = db.session.query(func.coalesce(func.sum(EventLine.amount), 0)).filter(
            EventLine.event_id == event_id, EventLine.is_cost == 1).scalar()
        paid = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
            Payment.event_id == event_id, Payment.is_refunded == 0).scalar()
        refunded = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
            Payment.event_id == event_id, Payment.is_refunded == 1).scalar()
        expenses = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
            Expense.event_id == event_id).scalar()

        return {
            "revenue": float(revenue),
            "costs": float(costs),
            "profit": float(revenue) - float(costs),
            "paid": float(paid),
            "refunded": float(refunded),
            "expenses": float(expenses),
            "adjusted_profit": float(revenue) - float(costs) - float(expenses),
        }

    @staticmethod
    def get_pending_alerts():
        """Events 'en attente' for > 48h in next 30 days."""
        threshold = (datetime.now() - timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")
        future = (date.today() + timedelta(days=30)).isoformat()
        today = date.today().isoformat()
        return Event.query.filter(
            Event.status == "en attente",
            Event.event_date.between(today, future),
            Event.created_at < threshold,
        ).all()

"""Samba Fête — Unit tests for BookingService.

Tests business logic in isolation — no HTTP requests, just service calls.
"""
import datetime
import pytest
from app.services.booking_service import BookingService
from app.models import db, Event, Client, Payment, EventLine, Venue


# ══════════════════════════════════════════════════════════════════════
# Status Transitions
# ══════════════════════════════════════════════════════════════════════

class TestStatusTransitions:
    """Unit tests for status validation logic."""

    def test_valid_transitions(self):
        assert BookingService.validate_status_transition("en attente", "confirmé") is None
        assert BookingService.validate_status_transition("en attente", "annulé") is None
        assert BookingService.validate_status_transition("confirmé", "annulé") is None
        assert BookingService.validate_status_transition("confirmé", "changé de date") is None
        assert BookingService.validate_status_transition("changé de date", "confirmé") is None

    def test_invalid_transitions(self):
        assert BookingService.validate_status_transition("annulé", "confirmé") is not None
        assert BookingService.validate_status_transition("terminé", "confirmé") is not None
        assert BookingService.validate_status_transition("en attente", "terminé") is not None

    def test_error_message_format(self):
        err = BookingService.validate_status_transition("annulé", "confirmé")
        assert "non autorisée" in err
        assert "annulé" in err
        assert "confirmé" in err


# ══════════════════════════════════════════════════════════════════════
# Date Conflict Validation
# ══════════════════════════════════════════════════════════════════════

class TestDateConflict:
    """Unit tests for date conflict detection."""

    def test_no_conflict_on_empty_db(self, _db, app):
        with app.app_context():
            errors = BookingService.validate_date_conflict("2026-06-15")
            assert errors == []

    def test_conflict_with_confirmed_event(self, _db, app):
        with app.app_context():
            c = Client(name="Test", phone="123")
            db.session.add(c); db.session.flush()
            e = Event(title="Existing", client_id=c.id, venue_id=1,
                      event_type="Mariage", event_date="2026-06-15", time_slot="Soirée",
                      status="confirmé")
            db.session.add(e); db.session.commit()

            errors = BookingService.validate_date_conflict("2026-06-15")
            assert len(errors) == 1
            assert "réservée" in errors[0]

    def test_conflict_with_pending_event(self, _db, app):
        with app.app_context():
            c = Client(name="Test", phone="123")
            db.session.add(c); db.session.flush()
            e = Event(title="Pending", client_id=c.id, venue_id=1,
                      event_type="Mariage", event_date="2026-06-20", time_slot="Soirée",
                      status="en attente")
            db.session.add(e); db.session.commit()

            errors = BookingService.validate_date_conflict("2026-06-20")
            assert len(errors) == 1
            assert "attente" in errors[0]

    def test_no_conflict_with_cancelled_event(self, _db, app):
        with app.app_context():
            c = Client(name="Test", phone="123")
            db.session.add(c); db.session.flush()
            e = Event(title="Cancelled", client_id=c.id, venue_id=1,
                      event_type="Mariage", event_date="2026-06-25", time_slot="Soirée",
                      status="annulé")
            db.session.add(e); db.session.commit()

            errors = BookingService.validate_date_conflict("2026-06-25")
            assert errors == []

    def test_exclude_own_id(self, _db, app):
        with app.app_context():
            c = Client(name="Test", phone="123")
            db.session.add(c); db.session.flush()
            e = Event(title="Mine", client_id=c.id, venue_id=1,
                      event_type="Mariage", event_date="2026-07-01", time_slot="Soirée",
                      status="confirmé")
            db.session.add(e); db.session.flush()

            # Should not conflict with itself
            errors = BookingService.validate_date_conflict("2026-07-01", exclude_id=e.id)
            assert errors == []


# ══════════════════════════════════════════════════════════════════════
# Create Event
# ══════════════════════════════════════════════════════════════════════

class TestCreateEvent:
    """Unit tests for event creation."""

    def test_create_valid_event(self, _db, app):
        with app.app_context():
            data = {
                "title": "Test Wedding",
                "client_name": "Ahmed",
                "client_phone": "0555123456",
                "venue_id": "1",
                "event_date": "2026-08-01",
                "time_slot": "Soirée",
                "total_amount": "300000",
                "deposit_required": "50000",
            }
            # Simulate ImmutableMultiDict
            from werkzeug.datastructures import ImmutableMultiDict
            event, errors = BookingService.create_event(ImmutableMultiDict(data))
            assert errors == []
            assert event is not None
            assert event.title == "Test Wedding"
            assert event.total_amount == 300000

    def test_create_event_missing_title(self, _db, app):
        with app.app_context():
            from werkzeug.datastructures import ImmutableMultiDict
            data = {"title": "", "client_name": "Ahmed", "venue_id": "1", "event_date": "2026-08-01"}
            event, errors = BookingService.create_event(ImmutableMultiDict(data))
            assert event is None
            assert "titre" in errors[0].lower() or "requis" in errors[0].lower()

    def test_create_event_creates_deposit_payment(self, _db, app):
        with app.app_context():
            from werkzeug.datastructures import ImmutableMultiDict
            data = {
                "title": "With Deposit",
                "client_name": "Test",
                "client_phone": "123",
                "venue_id": "1",
                "event_date": "2026-09-01",
                "time_slot": "Soirée",
                "total_amount": "200000",
                "deposit_required": "75000",
            }
            event, errors = BookingService.create_event(ImmutableMultiDict(data))
            assert errors == []
            payment = Payment.query.filter_by(event_id=event.id).first()
            assert payment is not None
            assert payment.amount == 75000


# ══════════════════════════════════════════════════════════════════════
# Payments
# ══════════════════════════════════════════════════════════════════════

class TestPayments:
    """Unit tests for payment logic."""

    def _create_event(self):
        c = Client(name="Test", phone="123")
        db.session.add(c); db.session.flush()
        e = Event(title="Test", client_id=c.id, venue_id=1,
                  event_type="Mariage", event_date="2026-10-01", time_slot="Soirée",
                  total_amount=100000, status="en attente")
        db.session.add(e); db.session.commit()
        return e

    def test_valid_payment(self, _db, app):
        with app.app_context():
            event = self._create_event()
            payment, error = BookingService.add_payment(event.id, 50000)
            assert error is None
            assert payment.amount == 50000

    def test_payment_exceeding_balance(self, _db, app):
        with app.app_context():
            event = self._create_event()
            _, error = BookingService.add_payment(event.id, 999999)
            assert error is not None
            assert "dépasse" in error.lower()

    def test_payment_on_cancelled_event(self, _db, app):
        with app.app_context():
            event = self._create_event()
            event.status = "annulé"
            db.session.commit()
            _, error = BookingService.add_payment(event.id, 10000)
            assert error is not None
            assert "annulé" in error.lower()

    def test_payment_zero_amount(self, _db, app):
        with app.app_context():
            event = self._create_event()
            _, error = BookingService.add_payment(event.id, 0)
            assert error is not None

    def test_full_payment_auto_confirms(self, _db, app):
        with app.app_context():
            event = self._create_event()
            assert event.status == "en attente"
            BookingService.add_payment(event.id, 100000)
            db.session.refresh(event)
            assert event.status == "confirmé"

    def test_partial_payment_keeps_pending(self, _db, app):
        with app.app_context():
            event = self._create_event()
            BookingService.add_payment(event.id, 50000)
            db.session.refresh(event)
            assert event.status == "en attente"


# ══════════════════════════════════════════════════════════════════════
# Financials
# ══════════════════════════════════════════════════════════════════════

class TestFinancials:
    """Unit tests for financial calculations."""

    def test_get_financials_empty(self, _db, app):
        with app.app_context():
            c = Client(name="Test", phone="123")
            db.session.add(c); db.session.flush()
            e = Event(title="Test", client_id=c.id, venue_id=1,
                      event_type="Mariage", event_date="2026-11-01", time_slot="Soirée",
                      total_amount=500000)
            db.session.add(e); db.session.commit()
            fin = BookingService.get_financials(e.id)
            assert fin["revenue"] == 0
            assert fin["paid"] == 0
            assert fin["profit"] == 0

    def test_get_financials_with_data(self, _db, app):
        with app.app_context():
            c = Client(name="Test", phone="123")
            db.session.add(c); db.session.flush()
            e = Event(title="Test", client_id=c.id, venue_id=1,
                      event_type="Mariage", event_date="2026-11-01", time_slot="Soirée",
                      total_amount=500000)
            db.session.add(e); db.session.flush()
            db.session.add(EventLine(event_id=e.id, description="Salle", amount=300000))
            db.session.add(EventLine(event_id=e.id, description="DJ", amount=100000, is_cost=1))
            db.session.add(Payment(event_id=e.id, amount=200000))
            db.session.commit()
            fin = BookingService.get_financials(e.id)
            assert fin["revenue"] == 300000
            assert fin["costs"] == 100000
            assert fin["profit"] == 200000
            assert fin["paid"] == 200000

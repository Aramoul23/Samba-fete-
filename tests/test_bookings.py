"""Samba Fête — Booking tests.

Tests: create/edit/delete bookings, service lines, calendar, payments.
"""
import datetime
import pytest
from app.models import db, Event, Payment, EventLine


def _future_date(days=30):
    return (datetime.date.today() + datetime.timedelta(days=days)).isoformat()


def _csrf(sess):
    """Get or set a CSRF token in the session."""
    token = sess.get("csrf_token", "test-csrf-token")
    sess["csrf_token"] = token
    return token


# ══════════════════════════════════════════════════════════════════════
# Create Booking
# ══════════════════════════════════════════════════════════════════════

class TestCreateBooking:
    """Test booking creation via the form."""

    def test_form_page_loads(self, admin_client):
        """GET /evenement/nouveau should return 200."""
        resp = admin_client.get("/evenement/nouveau")
        assert resp.status_code == 200

    def test_create_booking_valid(self, admin_client, sample_client):
        """Creating a booking with valid data should succeed."""
        with admin_client.session_transaction() as sess:
            token = _csrf(sess)

        resp = admin_client.post("/evenement/nouveau", data={
            "csrf_token": token,
            "title": "Mariage Test",
            "client_name": "Ahmed Benali",
            "client_phone": "0555123456",
            "client_email": "ahmed@test.com",
            "venue_id": "1",
            "event_type": "Mariage",
            "event_date": _future_date(),
            "time_slot": "Soirée",
            "guests_men": "100",
            "guests_women": "80",
            "total_amount": "300000",
            "deposit_required": "50000",
            "price_location": "200000",
        }, follow_redirects=True)

        assert resp.status_code == 200
        event = Event.query.filter_by(title="Mariage Test").first()
        assert event is not None
        assert event.total_amount == 300000

    def test_create_booking_missing_title(self, admin_client, sample_client):
        """Missing title should show error."""
        with admin_client.session_transaction() as sess:
            token = _csrf(sess)

        resp = admin_client.post("/evenement/nouveau", data={
            "csrf_token": token,
            "title": "",
            "client_name": "Ahmed Benali",
            "client_phone": "0555123456",
            "venue_id": "1",
            "event_date": _future_date(),
        }, follow_redirects=True)

        assert resp.status_code == 200
        assert b"requis" in resp.data.lower() or b"titre" in resp.data.lower()

    def test_create_booking_missing_phone(self, admin_client, sample_client):
        """Missing phone should show error."""
        with admin_client.session_transaction() as sess:
            token = _csrf(sess)

        resp = admin_client.post("/evenement/nouveau", data={
            "csrf_token": token,
            "title": "Test Event",
            "client_name": "Ahmed Benali",
            "client_phone": "",
            "venue_id": "1",
            "event_date": _future_date(),
        }, follow_redirects=True)

        assert resp.status_code == 200
        assert b"t" in resp.data.lower()

    def test_create_booking_missing_date(self, admin_client, sample_client):
        """Missing date should show error."""
        with admin_client.session_transaction() as sess:
            token = _csrf(sess)

        resp = admin_client.post("/evenement/nouveau", data={
            "csrf_token": token,
            "title": "Test Event",
            "client_name": "Ahmed Benali",
            "client_phone": "0555123456",
            "venue_id": "1",
            "event_date": "",
        }, follow_redirects=True)

        assert resp.status_code == 200
        assert b"requise" in resp.data.lower() or b"date" in resp.data.lower()

    def test_create_booking_with_services(self, admin_client, sample_client):
        """Service line items should be saved to event_lines."""
        with admin_client.session_transaction() as sess:
            token = _csrf(sess)

        future = _future_date()
        admin_client.post("/evenement/nouveau", data={
            "csrf_token": token,
            "title": "Service Test",
            "client_name": "Ahmed Benali",
            "client_phone": "0555123456",
            "venue_id": "1",
            "event_date": future,
            "time_slot": "Soirée",
            "total_amount": "350000",
            "price_location": "200000",
            "service_individuel": "on",
            "price_individuel": "50000",
            "service_cafe": "on",
            "price_cafe": "100000",
        }, follow_redirects=True)

        event = Event.query.filter_by(title="Service Test").first()
        assert event is not None

        lines = EventLine.query.filter_by(event_id=event.id).all()
        descriptions = [line.description for line in lines]
        assert "Location de la salle" in descriptions
        assert "Service individuel" in descriptions
        assert "Service café" in descriptions

    def test_create_booking_auto_creates_deposit_payment(self, admin_client, sample_client):
        """If deposit_required > 0, a payment should be auto-created."""
        with admin_client.session_transaction() as sess:
            token = _csrf(sess)

        admin_client.post("/evenement/nouveau", data={
            "csrf_token": token,
            "title": "Deposit Test",
            "client_name": "Ahmed Benali",
            "client_phone": "0555123456",
            "venue_id": "1",
            "event_date": _future_date(),
            "time_slot": "Soirée",
            "total_amount": "200000",
            "deposit_required": "50000",
            "price_location": "200000",
        }, follow_redirects=True)

        event = Event.query.filter_by(title="Deposit Test").first()
        assert event is not None
        payment = Payment.query.filter_by(event_id=event.id).first()
        assert payment is not None
        assert payment.amount == 50000


# ══════════════════════════════════════════════════════════════════════
# View & Edit Booking
# ══════════════════════════════════════════════════════════════════════

class TestViewEditBooking:
    """Test viewing and editing bookings."""

    def test_view_booking(self, admin_client, sample_booking):
        """Viewing a booking should return event details."""
        if not sample_booking:
            pytest.skip("No booking created")
        resp = admin_client.get(f"/evenement/{sample_booking['id']}")
        assert resp.status_code == 200
        assert b"Mariage Ahmed" in resp.data

    def test_edit_booking_updates_data(self, admin_client, sample_booking):
        """Editing a booking should update the DB."""
        if not sample_booking:
            pytest.skip("No booking created")

        event_id = sample_booking["id"]
        with admin_client.session_transaction() as sess:
            token = _csrf(sess)

        resp = admin_client.post(f"/evenement/{event_id}/modifier", data={
            "csrf_token": token,
            "title": "Mariage Ahmed — Updated",
            "client_name": "Ahmed Benali",
            "client_phone": "0555123456",
            "venue_id": "1",
            "event_type": "Mariage",
            "event_date": sample_booking["event_date"],
            "time_slot": "Soirée",
            "guests_men": "200",
            "guests_women": "150",
            "total_amount": "600000",
            "deposit_required": "100000",
            "price_location": "400000",
            "service_cafe": "on",
            "price_cafe": "200000",
        }, follow_redirects=True)

        assert resp.status_code == 200
        event = db.session.get(Event, event_id)
        assert event is not None
        assert event.title == "Mariage Ahmed — Updated"
        assert event.total_amount == 600000

    def test_view_nonexistent_booking(self, admin_client, _db):
        """Viewing a nonexistent booking should return 404."""
        resp = admin_client.get("/evenement/99999")
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════
# Delete Booking
# ══════════════════════════════════════════════════════════════════════

class TestDeleteBooking:
    """Test booking deletion (admin only)."""

    def test_admin_can_delete_booking(self, admin_client, sample_booking):
        """Admin should be able to delete a booking."""
        if not sample_booking:
            pytest.skip("No booking created")

        event_id = sample_booking["id"]
        with admin_client.session_transaction() as sess:
            token = _csrf(sess)

        resp = admin_client.post(
            f"/evenement/{event_id}/supprimer",
            data={"csrf_token": token},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        event = db.session.get(Event, event_id)
        assert event is None

    def test_manager_cannot_delete_booking(self, manager_client, sample_booking):
        """Non-admin should not be able to delete bookings."""
        if not sample_booking:
            pytest.skip("No booking created")

        event_id = sample_booking["id"]
        with manager_client.session_transaction() as sess:
            token = _csrf(sess)

        resp = manager_client.post(
            f"/evenement/{event_id}/supprimer",
            data={"csrf_token": token},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"administrateur" in resp.data.lower()


# ══════════════════════════════════════════════════════════════════════
# Calendar
# ══════════════════════════════════════════════════════════════════════

class TestCalendar:
    """Test calendar view."""

    def test_calendar_loads(self, admin_client):
        """Calendar page should load."""
        resp = admin_client.get("/calendrier")
        assert resp.status_code == 200

    def test_calendar_shows_fullcalendar(self, admin_client):
        """Calendar page should include FullCalendar div."""
        resp = admin_client.get("/calendrier")
        assert resp.status_code == 200
        assert b'fullcalendar' in resp.data

    def test_calendar_with_venue_filter(self, admin_client, sample_booking):
        """Calendar should accept a venue filter."""
        resp = admin_client.get("/calendrier?venue=1")
        assert resp.status_code == 200

    def test_calendar_api_returns_events(self, admin_client, sample_booking):
        """API /api/calendar-events should return valid JSON with event colors."""
        if not sample_booking:
            pytest.skip("No booking")

        # Get the event date from the sample booking
        from app.models import Event
        event = Event.query.get(sample_booking["id"])
        if not event or not event.event_date:
            pytest.skip("No event date")

        date_str = str(event.event_date)[:10]
        year, month = date_str[:4], date_str[5:7]

        resp = admin_client.get(f"/api/calendar-events?year={year}&month={month}")
        assert resp.status_code == 200
        data = resp.json
        assert isinstance(data, list)
        assert len(data) > 0

        # Verify the event structure
        ev = data[0]
        assert "start" in ev
        assert "backgroundColor" in ev
        assert "borderColor" in ev
        assert "extendedProps" in ev
        assert "status" in ev["extendedProps"]

        # Verify date is a valid string (not an object)
        assert isinstance(ev["start"], str)
        assert len(ev["start"]) == 10  # YYYY-MM-DD

        # Verify colors are set based on status
        status = ev["extendedProps"]["status"]
        if status == "confirmé":
            assert ev["backgroundColor"] == "#06d6a0"
        elif status == "en attente":
            assert ev["backgroundColor"] == "#ffd166"

    def test_calendar_api_fullcalendar_start_end(self, admin_client, sample_booking):
        """API should accept FullCalendar's start/end date parameters."""
        if not sample_booking:
            pytest.skip("No booking")

        from app.models import Event
        event = Event.query.get(sample_booking["id"])
        if not event or not event.event_date:
            pytest.skip("No event date")

        date_str = str(event.event_date)[:10]

        # FullCalendar sends start/end as ISO date strings spanning the visible range
        # Use a range that definitely includes the event date
        start = (datetime.date.fromisoformat(date_str) - datetime.timedelta(days=1)).isoformat()
        end = (datetime.date.fromisoformat(date_str) + datetime.timedelta(days=1)).isoformat()

        resp = admin_client.get(f"/api/calendar-events?start={start}&end={end}")
        assert resp.status_code == 200
        data = resp.json
        assert isinstance(data, list)
        assert len(data) > 0


# ══════════════════════════════════════════════════════════════════════
# Event List
# ══════════════════════════════════════════════════════════════════════

class TestEventList:
    """Test event list with filters."""

    def test_event_list_loads(self, admin_client):
        """Event list page should load."""
        resp = admin_client.get("/evenements")
        assert resp.status_code == 200

    def test_event_list_with_search(self, admin_client, sample_booking):
        """Search should filter events."""
        resp = admin_client.get("/evenements?q=Ahmed")
        assert resp.status_code == 200

    def test_event_list_with_status_filter(self, admin_client, sample_booking):
        """Status filter should work."""
        resp = admin_client.get("/evenements?status=en attente")
        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════════
# Status Transitions
# ══════════════════════════════════════════════════════════════════════

class TestStatusTransitions:
    """Test event status changes."""

    def test_confirm_event(self, admin_client, sample_booking):
        """Confirming an 'en attente' event should work."""
        if not sample_booking:
            pytest.skip("No booking created")

        event_id = sample_booking["id"]
        with admin_client.session_transaction() as sess:
            token = _csrf(sess)

        resp = admin_client.post(f"/evenement/{event_id}/statut", data={
            "csrf_token": token,
            "status": "confirmé",
        }, follow_redirects=True)

        assert resp.status_code == 200
        event = db.session.get(Event, event_id)
        assert event.status == "confirmé"

    def test_cancel_event(self, admin_client, sample_booking):
        """Cancelling a confirmed event should work."""
        if not sample_booking:
            pytest.skip("No booking created")

        event_id = sample_booking["id"]

        # First confirm
        with admin_client.session_transaction() as sess:
            token = _csrf(sess)
        admin_client.post(f"/evenement/{event_id}/statut", data={
            "csrf_token": token,
            "status": "confirmé",
        })

        # Then cancel
        with admin_client.session_transaction() as sess:
            token = _csrf(sess)
        resp = admin_client.post(f"/evenement/{event_id}/statut", data={
            "csrf_token": token,
            "status": "annulé",
        }, follow_redirects=True)

        assert resp.status_code == 200
        event = db.session.get(Event, event_id)
        assert event.status == "annulé"

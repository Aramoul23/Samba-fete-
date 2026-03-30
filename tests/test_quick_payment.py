"""Samba Fête — Quick Payment tests.

Tests for the quick payment flow: template rendering, form validation,
and edge cases with non-round amounts (the step="any" fix).
"""
import datetime
import pytest
from app.models import db, Event, Payment


def _future_date(days=30):
    return (datetime.date.today() + datetime.timedelta(days=days)).isoformat()


def _csrf(sess):
    token = sess.get("csrf_token", "test-csrf-token")
    sess["csrf_token"] = token
    return token


# ══════════════════════════════════════════════════════════════════════
# Quick Payment Page Loads
# ══════════════════════════════════════════════════════════════════════

class TestQuickPaymentPage:
    """Test that the quick payment page loads correctly."""

    def test_quick_payment_loads(self, admin_client):
        """GET /paiement-rapide should return 200."""
        resp = admin_client.get("/paiement-rapide")
        assert resp.status_code == 200

    def test_quick_payment_search(self, admin_client, sample_client):
        """Searching for a client should show results."""
        resp = admin_client.get("/paiement-rapide?q=Ahmed")
        assert resp.status_code == 200
        assert b"Ahmed Benali" in resp.data

    def test_quick_payment_select_client(self, admin_client, sample_booking):
        """Selecting a client should show their events."""
        if not sample_booking:
            pytest.skip("No booking created")
        resp = admin_client.get(f"/paiement-rapide?client_id=1")
        assert resp.status_code == 200
        assert b"Mariage Ahmed" in resp.data

    def test_quick_payment_select_event(self, admin_client, sample_booking):
        """Selecting an event should show the payment form."""
        if not sample_booking:
            pytest.skip("No booking created")
        eid = sample_booking["id"]
        resp = admin_client.get(f"/paiement-rapide?client_id=1&event_id={eid}")
        assert resp.status_code == 200
        assert b"Encaisser le Paiement" in resp.data
        assert b"Montant" in resp.data


# ══════════════════════════════════════════════════════════════════════
# Quick Payment Amount Validation (the step="any" fix)
# ══════════════════════════════════════════════════════════════════════

class TestQuickPaymentAmounts:
    """Test that non-round amounts work correctly (step="any" fix)."""

    def test_step_any_attribute(self, admin_client, sample_booking):
        """The amount input should have step='any', not step='100'."""
        if not sample_booking:
            pytest.skip("No booking created")
        eid = sample_booking["id"]
        resp = admin_client.get(f"/paiement-rapide?client_id=1&event_id={eid}")
        html = resp.data.decode()
        # Must have step="any" to accept any amount
        assert 'step="any"' in html, "Amount input should have step='any'"
        # Must NOT have step="100" which caused the validation error
        assert 'step="100"' not in html, "Amount input must not have step='100'"

    def test_non_round_amount_accepted(self, admin_client, sample_booking):
        """A non-round amount like 47250.50 should be accepted by the backend."""
        if not sample_booking:
            pytest.skip("No booking created")
        eid = sample_booking["id"]
        with admin_client.session_transaction() as sess:
            token = _csrf(sess)

        resp = admin_client.post(f"/evenement/{eid}/paiement", data={
            "csrf_token": token,
            "amount": "47250.50",
            "method": "espèces",
            "payment_type": "avance",
            "next": f"/paiement-rapide?client_id=1&event_id={eid}",
        }, follow_redirects=True)

        assert resp.status_code == 200
        payment = Payment.query.filter_by(event_id=eid, amount=47250.50).first()
        assert payment is not None, "Non-round amount payment should be saved"

    def test_odd_amount_10001(self, admin_client, sample_booking):
        """An odd amount like 10001 (not divisible by 100) should be accepted."""
        if not sample_booking:
            pytest.skip("No booking created")
        eid = sample_booking["id"]
        with admin_client.session_transaction() as sess:
            token = _csrf(sess)

        resp = admin_client.post(f"/evenement/{eid}/paiement", data={
            "csrf_token": token,
            "amount": "10001",
            "method": "espèces",
            "payment_type": "avance",
            "next": f"/paiement-rapide?client_id=1&event_id={eid}",
        }, follow_redirects=True)

        assert resp.status_code == 200
        payment = Payment.query.filter_by(event_id=eid, amount=10001).first()
        assert payment is not None, "Odd amount payment should be saved"

    def test_single_dinar(self, admin_client, sample_booking):
        """A 1 DA payment should be accepted (min=1)."""
        if not sample_booking:
            pytest.skip("No booking created")
        eid = sample_booking["id"]
        with admin_client.session_transaction() as sess:
            token = _csrf(sess)

        resp = admin_client.post(f"/evenement/{eid}/paiement", data={
            "csrf_token": token,
            "amount": "1",
            "method": "espèces",
            "payment_type": "avance",
            "next": f"/paiement-rapide?client_id=1&event_id={eid}",
        }, follow_redirects=True)

        assert resp.status_code == 200
        payment = Payment.query.filter_by(event_id=eid, amount=1).first()
        assert payment is not None, "1 DA payment should be accepted"

    def test_zero_amount_rejected(self, admin_client, sample_booking):
        """Zero amount should be rejected by the backend."""
        if not sample_booking:
            pytest.skip("No booking created")
        eid = sample_booking["id"]
        with admin_client.session_transaction() as sess:
            token = _csrf(sess)

        resp = admin_client.post(f"/evenement/{eid}/paiement", data={
            "csrf_token": token,
            "amount": "0",
            "method": "espèces",
            "payment_type": "avance",
        }, follow_redirects=True)

        assert resp.status_code == 200
        assert b"invalide" in resp.data.lower() or b"montant" in resp.data.lower()

    def test_negative_amount_rejected(self, admin_client, sample_booking):
        """Negative amount should be rejected."""
        if not sample_booking:
            pytest.skip("No booking created")
        eid = sample_booking["id"]
        with admin_client.session_transaction() as sess:
            token = _csrf(sess)

        resp = admin_client.post(f"/evenement/{eid}/paiement", data={
            "csrf_token": token,
            "amount": "-500",
            "method": "espèces",
            "payment_type": "avance",
        }, follow_redirects=True)

        assert resp.status_code == 200
        # Should not have created a payment
        payment = Payment.query.filter_by(event_id=eid, amount=-500).first()
        assert payment is None


# ══════════════════════════════════════════════════════════════════════
# Quick Payment Redirect (next URL)
# ══════════════════════════════════════════════════════════════════════

class TestQuickPaymentRedirect:
    """Test that payment redirects back to quick payment page."""

    def test_redirect_back_to_quick_pay(self, admin_client, sample_booking):
        """After payment, should redirect to the quick payment page."""
        if not sample_booking:
            pytest.skip("No booking created")
        eid = sample_booking["id"]
        with admin_client.session_transaction() as sess:
            token = _csrf(sess)

        next_url = f"/paiement-rapide?client_id=1&event_id={eid}"
        resp = admin_client.post(f"/evenement/{eid}/paiement", data={
            "csrf_token": token,
            "amount": "25000",
            "method": "espèces",
            "payment_type": "avance",
            "next": next_url,
        })

        # Should redirect to the next URL (quick payment page)
        assert resp.status_code == 302
        assert "paiement-rapide" in resp.headers["Location"]


# ══════════════════════════════════════════════════════════════════════
# Quick Payment Buttons Render
# ══════════════════════════════════════════════════════════════════════

class TestQuickPaymentButtons:
    """Test that quick-pay preset buttons render correctly."""

    def test_solde_complet_button_shown(self, admin_client, sample_booking):
        """Full balance button should show remaining amount."""
        if not sample_booking:
            pytest.skip("No booking created")
        eid = sample_booking["id"]
        resp = admin_client.get(f"/paiement-rapide?client_id=1&event_id={eid}")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Solde Complet" in html

    def test_preset_buttons_shown(self, admin_client, sample_booking):
        """Preset amount buttons should be present."""
        if not sample_booking:
            pytest.skip("No booking created")
        eid = sample_booking["id"]
        resp = admin_client.get(f"/paiement-rapide?client_id=1&event_id={eid}")
        assert resp.status_code == 200
        html = resp.data.decode()
        # 20000 and 30000 preset buttons should always appear
        assert 'data-amount="20000"' in html
        assert 'data-amount="30000"' in html

    def test_financial_summary_shown(self, admin_client, sample_booking):
        """Financial summary should be displayed."""
        if not sample_booking:
            pytest.skip("No booking created")
        eid = sample_booking["id"]
        resp = admin_client.get(f"/paiement-rapide?client_id=1&event_id={eid}")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Résumé" in html
        assert "Reste à Payer" in html

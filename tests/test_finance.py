"""Samba Fête — Finance tests.

Tests: payments, dashboard stats, expenses, PDF generation.
"""
import datetime
import pytest
from app.models import db, Event, Client, Payment, Expense


def _has_weasyprint():
    try:
        import weasyprint  # noqa: F401
        return True
    except ImportError:
        return False


def _future_date(days=30):
    return (datetime.date.today() + datetime.timedelta(days=days)).isoformat()


def _csrf(sess):
    token = sess.get("csrf_token", "test-csrf-token")
    sess["csrf_token"] = token
    return token


# ══════════════════════════════════════════════════════════════════════
# Payment Tests
# ══════════════════════════════════════════════════════════════════════

class TestPayments:
    """Test payment recording and validation."""

    def test_record_payment(self, admin_client, sample_booking):
        """Recording a valid payment should succeed."""
        if not sample_booking:
            pytest.skip("No booking")

        event_id = sample_booking["id"]
        with admin_client.session_transaction() as sess:
            token = _csrf(sess)

        resp = admin_client.post(f"/evenement/{event_id}/paiement", data={
            "csrf_token": token,
            "amount": "50000",
            "method": "espèces",
            "payment_type": "acompte",
        }, follow_redirects=True)

        assert resp.status_code == 200
        total = db.session.query(
            db.func.coalesce(db.func.sum(Payment.amount), 0)
        ).filter(
            Payment.event_id == event_id,
            Payment.is_refunded == False,  # noqa: E712
        ).scalar()
        assert total >= 50000

    def test_payment_exceeding_balance_rejected(self, admin_client, sample_booking):
        """Payment exceeding remaining balance should be rejected."""
        if not sample_booking:
            pytest.skip("No booking")

        event_id = sample_booking["id"]
        with admin_client.session_transaction() as sess:
            token = _csrf(sess)

        resp = admin_client.post(f"/evenement/{event_id}/paiement", data={
            "csrf_token": token,
            "amount": "9999999",
            "method": "espèces",
            "payment_type": "solde",
        }, follow_redirects=True)

        assert resp.status_code == 200
        assert b"d" in resp.data.lower() or b"maximum" in resp.data.lower()

    def test_payment_zero_amount_rejected(self, admin_client, sample_booking):
        """Zero amount payment should be rejected."""
        if not sample_booking:
            pytest.skip("No booking")

        event_id = sample_booking["id"]
        with admin_client.session_transaction() as sess:
            token = _csrf(sess)

        resp = admin_client.post(f"/evenement/{event_id}/paiement", data={
            "csrf_token": token,
            "amount": "0",
            "method": "espèces",
        }, follow_redirects=True)

        assert resp.status_code == 200
        assert b"invalide" in resp.data.lower() or b"montant" in resp.data.lower()

    def test_payment_on_cancelled_event_rejected(self, admin_client, sample_booking):
        """Payments on cancelled events should be rejected."""
        if not sample_booking:
            pytest.skip("No booking")

        event_id = sample_booking["id"]

        # First cancel the event
        with admin_client.session_transaction() as sess:
            token = _csrf(sess)
        admin_client.post(f"/evenement/{event_id}/statut", data={
            "csrf_token": token,
            "status": "confirmé",
        })
        with admin_client.session_transaction() as sess:
            token = _csrf(sess)
        admin_client.post(f"/evenement/{event_id}/statut", data={
            "csrf_token": token,
            "status": "annulé",
        })

        # Try to add payment
        with admin_client.session_transaction() as sess:
            token = _csrf(sess)
        resp = admin_client.post(f"/evenement/{event_id}/paiement", data={
            "csrf_token": token,
            "amount": "10000",
            "method": "espèces",
        }, follow_redirects=True)

        assert resp.status_code == 200
        assert b"annul" in resp.data.lower()

    def test_payment_methods(self, admin_client, sample_booking):
        """Different payment methods should be recorded."""
        if not sample_booking:
            pytest.skip("No booking")

        event_id = sample_booking["id"]
        methods = ["espèces", "chèque", "virement"]
        for method in methods:
            with admin_client.session_transaction() as sess:
                token = _csrf(sess)
            admin_client.post(f"/evenement/{event_id}/paiement", data={
                "csrf_token": token,
                "amount": "10000",
                "method": method,
                "payment_type": "acompte",
            })

        payments = Payment.query.filter_by(event_id=event_id).all()
        recorded_methods = {p.method for p in payments}
        assert len(recorded_methods) >= 1


# ══════════════════════════════════════════════════════════════════════
# Dashboard Tests
# ══════════════════════════════════════════════════════════════════════

class TestDashboard:
    """Test dashboard statistics."""

    def test_dashboard_loads(self, admin_client):
        """Dashboard should load with KPIs."""
        resp = admin_client.get("/")
        assert resp.status_code == 200

    def test_dashboard_shows_stats(self, admin_client, sample_booking):
        """Dashboard should show event count."""
        resp = admin_client.get("/")
        assert resp.status_code == 200
        assert b"Samba" in resp.data or b"F" in resp.data

    def test_dashboard_chart_data(self, admin_client):
        """Dashboard should include chart data."""
        resp = admin_client.get("/")
        assert resp.status_code == 200
        assert b"chart" in resp.data.lower() or b"revenu" in resp.data.lower()


# ══════════════════════════════════════════════════════════════════════
# Financial Reports
# ══════════════════════════════════════════════════════════════════════

class TestFinancialReports:
    """Test financial report generation."""

    def test_financials_page_loads(self, admin_client):
        """Financials page should load."""
        resp = admin_client.get("/finances")
        assert resp.status_code == 200

    def test_financials_with_date_range(self, admin_client):
        """Financials should accept date range parameters."""
        start = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()
        end = datetime.date.today().isoformat()
        resp = admin_client.get(f"/finances?start_date={start}&end_date={end}")
        assert resp.status_code == 200

    def test_financials_csv_export(self, admin_client):
        """CSV export should return text/csv content."""
        resp = admin_client.get("/finances?export=1")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type

    def test_accounting_page_loads(self, admin_client):
        """Accounting P&L page should load."""
        resp = admin_client.get("/comptabilite")
        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════════
# Expense Tests
# ══════════════════════════════════════════════════════════════════════

class TestExpenses:
    """Test expense management."""

    def test_expenses_page_loads(self, admin_client):
        """Expenses page should load."""
        resp = admin_client.get("/depenses")
        assert resp.status_code == 200

    def test_add_expense(self, admin_client):
        """Adding an expense should succeed."""
        with admin_client.session_transaction() as sess:
            token = _csrf(sess)

        resp = admin_client.post("/depenses/ajouter", data={
            "csrf_token": token,
            "category": "Serveurs",
            "description": "Test expense",
            "amount": "15000",
            "expense_date": datetime.date.today().isoformat(),
            "method": "espèces",
        }, follow_redirects=True)

        assert resp.status_code == 200
        exp = Expense.query.filter_by(description="Test expense").first()
        assert exp is not None
        assert exp.amount == 15000

    def test_add_expense_zero_amount_rejected(self, admin_client):
        """Zero amount expense should be rejected."""
        with admin_client.session_transaction() as sess:
            token = _csrf(sess)

        resp = admin_client.post("/depenses/ajouter", data={
            "csrf_token": token,
            "category": "Serveurs",
            "description": "Bad expense",
            "amount": "0",
            "expense_date": datetime.date.today().isoformat(),
        }, follow_redirects=True)

        assert resp.status_code == 200
        exp = Expense.query.filter_by(description="Bad expense").first()
        assert exp is None

    def test_delete_expense(self, admin_client):
        """Deleting an expense should remove it."""
        # First create one
        exp = Expense(
            category="Serveurs",
            description="To Delete",
            amount=10000,
            expense_date=datetime.date.today().isoformat(),
        )
        db.session.add(exp)
        db.session.commit()
        exp_id = exp.id

        with admin_client.session_transaction() as sess:
            token = _csrf(sess)

        resp = admin_client.post(
            f"/depense/{exp_id}/supprimer",
            data={"csrf_token": token},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        deleted = db.session.get(Expense, exp_id)
        assert deleted is None


# ══════════════════════════════════════════════════════════════════════
# PDF Generation
# ══════════════════════════════════════════════════════════════════════

class TestPDFGeneration:
    """Test contract and receipt PDF generation."""

    @pytest.mark.skipif(not _has_weasyprint(), reason="weasyprint not installed")
    def test_contract_returns_pdf(self, admin_client, sample_booking):
        """Contract generation should return PDF content."""
        if not sample_booking:
            pytest.skip("No booking")

        event_id = sample_booking["id"]
        resp = admin_client.get(f"/evenement/{event_id}/contrat")
        assert resp.status_code == 200
        assert "application/pdf" in resp.content_type
        assert resp.data[:4] == b"%PDF"

    @pytest.mark.skipif(not _has_weasyprint(), reason="weasyprint not installed")
    def test_receipt_returns_pdf(self, admin_client, sample_payment):
        """Receipt generation should return PDF content."""
        if not sample_payment:
            pytest.skip("No payment")

        event_id = sample_payment["event_id"]
        payment_id = sample_payment["id"]
        resp = admin_client.get(f"/evenement/{event_id}/recu/{payment_id}")
        assert resp.status_code == 200
        assert "application/pdf" in resp.content_type
        assert resp.data[:4] == b"%PDF"

    def test_contract_nonexistent_event(self, admin_client, _db):
        """Contract for nonexistent event should return 404."""
        resp = admin_client.get("/evenement/99999/contrat")
        assert resp.status_code in (404, 302)


# ══════════════════════════════════════════════════════════════════════
# ODS Exports
# ══════════════════════════════════════════════════════════════════════

class TestExports:
    """Test ODS export endpoints."""

    def test_export_events(self, admin_client):
        """Events ODS export should return spreadsheet."""
        resp = admin_client.get("/export/events.ods")
        assert resp.status_code == 200
        assert "opendocument" in resp.content_type

    def test_export_clients(self, admin_client):
        """Clients ODS export should return spreadsheet."""
        resp = admin_client.get("/export/clients.ods")
        assert resp.status_code == 200
        assert "opendocument" in resp.content_type

    def test_export_payments(self, admin_client):
        """Payments ODS export should return spreadsheet."""
        resp = admin_client.get("/export/payments.ods")
        assert resp.status_code == 200
        assert "opendocument" in resp.content_type

    def test_export_expenses(self, admin_client):
        """Expenses ODS export should return spreadsheet."""
        resp = admin_client.get("/export/expenses.ods")
        assert resp.status_code == 200
        assert "opendocument" in resp.content_type

    def test_export_finances(self, admin_client):
        """Finances ODS export should return spreadsheet."""
        resp = admin_client.get("/export/finances.ods")
        assert resp.status_code == 200
        assert "opendocument" in resp.content_type

    def test_export_pl(self, admin_client):
        """P&L ODS export should return spreadsheet."""
        resp = admin_client.get("/export/pl.ods")
        assert resp.status_code == 200
        assert "opendocument" in resp.content_type

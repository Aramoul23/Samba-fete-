"""Samba Fête — Test fixtures.

conftest.py: test app factory, DB fixtures, auth helpers, sample data.
"""
import os
import sys
import tempfile
import shutil

import pytest

# ── Force test environment BEFORE any app imports ────────────────────
os.environ["FLASK_ENV"] = "testing"
os.environ["FLASK_DEBUG"] = "0"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["ADMIN_PASSWORD"] = "Admin123!"
os.environ.pop("DATABASE_URL", None)  # Force SQLite


# ══════════════════════════════════════════════════════════════════════
# App & Database Fixtures
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def tmp_db_path():
    """Create a temporary SQLite file for the test session."""
    tmpdir = tempfile.mkdtemp(prefix="samba_test_")
    db_path = os.path.join(tmpdir, "test.db")
    os.environ["SQLITE_DB_PATH"] = db_path
    yield db_path
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="session")
def app(tmp_db_path):
    """Create a test Flask app with CSRF and rate limiting disabled."""
    from app import create_app
    from app.models import db as sqlalchemy_db

    test_app = create_app("testing")
    test_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SECRET_KEY="test-secret-key-not-for-production",
        SERVER_NAME="localhost",
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_db_path}",
    )

    # Disable rate limiting for tests
    from app import limiter
    limiter.enabled = False

    # Disable CSRF for tests by removing csrf_protect before_request
    with test_app.app_context():
        # Remove all before_request handlers (including CSRF)
        test_app.before_request_funcs[None] = []

    yield test_app


@pytest.fixture()
def _reset_db(app, tmp_db_path):
    """Reset the database to a clean state before each test."""
    from app.models import db as sqlalchemy_db
    import gc
    gc.collect()

    with app.app_context():
        # Drop all tables and recreate
        sqlalchemy_db.drop_all()
        sqlalchemy_db.create_all()

        # Seed default data
        from app.models import User, Venue, Setting
        for name, cap_m, cap_w in [
            ("Grande Salle", 200, 200),
            ("Salle VIP", 80, 80),
        ]:
            sqlalchemy_db.session.add(Venue(name=name, capacity_men=cap_m, capacity_women=cap_w))
        for key, val in [("hall_name", "Samba Fête"), ("currency", "DA"), ("deposit_min", "20000")]:
            sqlalchemy_db.session.add(Setting(key=key, value=val))
        sqlalchemy_db.session.commit()

    yield

    gc.collect()


# ══════════════════════════════════════════════════════════════════════
# User Fixtures
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture()
def admin_user(_reset_db, app):
    """Create an admin user."""
    from app.models import db, User
    with app.app_context():
        user = User(username="admin", role="admin")
        user.set_password("Admin123!")
        db.session.add(user)
        db.session.commit()
        return {
            "id": user.id,
            "username": "admin",
            "password": "Admin123!",
            "role": "admin",
        }


@pytest.fixture()
def manager_user(_reset_db, app):
    """Create a manager (non-admin) user."""
    from app.models import db, User
    with app.app_context():
        user = User(username="manager", role="manager")
        user.set_password("Manager123!")
        db.session.add(user)
        db.session.commit()
        return {
            "id": user.id,
            "username": "manager",
            "password": "Manager123!",
            "role": "manager",
        }


@pytest.fixture()
def admin_client(app, admin_user):
    """Test client logged in as admin."""
    client = app.test_client()
    client.post("/login", data={
        "username": admin_user["username"],
        "password": admin_user["password"],
    })
    return client


@pytest.fixture()
def client(app, _reset_db):
    """Unauthenticated test client."""
    return app.test_client()


@pytest.fixture()
def manager_client(app, manager_user):
    """Test client logged in as manager."""
    client = app.test_client()
    client.post("/login", data={
        "username": manager_user["username"],
        "password": manager_user["password"],
    })
    return client


# ══════════════════════════════════════════════════════════════════════
# Sample Data Fixtures
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture()
def sample_client(_reset_db, app):
    """Create a sample client."""
    from app.models import db, Client
    with app.app_context():
        client = Client(name="Ahmed Benali", phone="0555123456", email="ahmed@test.com")
        db.session.add(client)
        db.session.commit()
        return client.id


@pytest.fixture()
def sample_booking(app, admin_client, sample_client):
    """Create a sample booking via the API."""
    import datetime
    future_date = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()

    with admin_client.session_transaction() as sess:
        sess["csrf_token"] = "test-csrf-token"

    resp = admin_client.post("/evenement/nouveau", data={
        "csrf_token": "test-csrf-token",
        "title": "Mariage Ahmed",
        "client_name": "Ahmed Benali",
        "client_phone": "0555123456",
        "client_email": "ahmed@test.com",
        "venue_id": "1",
        "event_type": "Mariage",
        "event_date": future_date,
        "time_slot": "Soirée",
        "guests_men": "150",
        "guests_women": "100",
        "total_amount": "500000",
        "deposit_required": "100000",
        "price_location": "300000",
        "service_individuel": "on",
        "price_individuel": "50000",
        "service_cafe": "on",
        "price_cafe": "100000",
        "notes": "Test booking",
    }, follow_redirects=True)

    from app.models import Event
    with app.app_context():
        event = Event.query.filter_by(title="Mariage Ahmed").first()
        if event:
            return {
                "id": event.id,
                "title": event.title,
                "event_date": event.event_date,
                "total_amount": event.total_amount,
                "status": event.status,
            }
        return None


@pytest.fixture()
def sample_payment(app, admin_client, sample_booking):
    """Create a sample payment for a booking."""
    if not sample_booking:
        pytest.skip("No booking to attach payment to")

    event_id = sample_booking["id"]
    with admin_client.session_transaction() as sess:
        sess["csrf_token"] = "test-csrf-token"

    admin_client.post(f"/evenement/{event_id}/paiement", data={
        "csrf_token": "test-csrf-token",
        "amount": "50000",
        "method": "espèces",
        "payment_type": "acompte",
        "notes": "Test payment",
    })

    from app.models import Payment
    with app.app_context():
        payment = Payment.query.filter_by(event_id=event_id).order_by(Payment.id.desc()).first()
        if payment:
            return {"id": payment.id, "event_id": payment.event_id, "amount": payment.amount}
        return None

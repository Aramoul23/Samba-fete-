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
os.environ["ADMIN_PASSWORD"] = "Admin123!"  # Default admin password for tests
os.environ.pop("DATABASE_URL", None)  # Force SQLite


# ── Import app modules (AFTER env is set) ────────────────────────────
from models import init_db, get_db, create_user, generate_password_hash


# ══════════════════════════════════════════════════════════════════════
# App & Database Fixtures
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def tmp_db_path():
    """Create a temporary SQLite file for the test session."""
    import tempfile
    # Use a temp DIRECTORY so we can freely delete/recreate the file
    tmpdir = tempfile.mkdtemp(prefix="samba_test_")
    db_path = os.path.join(tmpdir, "test.db")
    os.environ["SQLITE_DB_PATH"] = db_path
    yield db_path
    # Cleanup
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="session")
def app(tmp_db_path):
    """Create a test Flask app with CSRF and rate limiting disabled."""
    from app import create_app

    test_app = create_app("testing")
    test_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SECRET_KEY="test-secret-key-not-for-production",
        SERVER_NAME="localhost",
    )

    # Disable rate limiting for tests
    from app import limiter
    limiter.enabled = False

    # Disable CSRF for tests
    test_app.before_request_funcs.pop(None, None)  # Remove csrf_protect

    # Re-add non-CSRF before_request handlers
    @test_app.before_request
    def _no_csrf():
        pass

    yield test_app


@pytest.fixture(scope="session")
def _app_ctx(app):
    """Push an app context for the entire test session."""
    ctx = app.app_context()
    ctx.push()
    yield
    ctx.pop()


@pytest.fixture()
def client(app, _reset_db):
    """Flask test client — fresh session per test with fresh app context."""
    with app.test_client() as test_client:
        with app.app_context():
            yield test_client


# ══════════════════════════════════════════════════════════════════════
# Database Reset
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture()
def _reset_db(tmp_db_path):
    """Reset the database to a clean state before each test."""
    import gc
    gc.collect()

    # Delete and recreate the DB file
    try:
        if os.path.exists(tmp_db_path):
            os.unlink(tmp_db_path)
    except Exception:
        pass

    # Re-init the schema (init_db() already seeds venues, settings, admin user)
    init_db()

    # Verify the DB is writable
    db = get_db()
    try:
        db.execute("SELECT 1").fetchone()
    finally:
        db.close()

    yield

    # Cleanup after test
    gc.collect()


def _seed_default_data():
    """Seed venues and settings (same as _ensure_default_data in factory)."""
    db = get_db()
    try:
        for v in [
            {"name": "Grande Salle", "capacity_men": 200, "capacity_women": 200},
            {"name": "Salle VIP", "capacity_men": 80, "capacity_women": 80},
        ]:
            db.execute(
                "INSERT INTO venues (name, capacity_men, capacity_women, is_active) "
                "VALUES (?, ?, ?, 1)",
                (v["name"], v["capacity_men"], v["capacity_women"]),
            )
        for key, val in [("hall_name", "Samba Fête"), ("currency", "DA"), ("deposit_min", "20000")]:
            db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, val))
        db.commit()
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════
# User Fixtures
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture()
def admin_user(_reset_db):
    """Return the default admin user created by init_db()."""
    db = get_db()
    try:
        user = db.execute("SELECT * FROM users WHERE username='admin'").fetchone()
        return {
            "id": user["id"],
            "username": "admin",
            "password": "Admin123!",
            "role": "admin",
        }
    finally:
        db.close()


@pytest.fixture()
def manager_user(_reset_db):
    """Create a manager (non-admin) user."""
    create_user("manager", "Manager123!", "manager")
    db = get_db()
    try:
        user = db.execute("SELECT * FROM users WHERE username='manager'").fetchone()
        return {
            "id": user["id"],
            "username": "manager",
            "password": "Manager123!",
            "role": "manager",
        }
    finally:
        db.close()


@pytest.fixture()
def admin_client(client, admin_user):
    """Test client logged in as admin."""
    client.post("/login", data={
        "username": admin_user["username"],
        "password": admin_user["password"],
    })
    return client


@pytest.fixture()
def manager_client(client, manager_user):
    """Test client logged in as manager."""
    client.post("/login", data={
        "username": manager_user["username"],
        "password": manager_user["password"],
    })
    return client


# ══════════════════════════════════════════════════════════════════════
# Sample Data Fixtures
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture()
def sample_client(_reset_db):
    """Create a sample client in the DB."""
    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO clients (name, phone, email) VALUES (?, ?, ?)",
            ("Ahmed Benali", "0555123456", "ahmed@test.com"),
        )
        db.commit()
        return cur.lastrowid
    finally:
        db.close()


@pytest.fixture()
def sample_booking(admin_client, sample_client):
    """Create a sample booking via the API."""
    import datetime
    future_date = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()

    # Get CSRF token from session
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

    # Return the event ID
    db = get_db()
    try:
        event = db.execute("SELECT * FROM events WHERE title='Mariage Ahmed'").fetchone()
        return dict(event) if event else None
    finally:
        db.close()


@pytest.fixture()
def sample_payment(admin_client, sample_booking):
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

    db = get_db()
    try:
        payment = db.execute(
            "SELECT * FROM payments WHERE event_id=? ORDER BY id DESC LIMIT 1",
            (event_id,),
        ).fetchone()
        return dict(payment) if payment else None
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def login(client, username, password):
    """Helper to log in a user."""
    return client.post("/login", data={
        "username": username,
        "password": password,
    })


def post_with_csrf(client, url, data=None, **kwargs):
    """POST with CSRF token injected from session."""
    data = data or {}
    with client.session_transaction() as sess:
        data["csrf_token"] = sess.get("csrf_token", "test-csrf-token")
    return client.post(url, data=data, **kwargs)

"""Samba Fête — Test fixtures.

Fresh SQLite database per test session, clean state per test.
Flask-WTF CSRF disabled via WTF_CSRF_ENABLED=False.
"""
import os
import tempfile

import pytest

# ── Force test environment BEFORE any app imports ────────────────────
os.environ["FLASK_ENV"] = "testing"
os.environ["FLASK_DEBUG"] = "0"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["ADMIN_PASSWORD"] = "Admin123!"
os.environ.pop("DATABASE_URL", None)


@pytest.fixture(scope="session")
def tmp_db_path():
    tmpdir = tempfile.mkdtemp(prefix="samba_test_")
    db_path = os.path.join(tmpdir, "test.db")
    os.environ["SQLITE_DB_PATH"] = db_path
    yield db_path
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="session")
def app(tmp_db_path):
    from app import create_app
    test_app = create_app("testing")
    test_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key-not-for-production",
        SERVER_NAME="localhost",
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_db_path}",
        WTF_CSRF_ENABLED=False,
    )
    from app import limiter
    limiter.enabled = False
    yield test_app


@pytest.fixture()
def _reset_db(app, tmp_db_path):
    """Reset DB — include in tests that need clean state."""
    from app.models import db as sa
    with app.app_context():
        sa.session.rollback()
        sa.drop_all()
        sa.create_all()
        from app.models import Venue, Setting
        for name, m, w in [("Grande Salle", 200, 200), ("Salle VIP", 80, 80)]:
            sa.session.add(Venue(name=name, capacity_men=m, capacity_women=w))
        for k, v in [("hall_name", "Samba Fête"), ("currency", "DA"), ("deposit_min", "20000")]:
            sa.session.add(Setting(key=k, value=v))
        sa.session.commit()
    yield


@pytest.fixture()
def admin_user(app, _reset_db):
    from app.models import db, User
    with app.app_context():
        u = User(username="admin", role="admin")
        u.set_password("Admin123!")
        db.session.add(u); db.session.commit()
        return {"id": u.id, "username": "admin", "password": "Admin123!", "role": "admin"}


@pytest.fixture()
def manager_user(app, _reset_db):
    from app.models import db, User
    with app.app_context():
        u = User(username="manager", role="manager")
        u.set_password("Manager123!")
        db.session.add(u); db.session.commit()
        return {"id": u.id, "username": "manager", "password": "Manager123!", "role": "manager"}


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin_client(app, admin_user):
    c = app.test_client()
    c.post("/login", data={"username": admin_user["username"], "password": admin_user["password"]})
    return c


@pytest.fixture()
def manager_client(app, manager_user):
    c = app.test_client()
    c.post("/login", data={"username": manager_user["username"], "password": manager_user["password"]})
    return c


@pytest.fixture()
def sample_client(app, _reset_db):
    from app.models import db, Client
    with app.app_context():
        c = Client(name="Ahmed Benali", phone="0555123456", email="ahmed@test.com")
        db.session.add(c); db.session.commit()
        return c.id


@pytest.fixture()
def sample_booking(app, admin_client, sample_client):
    import datetime
    fd = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
    with admin_client.session_transaction() as sess:
        sess["csrf_token"] = "test-csrf-token"
    admin_client.post("/evenement/nouveau", data={
        "csrf_token": "test-csrf-token",
        "title": "Mariage Ahmed", "client_name": "Ahmed Benali",
        "client_phone": "0555123456", "client_email": "ahmed@test.com",
        "venue_id": "1", "event_type": "Mariage", "event_date": fd,
        "time_slot": "Soirée", "guests_men": "150", "guests_women": "100",
        "total_amount": "500000", "deposit_required": "100000",
        "price_location": "300000", "service_individuel": "on",
        "price_individuel": "50000", "service_cafe": "on", "price_cafe": "100000",
    }, follow_redirects=True)
    from app.models import Event
    with app.app_context():
        e = Event.query.filter_by(title="Mariage Ahmed").first()
        if e:
            return {"id": e.id, "title": e.title, "event_date": e.event_date,
                    "total_amount": e.total_amount, "status": e.status}
        return None


@pytest.fixture()
def sample_payment(app, admin_client, sample_booking):
    if not sample_booking:
        pytest.skip("No booking")
    eid = sample_booking["id"]
    with admin_client.session_transaction() as sess:
        sess["csrf_token"] = "test-csrf-token"
    admin_client.post(f"/evenement/{eid}/paiement", data={
        "csrf_token": "test-csrf-token", "amount": "50000",
        "method": "espèces", "payment_type": "acompte",
    })
    from app.models import Payment
    with app.app_context():
        p = Payment.query.filter_by(event_id=eid).order_by(Payment.id.desc()).first()
        if p:
            return {"id": p.id, "event_id": p.event_id, "amount": p.amount}
        return None

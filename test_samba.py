"""Tests for Samba Fête app – utils + models (no Flask server needed)."""

import sqlite3

import pytest
from werkzeug.security import generate_password_hash, check_password_hash

# ── utils (safe to import anytime) ──────────────────────────────────────────
from utils import format_da, format_date_fr

# ── models (must point DB_PATH at a temp file BEFORE first import) ──────────
DB_PATH = None  # set per-test via fixture


def _patched_get_db():
    """Drop-in replacement for models.get_db that uses DB_PATH."""
    import models

    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return models.DB(conn, False)


@pytest.fixture(autouse=True)
def _setup_models(monkeypatch, tmp_path):
    """Point models at a fresh temp database for every test."""
    global DB_PATH
    db_file = str(tmp_path / "test.db")
    DB_PATH = db_file

    import models

    monkeypatch.setattr(models, "get_db", _patched_get_db)
    monkeypatch.setattr(models, "is_postgres", lambda: False)


# ═══════════════════════════════════════════════════════════════════════════
# Test 1 – utils.format_da
# ═══════════════════════════════════════════════════════════════════════════


class TestFormatDa:
    @pytest.mark.parametrize(
        "amount, expected",
        [
            (0, "0 DA"),
            (1000, "1 000 DA"),
            (1000000, "1 000 000 DA"),
            (20000, "20 000 DA"),
            (500.5, "500 DA"),
            (999, "999 DA"),
            ("3000", "3 000 DA"),
            ("not_a_number", "0 DA"),
            (None, "0 DA"),
            ("", "0 DA"),
        ],
    )
    def test_format_da(self, amount, expected):
        assert format_da(amount) == expected


# ═══════════════════════════════════════════════════════════════════════════
# Test 2 – utils.format_date_fr
# ═══════════════════════════════════════════════════════════════════════════


class TestFormatDateFr:
    @pytest.mark.parametrize(
        "date_str, expected",
        [
            ("2024-01-15", "15 Janvier 2024"),
            ("2024-06-01", "1 Juin 2024"),
            ("2024-12-31", "31 Décembre 2024"),
            ("2024-03-08", "8 Mars 2024"),
            ("2024-07-14", "14 Juillet 2024"),
            ("2024-11-01", "1 Novembre 2024"),
            ("invalid", "invalid"),
            ("", ""),
            (None, "None"),
        ],
    )
    def test_format_date_fr(self, date_str, expected):
        assert format_date_fr(date_str) == expected

    def test_datetime_object(self):
        from datetime import datetime

        dt = datetime(2024, 5, 20)
        assert format_date_fr(dt) == "20 Mai 2024"


# ═══════════════════════════════════════════════════════════════════════════
# Test 3 – models.User creation & password hashing
# ═══════════════════════════════════════════════════════════════════════════


class TestUser:
    def test_attributes(self):
        from models import User

        u = User(1, "alice", "hash123", "admin", 1)
        assert u.id == 1
        assert u.username == "alice"
        assert u.role == "admin"

    def test_is_admin(self):
        from models import User

        admin = User(1, "a", "h", "admin")
        manager = User(2, "m", "h", "manager")
        assert admin.is_admin is True
        assert manager.is_admin is False

    def test_is_active_property(self):
        from models import User

        active = User(1, "a", "h", "admin", 1)
        inactive = User(2, "b", "h", "admin", 0)
        assert active.is_active is True
        assert inactive.is_active is False

    def test_flask_login_properties(self):
        from models import User

        u = User(1, "a", "h", "admin")
        assert u.is_authenticated is True
        assert u.is_anonymous is False
        assert u.get_id() == "1"

    def test_password_hash_and_check(self):
        pw = "s3cret!"
        h = generate_password_hash(pw)
        assert h != pw
        assert check_password_hash(h, pw)
        assert not check_password_hash(h, "wrong")


# ═══════════════════════════════════════════════════════════════════════════
# Test 4 – models.init_db creates tables + defaults
# ═══════════════════════════════════════════════════════════════════════════


class TestInitDb:
    def test_creates_all_tables(self):
        from models import init_db

        init_db()
        conn = sqlite3.connect(DB_PATH)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        expected = {
            "venues",
            "clients",
            "events",
            "event_lines",
            "payments",
            "expenses",
            "settings",
            "users",
        }
        assert expected.issubset(tables)

    def test_seeds_venues(self):
        from models import init_db

        init_db()
        conn = sqlite3.connect(DB_PATH)
        count = conn.execute("SELECT COUNT(*) FROM venues").fetchone()[0]
        conn.close()
        assert count == 3

    def test_seeds_settings(self):
        from models import init_db

        init_db()
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        conn.close()
        settings = {r[0]: r[1] for r in rows}
        assert settings["currency"] == "DA"
        assert settings["deposit_min"] == "20000"
        assert settings["hall_name"] == "Samba Fête"

    def test_seeds_default_admin(self):
        from models import init_db

        init_db()
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM users WHERE username='admin'").fetchone()
        conn.close()
        assert row is not None
        assert row["role"] == "admin"
        assert row["is_active"] == 1
        # Password is now randomly generated, just verify hash is valid
        assert row["password_hash"].startswith(("scrypt:", "pbkdf2:"))


# ═══════════════════════════════════════════════════════════════════════════
# Test 5 – models.create_user / get_user_by_username / delete
# ═══════════════════════════════════════════════════════════════════════════


class TestUserCrud:
    def test_create_and_retrieve(self):
        from models import init_db, create_user, get_user_by_username

        init_db()
        create_user("bob", "pass456", role="manager")

        bob = get_user_by_username("bob")
        assert bob is not None
        assert bob.username == "bob"
        assert bob.role == "manager"
        assert bob.is_active
        assert bob.check_password("pass456")
        assert not bob.check_password("wrong")

    def test_get_nonexistent_user(self):
        from models import init_db, get_user_by_username

        init_db()
        assert get_user_by_username("ghost") is None

    def test_get_user_by_id(self):
        from models import init_db, create_user, get_user_by_id

        init_db()
        create_user("carol", "pw789")
        conn = sqlite3.connect(DB_PATH)
        uid = conn.execute("SELECT id FROM users WHERE username='carol'").fetchone()[0]
        conn.close()

        user = get_user_by_id(uid)
        assert user is not None
        assert user.username == "carol"

    def test_update_user(self):
        from models import init_db, create_user, update_user, get_user_by_username

        init_db()
        create_user("dave", "oldpw")
        user = get_user_by_username("dave")
        update_user(user.id, password="newpw", role="admin")

        updated = get_user_by_username("dave")
        assert updated.check_password("newpw")
        assert updated.role == "admin"

    def test_delete_user(self):
        from models import init_db, create_user, delete_user, get_user_by_username

        init_db()
        create_user("eve", "pw")
        user = get_user_by_username("eve")
        assert user is not None

        delete_user(user.id)
        assert get_user_by_username("eve") is None

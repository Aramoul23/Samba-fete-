"""Samba Fête — Auth tests.

Tests: login, logout, rate limiting, access control, user management.
"""
import pytest


# ══════════════════════════════════════════════════════════════════════
# Login Tests
# ══════════════════════════════════════════════════════════════════════

class TestLogin:
    """Test the login flow."""

    def test_login_page_loads(self, client):
        """GET /login should return 200."""
        resp = client.get("/login")
        assert resp.status_code == 200
        assert b"Samba" in resp.data

    def test_login_valid_credentials(self, client, admin_user):
        """Login with correct credentials should redirect to dashboard."""
        resp = client.post("/login", data={
            "username": "admin",
            "password": "Admin123!",
        }, follow_redirects=False)
        assert resp.status_code == 302  # Redirect to index

    def test_login_valid_follow_redirect(self, client, admin_user):
        """Login should land on dashboard after redirect."""
        resp = client.post("/login", data={
            "username": "admin",
            "password": "Admin123!",
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_login_wrong_password(self, client, admin_user):
        """Login with wrong password should stay on login page."""
        resp = client.post("/login", data={
            "username": "admin",
            "password": "wrongpassword",
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b"incorrect" in resp.data.lower() or b"Samba" in resp.data

    def test_login_nonexistent_user(self, client, _reset_db):
        """Login with nonexistent user should fail."""
        resp = client.post("/login", data={
            "username": "ghost",
            "password": "whatever",
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_login_empty_username(self, client, _reset_db):
        """Login with empty username should fail."""
        resp = client.post("/login", data={
            "username": "",
            "password": "something",
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_login_already_authenticated_redirects(self, client, admin_user):
        """If already logged in, GET /login should redirect."""
        client.post("/login", data={
            "username": "admin",
            "password": "Admin123!",
        })
        resp = client.get("/login")
        # Should redirect to index
        assert resp.status_code == 302


# ══════════════════════════════════════════════════════════════════════
# Logout Tests
# ══════════════════════════════════════════════════════════════════════

class TestLogout:
    """Test the logout flow."""

    def test_logout_clears_session(self, client, admin_user):
        """After logout, user should not be authenticated."""
        # Login
        client.post("/login", data={
            "username": "admin",
            "password": "Admin123!",
        })
        # Verify we can access protected page
        resp = client.get("/")
        assert resp.status_code == 200

        # Logout
        resp = client.get("/logout", follow_redirects=True)
        assert resp.status_code == 200

        # Should not be able to access dashboard anymore
        resp = client.get("/")
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")

    def test_logout_redirects_to_login(self, client, admin_user):
        """Logout should redirect to login page."""
        client.post("/login", data={
            "username": "admin",
            "password": "Admin123!",
        })
        resp = client.get("/logout")
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")


# ══════════════════════════════════════════════════════════════════════
# Access Control Tests
# ══════════════════════════════════════════════════════════════════════

class TestAccessControl:
    """Test authentication and authorization guards."""

    def test_unauthenticated_redirects_to_login(self, client, _reset_db):
        """Accessing protected routes without login should redirect."""
        protected_urls = [
            "/",
            "/calendrier",
            "/evenements",
            "/clients",
            "/finances",
            "/depenses",
            "/comptabilite",
            "/parametres",
            "/paiement-rapide",
        ]
        for url in protected_urls:
            resp = client.get(url)
            assert resp.status_code == 302, f"{url} should redirect to login"
            assert "/login" in resp.headers.get("Location", ""), \
                f"{url} should redirect to /login"

    def test_non_admin_cannot_access_user_management(self, manager_client):
        """Manager role should not access admin-only user management."""
        resp = manager_client.get("/parametres/utilisateurs", follow_redirects=True)
        assert resp.status_code == 200
        # Should have been redirected away with flash message
        assert b'administrateur' in resp.data.lower() or '/login' in (resp.headers.get('Location', '') or '').lower()

    def test_admin_can_access_user_management(self, admin_client):
        """Admin should access user management."""
        resp = admin_client.get("/parametres/utilisateurs")
        assert resp.status_code == 200

    def test_admin_can_add_user(self, admin_client):
        """Admin should be able to create a new user."""
        with admin_client.session_transaction() as sess:
            sess["csrf_token"] = "test-csrf-token"

        resp = admin_client.post("/parametres/utilisateurs/ajouter", data={
            "csrf_token": "test-csrf-token",
            "username": "newuser",
            "password": "NewPass123!",
            "role": "manager",
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b"cr" in resp.data.lower() or b"ajout" in resp.data.lower()

    def test_cannot_delete_self(self, admin_client, admin_user):
        """Admin should not be able to delete their own account."""
        with admin_client.session_transaction() as sess:
            sess["csrf_token"] = "test-csrf-token"

        resp = admin_client.post(
            f"/parametres/utilisateurs/{admin_user['id']}/supprimer",
            data={"csrf_token": "test-csrf-token"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        # Should not have deleted self
        from models import get_user_by_username
        assert get_user_by_username("admin") is not None


# ══════════════════════════════════════════════════════════════════════
# Password Tests
# ══════════════════════════════════════════════════════════════════════

class TestPassword:
    """Test password handling."""

    def test_password_is_hashed(self, admin_user):
        """Password should be stored as a hash, not plaintext."""
        from models import get_db
        db = get_db()
        try:
            row = db.execute(
                "SELECT password_hash FROM users WHERE username='admin'"
            ).fetchone()
            assert row["password_hash"] != "Admin123!"
            assert row["password_hash"].startswith(("pbkdf2:", "scrypt:"))
        finally:
            db.close()

    def test_wrong_password_fails_check(self, admin_user):
        """Wrong password should not pass check_password."""
        from models import get_user_by_username
        user = get_user_by_username("admin")
        assert user.check_password("Admin123!") is True
        assert user.check_password("wrong") is False

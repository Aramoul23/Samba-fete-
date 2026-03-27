import os
import secrets
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

DATABASE_URL = os.environ.get("DATABASE_URL", "")


def is_postgres():
    """Vérifie si la base de données est PostgreSQL."""
    return DATABASE_URL.startswith("postgresql://")


class User:
    """User model for Flask-Login."""

    def __init__(self, id, username, password_hash, role, is_active=1):
        """Initialise un utilisateur avec ses attributs."""
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.role = role
        self._is_active = bool(is_active)

    @property
    def is_active(self):
        """Retourne si l'utilisateur est actif."""
        return self._is_active

    @property
    def is_authenticated(self):
        """Retourne si l'utilisateur est authentifié."""
        return True

    @property
    def is_anonymous(self):
        """Retourne si l'utilisateur est anonyme."""
        return False

    @property
    def is_admin(self):
        """Retourne si l'utilisateur est administrateur."""
        return self.role == "admin"

    def get_id(self):
        """Retourne l'identifiant de l'utilisateur."""
        return str(self.id)

    def check_password(self, password):
        """Vérifie si le mot de passe est correct."""
        return check_password_hash(self.password_hash, password)


class DB:
    """Database wrapper that works with both SQLite and PostgreSQL."""

    def __init__(self, conn, is_pg):
        """Initialise la connexion à la base de données."""
        self.conn = conn
        self.is_pg = is_pg
        self._lastrowid = None

    @property
    def lastrowid(self):
        """Return the last inserted row ID."""
        if self._lastrowid:
            return self._lastrowid
        cur = self.conn.cursor()
        if self.is_pg:
            cur.execute("SELECT LASTVAL()")
        else:
            cur.execute("SELECT LAST_INSERT_ROWID()")
        return cur.fetchone()[0]

    def execute(self, sql, params=None):
        """Execute SQL and return self for chaining."""
        if self.is_pg:
            # Convert ? to %s for PostgreSQL
            sql = sql.replace("?", "%s")
        cur = self.conn.cursor()
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        self._cur = cur
        # Store lastrowid for INSERT statements
        if sql.strip().upper().startswith("INSERT"):
            if self.is_pg:
                cur.execute("SELECT LASTVAL()")
            else:
                pass  # SQLite will use LAST_INSERT_ROWID() via property
            try:
                self._lastrowid = cur.fetchone()[0] if self.is_pg else None
            except (TypeError, IndexError):
                self._lastrowid = None
        return self

    def fetchone(self):
        """Fetch one row as dict."""
        row = self._cur.fetchone()
        if row is None:
            return None
        if self.is_pg:
            return dict(zip([col[0] for col in self._cur.description], row))
        else:
            return dict(row)

    def fetchall(self):
        """Fetch all rows as list of dicts."""
        rows = self._cur.fetchall()
        if self.is_pg:
            columns = [col[0] for col in self._cur.description]
            return [dict(zip(columns, row)) for row in rows]
        else:
            return [dict(row) for row in rows]

    def commit(self):
        """Valide les modifications dans la base de données."""
        self.conn.commit()
        return self

    def rollback(self):
        """Annule les modifications non validées."""
        self.conn.rollback()
        return self

    def close(self):
        """Ferme la connexion à la base de données."""
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.conn.rollback()
        self.close()
        return False


def get_db():
    """Établit et retourne une connexion à la base de données."""
    if is_postgres():
        import psycopg2

        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        return DB(conn, True)
    else:
        import sqlite3

        db_path = os.environ.get("SQLITE_DB_PATH")
        if not db_path:
            db_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "samba_fete.db"
            )
        conn = sqlite3.connect(db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return DB(conn, False)


def init_db():
    """Initialise la base de données et crée les tables par défaut."""
    db = get_db()

    if is_postgres():
        sqls = """
            CREATE TABLE IF NOT EXISTS venues (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                capacity_men INTEGER DEFAULT 0,
                capacity_women INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS clients (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                phone2 TEXT,
                email TEXT,
                address TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS events (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                client_id INTEGER REFERENCES clients(id),
                venue_id INTEGER REFERENCES venues(id),
                venue_id2 INTEGER REFERENCES venues(id),
                event_type TEXT NOT NULL,
                event_date TEXT NOT NULL,
                time_slot TEXT NOT NULL,
                guests_men INTEGER DEFAULT 0,
                guests_women INTEGER DEFAULT 0,
                status TEXT DEFAULT 'en attente',
                notes TEXT,
                total_amount NUMERIC DEFAULT 0,
                deposit_required NUMERIC DEFAULT 20000,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS event_lines (
                id SERIAL PRIMARY KEY,
                event_id INTEGER REFERENCES events(id) ON DELETE CASCADE,
                description TEXT NOT NULL,
                amount NUMERIC DEFAULT 0,
                is_cost INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                event_id INTEGER REFERENCES events(id) ON DELETE CASCADE,
                amount NUMERIC NOT NULL,
                payment_type TEXT DEFAULT 'Acompte',
                method TEXT DEFAULT 'Espèces',
                reference TEXT,
                notes TEXT,
                payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_refunded INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS expenses (
                id SERIAL PRIMARY KEY,
                event_id INTEGER REFERENCES events(id) ON DELETE CASCADE,
                category TEXT NOT NULL,
                description TEXT DEFAULT '',
                amount NUMERIC DEFAULT 0,
                expense_date TEXT DEFAULT CURRENT_DATE::TEXT,
                method TEXT DEFAULT 'espèces',
                reference TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'manager',
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """
        for sql in sqls.split(";"):
            sql = sql.strip()
            if sql:
                db.conn.cursor().execute(sql)
    else:
        db.conn.executescript("""
            CREATE TABLE IF NOT EXISTS venues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                capacity_men INTEGER DEFAULT 0,
                capacity_women INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                phone2 TEXT,
                email TEXT,
                address TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                client_id INTEGER NOT NULL,
                venue_id INTEGER NOT NULL,
                venue_id2 INTEGER,
                event_type TEXT NOT NULL,
                event_date TEXT NOT NULL,
                time_slot TEXT NOT NULL,
                guests_men INTEGER DEFAULT 0,
                guests_women INTEGER DEFAULT 0,
                status TEXT DEFAULT 'en attente',
                notes TEXT,
                total_amount REAL DEFAULT 0,
                deposit_required REAL DEFAULT 20000,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                updated_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (client_id) REFERENCES clients(id),
                FOREIGN KEY (venue_id) REFERENCES venues(id),
                FOREIGN KEY (venue_id2) REFERENCES venues(id)
            );
            CREATE TABLE IF NOT EXISTS event_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                amount REAL DEFAULT 0,
                is_cost INTEGER DEFAULT 0,
                FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                payment_type TEXT DEFAULT 'Acompte',
                method TEXT DEFAULT 'Espèces',
                reference TEXT,
                notes TEXT,
                payment_date TEXT DEFAULT (datetime('now','localtime')),
                is_refunded INTEGER DEFAULT 0,
                FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER,
                category TEXT NOT NULL,
                description TEXT DEFAULT '',
                amount REAL DEFAULT 0,
                expense_date TEXT DEFAULT (date('now','localtime')),
                method TEXT DEFAULT 'espèces',
                reference TEXT,
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'manager',
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );
        """)

    # Insert default data if empty
    count = db.execute("SELECT COUNT(*) as cnt FROM venues").fetchone()["cnt"]
    if count == 0:
        if is_postgres():
            db.execute(
                "INSERT INTO venues (name, capacity_men, capacity_women) VALUES ('Grande Salle', 400, 270)"
            )
            db.execute(
                "INSERT INTO venues (name, capacity_men, capacity_women) VALUES ('Jardin', 200, 150)"
            )
            db.execute(
                "INSERT INTO venues (name, capacity_men, capacity_women) VALUES ('Salle VIP', 50, 30)"
            )
        else:
            db.conn.executescript("""
                INSERT INTO venues (name, capacity_men, capacity_women) VALUES ('Grande Salle', 400, 270);
                INSERT INTO venues (name, capacity_men, capacity_women) VALUES ('Jardin', 200, 150);
                INSERT INTO venues (name, capacity_men, capacity_women) VALUES ('Salle VIP', 50, 30);
            """)

    count = db.execute("SELECT COUNT(*) as cnt FROM settings").fetchone()["cnt"]
    if count == 0:
        if is_postgres():
            db.execute(
                "INSERT INTO settings (key, value) VALUES ('deposit_min', '20000')"
            )
            db.execute("INSERT INTO settings (key, value) VALUES ('currency', 'DA')")
            db.execute(
                "INSERT INTO settings (key, value) VALUES ('hall_name', 'Samba Fête')"
            )
        else:
            db.conn.executescript("""
                INSERT INTO settings (key, value) VALUES ('deposit_min', '20000');
                INSERT INTO settings (key, value) VALUES ('currency', 'DA');
                INSERT INTO settings (key, value) VALUES ('hall_name', 'Samba Fête');
            """)

    # Create default admin user if users table is empty
    user_count = db.execute("SELECT COUNT(*) as cnt FROM users").fetchone()["cnt"]
    if user_count == 0:
        admin_pw = os.environ.get("ADMIN_PASSWORD", "Ramsys2020$")
        admin_hash = generate_password_hash(admin_pw)
        if is_postgres():
            db.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                ("admin", admin_hash, "admin"),
            )
        else:
            db.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                ("admin", admin_hash, "admin"),
            )
        import logging
        _logger = logging.getLogger(__name__)
        _logger.warning(
            "Default admin user created. Password: %s — "
            "Change it immediately or set ADMIN_PASSWORD env var.",
            admin_pw,
        )

    db.conn.commit()
    db.close()


def get_user_by_id(user_id):
    """Get user by ID for Flask-Login."""
    db = get_db()
    try:
        row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if row:
            return User(
                row["id"],
                row["username"],
                row["password_hash"],
                row["role"],
                row["is_active"],
            )
        return None
    finally:
        db.close()


def get_user_by_username(username):
    """Get user by username."""
    db = get_db()
    try:
        row = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if row:
            return User(
                row["id"],
                row["username"],
                row["password_hash"],
                row["role"],
                row["is_active"],
            )
        return None
    finally:
        db.close()


def get_all_users():
    """Get all users."""
    db = get_db()
    try:
        users = db.execute(
            "SELECT id, username, role, is_active, created_at FROM users ORDER BY id"
        ).fetchall()
        return users
    finally:
        db.close()


def create_user(username, password, role="manager"):
    """Create a new user."""
    db = get_db()
    try:
        password_hash = generate_password_hash(password)
        if is_postgres():
            db.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                (username, password_hash, role),
            )
        else:
            db.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, password_hash, role),
            )
        db.commit()
    finally:
        db.close()


def update_user(user_id, username=None, password=None, role=None, is_active=None):
    """Update user fields."""
    db = get_db()
    try:
        updates = []
        params = []

        if username:
            updates.append("username=?")
            params.append(username)
        if password:
            updates.append("password_hash=?")
            params.append(generate_password_hash(password))
        if role:
            updates.append("role=?")
            params.append(role)
        if is_active is not None:
            updates.append("is_active=?")
            params.append(1 if is_active else 0)

        if updates:
            params.append(user_id)
            sql = f"UPDATE users SET {', '.join(updates)} WHERE id=?"
            if is_postgres():
                sql = sql.replace("?", "%s")
            db.execute(sql, params)
            db.commit()
    finally:
        db.close()


def delete_user(user_id):
    """Delete a user."""
    db = get_db()
    try:
        db.execute("DELETE FROM users WHERE id=?", (user_id,))
        db.commit()
    finally:
        db.close()


def _executescript_pg(conn, sql):
    """Exécute un script SQL sur une connexion PostgreSQL."""
    for statement in sql.split(";"):
        statement = statement.strip()
        if statement:
            conn.cursor().execute(statement)


def get_setting(key, default=""):
    """Récupère la valeur d'un paramètre de configuration."""
    db = get_db()
    try:
        row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        db.close()


def set_setting(key, value):
    """Enregistre ou met à jour un paramètre de configuration."""
    db = get_db()
    try:
        if is_postgres():
            db.execute(
                "INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value=%s",
                (key, value, value),
            )
        else:
            db.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
            )
        db.commit()
    finally:
        db.close()

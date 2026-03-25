import os
import psycopg2
import psycopg2.extras
from datetime import datetime

DATABASE_URL = os.environ.get('DATABASE_URL', '')

def is_postgres():
    return DATABASE_URL.startswith('postgresql://')

class DB:
    """Database wrapper that works with both SQLite and PostgreSQL."""
    
    def __init__(self, conn, is_pg):
        self.conn = conn
        self.is_pg = is_pg
    
    def execute(self, sql, params=None):
        """Execute SQL and return self for chaining."""
        if self.is_pg:
            # Convert ? to %s for PostgreSQL
            sql = sql.replace('?', '%s')
        cur = self.conn.cursor()
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        self._cur = cur
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
        self.conn.commit()
        return self
    
    def close(self):
        self.conn.close()

def get_db():
    if is_postgres():
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        return DB(conn, True)
    else:
        import sqlite3
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'samba_fete.db')
        conn = sqlite3.connect(db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return DB(conn, False)

def init_db():
    db = get_db()
    
    if is_postgres():
        db.conn.cursor().executescript = lambda sql: _executescript_pg(db.conn, sql)
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
                amount NUMERIC DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                event_id INTEGER REFERENCES events(id) ON DELETE CASCADE,
                amount NUMERIC NOT NULL,
                payment_type TEXT DEFAULT 'Acompte',
                method TEXT DEFAULT 'Espèces',
                reference TEXT,
                notes TEXT,
                payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS expenses (
                id SERIAL PRIMARY KEY,
                event_id INTEGER REFERENCES events(id) ON DELETE CASCADE,
                category TEXT NOT NULL,
                amount NUMERIC DEFAULT 0,
                expense_date TEXT DEFAULT CURRENT_DATE::TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """
        for sql in sqls.split(';'):
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
                FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER,
                category TEXT NOT NULL,
                amount REAL DEFAULT 0,
                expense_date TEXT DEFAULT (date('now','localtime')),
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)
    
    # Insert default data if empty
    count = db.execute("SELECT COUNT(*) as cnt FROM venues").fetchone()['cnt']
    if count == 0:
        if is_postgres():
            db.execute("INSERT INTO venues (name, capacity_men, capacity_women) VALUES ('Grande Salle', 400, 270)")
            db.execute("INSERT INTO venues (name, capacity_men, capacity_women) VALUES ('Jardin', 200, 150)")
            db.execute("INSERT INTO venues (name, capacity_men, capacity_women) VALUES ('Salle VIP', 50, 30)")
        else:
            db.conn.executescript("""
                INSERT INTO venues (name, capacity_men, capacity_women) VALUES ('Grande Salle', 400, 270);
                INSERT INTO venues (name, capacity_men, capacity_women) VALUES ('Jardin', 200, 150);
                INSERT INTO venues (name, capacity_men, capacity_women) VALUES ('Salle VIP', 50, 30);
            """)
    
    count = db.execute("SELECT COUNT(*) as cnt FROM settings").fetchone()['cnt']
    if count == 0:
        if is_postgres():
            db.execute("INSERT INTO settings (key, value) VALUES ('deposit_min', '20000')")
            db.execute("INSERT INTO settings (key, value) VALUES ('currency', 'DA')")
            db.execute("INSERT INTO settings (key, value) VALUES ('hall_name', 'Samba Fête')")
        else:
            db.conn.executescript("""
                INSERT INTO settings (key, value) VALUES ('deposit_min', '20000');
                INSERT INTO settings (key, value) VALUES ('currency', 'DA');
                INSERT INTO settings (key, value) VALUES ('hall_name', 'Samba Fête');
            """)
    
    db.conn.commit()

def _executescript_pg(conn, sql):
    for statement in sql.split(';'):
        statement = statement.strip()
        if statement:
            conn.cursor().execute(statement)

def get_setting(key, default=''):
    db = get_db()
    row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    db.close()
    return row['value'] if row else default

def set_setting(key, value):
    db = get_db()
    if is_postgres():
        db.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value=%s", (key, value, value))
    else:
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    db.commit()
    db.close()

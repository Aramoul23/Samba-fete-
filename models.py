import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'samba_fete.db')

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.executescript('''
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
            amount REAL NOT NULL,
            is_cost INTEGER DEFAULT 0,
            FOREIGN KEY (event_id) REFERENCES events(id)
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            date TEXT DEFAULT (datetime('now','localtime')),
            method TEXT DEFAULT 'espèces',
            payment_type TEXT DEFAULT 'acompte',
            reference TEXT,
            is_refunded INTEGER DEFAULT 0,
            refund_date TEXT,
            refund_reason TEXT,
            notes TEXT,
            FOREIGN KEY (event_id) REFERENCES events(id)
        );

        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            expense_date TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            amount REAL NOT NULL,
            vendor TEXT,
            event_id INTEGER,
            method TEXT DEFAULT 'espèces',
            reference TEXT,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (event_id) REFERENCES events(id)
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    ''')

    # Migration: Add updated_at column if it doesn't exist
    try:
        cur.execute("SELECT updated_at FROM events LIMIT 1")
    except sqlite3.OperationalError:
        cur.execute("ALTER TABLE events ADD COLUMN updated_at TEXT DEFAULT (datetime('now','localtime'))")

    # Migration: Add refund columns to payments if they don't exist
    try:
        cur.execute("SELECT is_refunded FROM payments LIMIT 1")
    except sqlite3.OperationalError:
        cur.execute("ALTER TABLE payments ADD COLUMN is_refunded INTEGER DEFAULT 0")
        cur.execute("ALTER TABLE payments ADD COLUMN refund_date TEXT")
        cur.execute("ALTER TABLE payments ADD COLUMN refund_reason TEXT")
        cur.execute("ALTER TABLE payments ADD COLUMN notes TEXT")

    # Seed default venues
    cur.execute("SELECT COUNT(*) FROM venues")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO venues (name, capacity_men, capacity_women) VALUES (?, ?, ?)",
                    ('Grande Salle', 400, 270))
        cur.execute("INSERT INTO venues (name, capacity_men, capacity_women) VALUES (?, ?, ?)",
                    ('Jardin', 200, 150))
        cur.execute("INSERT INTO venues (name, capacity_men, capacity_women) VALUES (?, ?, ?)",
                    ('Chalet', 100, 80))

    # Seed default settings
    cur.execute("SELECT COUNT(*) FROM settings")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ('deposit_min', '20000'))
        cur.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ('currency', 'DA'))
        cur.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ('hall_name', 'Samba Fête'))

    conn.commit()
    conn.close()

def get_setting(key, default=''):
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row['value'] if row else default

def set_setting(key, value):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

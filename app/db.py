"""Samba Fête — Database helpers.

Thin wrapper around models.get_db() so blueprints can do:

    from app.db import get_db_connection

without importing from the top-level models module directly.
Also provides Flask g-based per-request connection pooling.
"""
from flask import g
from models import get_db


def get_db_connection():
    """Get DB connection (one per request, auto-closed via teardown)."""
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = get_db()
    return db


def close_db_connection(exception=None):
    """Close database connection at end of request."""
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()

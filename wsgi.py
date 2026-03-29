"""Samba Fête — WSGI entry point.

    Development:  python wsgi.py
    Production:   gunicorn wsgi:app
"""
from app import create_app  # noqa: F401

app = create_app()

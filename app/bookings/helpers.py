"""Samba Fête — Booking helpers.

Shared constants and service definitions for the bookings blueprint.
"""
import logging
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

# ─── Shared Constants ────────────────────────────────────────────────
TIME_SLOTS = ["Déjeuner", "Après-midi", "Dîner"]
EVENT_TYPES = ["Mariage", "Fiançailles", "Anniversaire", "Conférence", "Autre"]
EVENT_STATUSES = ["en attente", "confirmé"]
ALL_STATUSES = ["en attente", "confirmé", "changé de date", "terminé", "annulé"]
STATUS_TRANSITIONS = {
    "en attente": ["confirmé", "annulé"],
    "confirmé": ["annulé", "changé de date"],
    "changé de date": ["confirmé", "annulé"],
    "terminé": [],
    "annulé": [],
}
PAYMENT_METHODS = ["espèces", "chèque", "virement", "carte"]
MONTH_NAMES_FR = [
    "",
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]

# ─── Default Services ───────────────────────────────────────────────
# Each entry: (form_key, display_name, default_price)
# Used by insert_service_lines() to avoid 9x copy-paste blocks.
DEFAULT_SERVICES = [
    ("location",    "Location de la salle",   0),
    ("individuel",  "Service individuel",     5000),
    ("cafe",        "Service café",           10000),
    ("groupe",      "Groupe interdit",        15000),
    ("photo",       "Photo",                  8000),
    ("deco",        "Déco el Hana",           25000),
    ("panneaux",    "Panneaux de réception",  12000),
    ("table",       "Table d'honneur",        7000),
]

# Predefined service display names (for splitting event_lines
# into predefined vs custom in the edit form)
PREDEFINED_NAMES = [s[1] for s in DEFAULT_SERVICES] + ["Autre"]


def check_pending_events(db=None):
    """Return events 'en attente' for more than 48h (next 30 days only)."""
    from app.models import Event
    threshold = (datetime.now() - timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")
    future_date = (date.today() + timedelta(days=30)).isoformat()
    today = date.today().isoformat()

    return Event.query.filter(
        Event.status == "en attente",
        Event.event_date.between(today, future_date),
        Event.created_at < threshold,
    ).all()



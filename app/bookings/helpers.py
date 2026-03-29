"""Samba Fête — Booking helpers.

Shared constants, service definitions, and reusable DB operations
for the bookings blueprint. Eliminates duplicated service-line
insertion code.
"""
import logging
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

# ─── Shared Constants ────────────────────────────────────────────────
TIME_SLOTS = ["Déjeuner", "Après-midi", "Dîner"]
EVENT_TYPES = ["Mariage", "Fiançailles", "Anniversaire", "Conférence", "Autre"]
EVENT_STATUSES = ["en attente", "confirmé", "changé de date", "terminé", "annulé"]
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


def insert_service_lines(db, event_id, form_data):
    """Insert all checked service lines in a single loop.

    Replaces 9 duplicated if-blocks.  Reads checkboxes like
    ``service_individuel`` / ``price_individuel`` from the form data
    and inserts one event_lines row per checked service.

    Args:
        db:        DB wrapper (from get_db_connection).
        event_id:  int — the event to attach lines to.
        form_data: ImmutableMultiDict from request.form.
    """
    inserted = 0

    # Location is always included if price > 0 (no checkbox)
    price = form_data.get("price_location", 0, type=float)
    if price > 0:
        db.execute(
            "INSERT INTO event_lines (event_id, description, amount, is_cost) "
            "VALUES (?, ?, ?, 0)",
            (event_id, "Location de la salle", price),
        )
        inserted += 1

    # Checkbox-driven services
    for key, name, _default in DEFAULT_SERVICES:
        if key == "location":
            continue  # handled above
        if not form_data.get(f"service_{key}"):
            continue
        price = form_data.get(f"price_{key}", 0, type=float)
        if price > 0:
            db.execute(
                "INSERT INTO event_lines (event_id, description, amount, is_cost) "
                "VALUES (?, ?, ?, 0)",
                (event_id, name, price),
            )
            inserted += 1

    # "Autre" — custom name + price
    if form_data.get("service_autre"):
        autre_price = form_data.get("price_autre", 0, type=float)
        autre_name = form_data.get("autre_name", "").strip() or "Autre"
        if autre_price > 0:
            db.execute(
                "INSERT INTO event_lines (event_id, description, amount, is_cost) "
                "VALUES (?, ?, ?, 0)",
                (event_id, autre_name, autre_price),
            )
            inserted += 1

    # Free-form custom lines (repeating inputs: line_desc[], line_amount[], line_is_cost[])
    line_descs = form_data.getlist("line_desc[]")
    line_amounts = form_data.getlist("line_amount[]")
    line_costs = form_data.getlist("line_is_cost[]")

    for i, desc in enumerate(line_descs):
        if desc.strip():
            amount = float(line_amounts[i]) if i < len(line_amounts) else 0
            is_cost = 1 if str(i) in line_costs else 0
            db.execute(
                "INSERT INTO event_lines (event_id, description, amount, is_cost) "
                "VALUES (?, ?, ?, ?)",
                (event_id, desc.strip(), amount, is_cost),
            )
            inserted += 1

    return inserted


def validate_event_date(db, event_date, event_id=0):
    """Check for double-bookings on the same date.

    Returns:
        list of error strings (empty = no conflicts).
    """
    errors = []
    if not event_date:
        return errors

    conflict = db.execute(
        "SELECT e.id, e.title, e.status, COALESCE(v.name, '') as venue_name "
        "FROM events e LEFT JOIN venues v ON e.venue_id = v.id "
        "WHERE e.event_date = ? AND e.status IN ('confirmé', 'en attente') AND e.id != ?",
        (event_date, event_id or 0),
    ).fetchone()

    if conflict:
        venue_label = f" ({conflict['venue_name']})" if conflict["venue_name"] else ""
        if conflict["status"] == "confirmé":
            errors.append(
                f"⛔ Date déjà réservée! '{conflict['title']}' est prévu le "
                f"{event_date}{venue_label} — 🔒 Cette date est verrouillée"
            )
        else:
            errors.append(
                f"⚠️ Attention! '{conflict['title']}' est en attente pour le "
                f"{event_date}{venue_label} — La validation est en cours"
            )
    return errors


def check_pending_events(db):
    """Return events 'en attente' for more than 48h (next 30 days only)."""
    now = datetime.now()
    threshold = (now - timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")
    future_date = (date.today() + timedelta(days=30)).isoformat()
    today = date.today().isoformat()

    return db.execute(
        "SELECT id, title, created_at, event_date FROM events "
        "WHERE status = 'en attente' "
        "AND event_date BETWEEN ? AND ? "
        "AND created_at < ?",
        (today, future_date, threshold),
    ).fetchall()


def get_event_financials(db, event_id):
    """Complete financial summary for one event (single-connection version)."""
    revenue = db.execute(
        "SELECT COALESCE(SUM(amount), 0) as t FROM event_lines WHERE event_id=? AND is_cost=0",
        (event_id,),
    ).fetchone()["t"]

    costs = db.execute(
        "SELECT COALESCE(SUM(amount), 0) as t FROM event_lines WHERE event_id=? AND is_cost=1",
        (event_id,),
    ).fetchone()["t"]

    paid = db.execute(
        "SELECT COALESCE(SUM(amount), 0) as t FROM payments WHERE event_id=? AND is_refunded=0",
        (event_id,),
    ).fetchone()["t"]

    refunded = db.execute(
        "SELECT COALESCE(SUM(amount), 0) as t FROM payments WHERE event_id=? AND is_refunded=1",
        (event_id,),
    ).fetchone()["t"]

    event = db.execute("SELECT total_amount FROM events WHERE id=?", (event_id,)).fetchone()
    event_total = event["total_amount"] if event else 0

    return {
        "revenue": float(revenue),
        "costs": float(costs),
        "profit": float(revenue) - float(costs),
        "paid": float(paid),
        "remaining": round(float(event_total) - float(paid), 2),
        "refunded": float(refunded),
    }

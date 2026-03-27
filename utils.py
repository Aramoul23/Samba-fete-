"""Shared utility functions for Samba Fête."""

from datetime import datetime

MONTHS_FR = {
    1: "Janvier",
    2: "Février",
    3: "Mars",
    4: "Avril",
    5: "Mai",
    6: "Juin",
    7: "Juillet",
    8: "Août",
    9: "Septembre",
    10: "Octobre",
    11: "Novembre",
    12: "Décembre",
}


def format_da(amount):
    """Formate un montant en dinars algériens (DA)."""
    try:
        return f"{float(amount):,.0f} DA".replace(",", " ")
    except (ValueError, TypeError):
        return "0 DA"


def format_date_fr(date_str):
    """Formate une date au format français (jour mois année)."""
    try:
        if isinstance(date_str, str):
            d = datetime.strptime(date_str[:10], "%Y-%m-%d")
        else:
            d = date_str
        return f"{d.day} {MONTHS_FR.get(d.month, '')} {d.year}"
    except (ValueError, TypeError):
        return str(date_str)

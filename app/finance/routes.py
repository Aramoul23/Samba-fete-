"""Samba Fête — Finance routes.

Financial reports, accounting dashboard, expense management,
and all ODS/CSV export endpoints.
"""
import csv
import io
import logging
from datetime import date, datetime, timedelta

from flask import (
    Blueprint,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import login_required

from app.db import get_db_connection
from app.bookings.helpers import MONTH_NAMES_FR

from export_functions import (
    export_events_ods,
    export_clients_ods,
    export_payments_ods,
    export_financials_ods,
    export_expenses_ods,
    export_pl_report_ods,
)

logger = logging.getLogger(__name__)

bp = Blueprint("finance", __name__, template_folder="../templates")

# ─── Constants ───────────────────────────────────────────────────────
EXPENSE_CATEGORIES = ["Serveurs", "Nettoyeurs", "Sécurité", "Autre"]

try:
    import psycopg2, sqlite3
    DatabaseError = (sqlite3.Error, psycopg2.Error)
except ImportError:
    import sqlite3
    DatabaseError = (sqlite3.Error,)


# ─── Helpers ─────────────────────────────────────────────────────────
def _get_setting_db(db, key, default=""):
    row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


# ─── Dashboard (index) ──────────────────────────────────────────────
@bp.route("/")
@login_required
def dashboard():
    """Tableau de bord principal — KPIs, graphiques, événements à venir."""
    from app.bookings.helpers import check_pending_events

    db = get_db_connection()
    today = date.today()
    first_day = today.replace(day=1)
    last_day = (
        today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        if today.month == 12
        else today.replace(month=today.month + 1, day=1) - timedelta(days=1)
    )

    # Previous month range
    prev_month = today.month - 1 if today.month > 1 else 12
    prev_year = today.year if today.month > 1 else today.year - 1
    prev_first = date(prev_year, prev_month, 1)
    prev_last = (
        date(prev_year + 1, 1, 1) - timedelta(days=1)
        if prev_month == 12
        else date(prev_year, prev_month + 1, 1) - timedelta(days=1)
    )

    # ── Consolidated KPI query (replaces ~8 separate queries) ────────
    kpi = db.execute(
        "SELECT "
        "  (SELECT COUNT(*) FROM events "
        "   WHERE event_date BETWEEN ? AND ? AND status != 'annulé') as events_month, "
        "  (SELECT COALESCE(SUM(p.amount),0) FROM payments p "
        "   JOIN events e ON p.event_id=e.id "
        "   WHERE p.payment_date BETWEEN ? AND ? AND e.status != 'annulé' "
        "   AND p.is_refunded=0) as revenue_month, "
        "  (SELECT COALESCE(SUM(p.amount),0) FROM payments p "
        "   JOIN events e ON p.event_id=e.id "
        "   WHERE p.payment_date BETWEEN ? AND ? AND e.status != 'annulé' "
        "   AND p.is_refunded=0) as last_month_revenue, "
        "  (SELECT COALESCE(SUM(amount),0) FROM expenses "
        "   WHERE expense_date BETWEEN ? AND ?) as month_expenses, "
        "  (SELECT COUNT(*) FROM clients) as total_clients, "
        "  (SELECT COUNT(*) FROM events WHERE status != 'annulé') as total_events, "
        "  (SELECT COUNT(*) FROM events "
        "   WHERE status = 'en attente' AND event_date >= ?) as pending_count ",
        (first_day.isoformat(), last_day.isoformat(),   # events_month
         first_day.isoformat(), last_day.isoformat(),   # revenue_month
         prev_first.isoformat(), prev_last.isoformat(), # last_month_revenue
         first_day.isoformat(), last_day.isoformat(),   # month_expenses
         today.isoformat()),                            # pending_count
    ).fetchone()

    events_this_month = kpi["events_month"]
    revenue_month = kpi["revenue_month"]
    last_month_revenue = kpi["last_month_revenue"]
    month_expenses = kpi["month_expenses"]
    month_profit = float(revenue_month) - float(month_expenses)
    revenue_pct_change = (
        ((float(revenue_month) - float(last_month_revenue)) / float(last_month_revenue) * 100)
        if float(last_month_revenue) > 0
        else (100.0 if float(revenue_month) > 0 else 0.0)
    )

    # ── Upcoming events + recent payments (single query each) ────────
    upcoming = db.execute(
        "SELECT e.*, c.name as client_name, v.name as venue_name FROM events e "
        "JOIN clients c ON e.client_id=c.id JOIN venues v ON e.venue_id=v.id "
        "WHERE e.event_date >= ? AND e.status NOT IN ('annulé', 'terminé') "
        "ORDER BY e.event_date ASC LIMIT 5",
        (today.isoformat(),),
    ).fetchall()

    recent_payments = db.execute(
        "SELECT p.*, e.title, c.name as client_name FROM payments p "
        "JOIN events e ON p.event_id=e.id JOIN clients c ON e.client_id=c.id "
        "WHERE p.is_refunded=0 ORDER BY p.payment_date DESC LIMIT 5"
    ).fetchall()

    # Next event
    next_event = db.execute(
        "SELECT e.event_date, c.name as client_name FROM events e "
        "JOIN clients c ON e.client_id=c.id "
        "WHERE e.event_date >= ? AND e.status NOT IN ('annulé', 'terminé') "
        "ORDER BY e.event_date ASC LIMIT 1",
        (today.isoformat(),),
    ).fetchone()

    # ── 6-month chart data ───────────────────────────────────────────
    chart_labels, chart_revenues, chart_expenses, chart_profits = [], [], [], []
    for i in range(5, -1, -1):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        m_first = date(y, m, 1)
        m_last = (
            date(y + 1, 1, 1) - timedelta(days=1) if m == 12
            else date(y, m + 1, 1) - timedelta(days=1)
        )
        m_rev = db.execute(
            "SELECT COALESCE(SUM(p.amount),0) as s FROM payments p "
            "JOIN events e ON p.event_id=e.id "
            "WHERE p.payment_date BETWEEN ? AND ? AND e.status != 'annulé' AND p.is_refunded=0",
            (m_first.isoformat(), m_last.isoformat()),
        ).fetchone()["s"]
        m_exp = db.execute(
            "SELECT COALESCE(SUM(amount),0) as s FROM expenses "
            "WHERE expense_date BETWEEN ? AND ?",
            (m_first.isoformat(), m_last.isoformat()),
        ).fetchone()["s"]
        chart_labels.append(MONTH_NAMES_FR[m][:3])
        chart_revenues.append(float(m_rev))
        chart_expenses.append(float(m_exp))
        chart_profits.append(float(m_rev) - float(m_exp))

    # ── Upcoming with paid amounts (batch query) ─────────────────────
    upcoming_ids = [ev["id"] for ev in upcoming]
    payments_map = {}
    if upcoming_ids:
        ph = ",".join("?" * len(upcoming_ids))
        rows = db.execute(
            f"SELECT event_id, COALESCE(SUM(amount),0) as tp FROM payments "
            f"WHERE event_id IN ({ph}) AND is_refunded=0 GROUP BY event_id",
            upcoming_ids,
        ).fetchall()
        payments_map = {r["event_id"]: float(r["tp"]) for r in rows}

    upcoming_with_revenue = []
    for ev in upcoming:
        ev_dict = ev
        ev_dict["paid"] = payments_map.get(ev["id"], 0.0)
        upcoming_with_revenue.append(ev_dict)

    hall_name = _get_setting_db(db, "hall_name", "Samba Fête")
    currency = _get_setting_db(db, "currency", "DA")

    return render_template(
        "finance/index.html",
        events_this_month=events_this_month,
        revenue_month=revenue_month,
        upcoming=upcoming,
        total_clients=kpi["total_clients"],
        total_events=kpi["total_events"],
        recent_payments=recent_payments,
        today=today,
        hall_name=hall_name,
        currency=currency,
        month_name=MONTH_NAMES_FR[today.month],
        pending_needs_attention=check_pending_events(db),
        last_month_revenue=last_month_revenue,
        month_expenses=month_expenses,
        month_profit=month_profit,
        revenue_pct_change=revenue_pct_change,
        pending_count=kpi["pending_count"],
        next_event=next_event,
        chart_labels=chart_labels,
        chart_revenues=chart_revenues,
        chart_expenses=chart_expenses,
        chart_profits=chart_profits,
        upcoming_with_revenue=upcoming_with_revenue,
    )


# ─── Financial Reports ──────────────────────────────────────────────
@bp.route("/finances")
@login_required
def financials():
    """Rapport financier avec revenus, bénéfices, et export CSV."""
    db = get_db_connection()

    start_date = request.args.get(
        "start_date", (date.today() - timedelta(days=365)).isoformat()
    )
    end_date = request.args.get("end_date", date.today().isoformat())
    export_csv = request.args.get("export", type=int)

    total_revenue = db.execute(
        "SELECT COALESCE(SUM(p.amount),0) as s FROM payments p "
        "JOIN events e ON p.event_id=e.id "
        "WHERE p.payment_date BETWEEN ? AND ? AND p.is_refunded=0",
        (start_date, end_date),
    ).fetchone()["s"]

    total_outstanding = db.execute(
        "SELECT COALESCE(SUM(e.total_amount - COALESCE(p.paid_total, 0)), 0) as s "
        "FROM events e "
        "LEFT JOIN (SELECT event_id, SUM(amount) as paid_total FROM payments "
        "WHERE is_refunded=0 GROUP BY event_id) p ON p.event_id = e.id "
        "WHERE e.event_date BETWEEN ? AND ? AND e.status NOT IN ('annulé', 'terminé')",
        (start_date, end_date),
    ).fetchone()["s"]

    total_refunded = db.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM payments "
        "WHERE payment_date BETWEEN ? AND ? AND is_refunded=1",
        (start_date, end_date),
    ).fetchone()["s"]

    revenue_by_type = db.execute(
        "SELECT e.event_type, COALESCE(SUM(p.amount), 0) as revenue, "
        "COUNT(DISTINCT e.id) as count "
        "FROM events e "
        "LEFT JOIN payments p ON p.event_id = e.id AND p.is_refunded = 0 "
        "WHERE e.event_date BETWEEN ? AND ? AND e.status != 'annulé' "
        "GROUP BY e.event_type ORDER BY revenue DESC",
        (start_date, end_date),
    ).fetchall()

    top_clients = db.execute(
        "SELECT c.id, c.name, "
        "COALESCE(SUM(e.total_amount), 0) as total_billed, "
        "COALESCE(SUM(CASE WHEN p.is_refunded=0 THEN p.amount ELSE 0 END), 0) as total_paid, "
        "COALESCE(SUM(e.total_amount), 0) - "
        "COALESCE(SUM(CASE WHEN p.is_refunded=0 THEN p.amount ELSE 0 END), 0) as total_remaining "
        "FROM clients c JOIN events e ON e.client_id = c.id "
        "LEFT JOIN payments p ON p.event_id = e.id "
        "WHERE e.event_date BETWEEN ? AND ? "
        "GROUP BY c.id, c.name "
        "HAVING COALESCE(SUM(e.total_amount), 0) > 0 "
        "ORDER BY total_billed DESC LIMIT 10",
        (start_date, end_date),
    ).fetchall()

    payments = db.execute(
        "SELECT p.*, e.title, e.event_date, c.name as client_name "
        "FROM payments p JOIN events e ON p.event_id = e.id "
        "JOIN clients c ON e.client_id = c.id "
        "WHERE p.payment_date BETWEEN ? AND ? ORDER BY p.payment_date DESC",
        (start_date, end_date),
    ).fetchall()

    event_financials_raw = db.execute(
        "SELECT e.id, e.title, e.event_date, e.event_type, e.status, e.total_amount, "
        "c.name as client_name, "
        "COALESCE(SUM(CASE WHEN el.is_cost=0 THEN el.amount ELSE 0 END), 0) as total_revenue, "
        "COALESCE(SUM(CASE WHEN el.is_cost=1 THEN el.amount ELSE 0 END), 0) as total_costs, "
        "COALESCE((SELECT SUM(p.amount) FROM payments p "
        "WHERE p.event_id=e.id AND p.is_refunded=0), 0) as total_paid "
        "FROM events e JOIN clients c ON e.client_id = c.id "
        "LEFT JOIN event_lines el ON el.event_id = e.id "
        "WHERE e.event_date BETWEEN ? AND ? AND e.status != 'annulé' "
        "GROUP BY e.id ORDER BY e.event_date DESC",
        (start_date, end_date),
    ).fetchall()

    event_financials_list = []
    for ef in event_financials_raw:
        d = ef
        d["total_revenue"] = float(d["total_revenue"])
        d["total_costs"] = float(d["total_costs"])
        d["total_paid"] = float(d["total_paid"])
        d["total_amount"] = float(d["total_amount"])
        d["profit"] = d["total_revenue"] - d["total_costs"]
        d["remaining"] = round(d["total_amount"] - d["total_paid"], 2)
        event_financials_list.append(d)

    total_profit = sum(ef["profit"] for ef in event_financials_list)

    if export_csv:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Date", "Événement", "Client", "Type", "Revenus",
                         "Coûts", "Bénéfice", "Payé", "Reste", "Statut"])
        for ef in event_financials_list:
            writer.writerow([
                ef["event_date"][:10], ef["title"], ef["client_name"],
                ef["event_type"], ef["total_revenue"], ef["total_costs"],
                ef["profit"], ef["total_paid"], ef["remaining"], ef["status"],
            ])
        resp = make_response(output.getvalue())
        resp.headers["Content-Type"] = "text/csv; charset=utf-8"
        resp.headers["Content-Disposition"] = (
            f"attachment; filename=finances_{start_date}_{end_date}.csv")
        return resp

    return render_template(
        "finance/financials.html",
        start_date=start_date, end_date=end_date,
        total_revenue=total_revenue, total_outstanding=total_outstanding,
        total_refunded=total_refunded, total_profit=total_profit,
        revenue_by_type=revenue_by_type, top_clients=top_clients,
        payments=payments, event_financials=event_financials_list,
    )


# ─── Accounting P&L ─────────────────────────────────────────────────
@bp.route("/comptabilite")
@login_required
def accounting():
    """Tableau de bord comptabilité avec P&L mensuel."""
    db = get_db_connection()

    start_date = request.args.get(
        "start_date", (date.today() - timedelta(days=365)).isoformat()
    )
    end_date = request.args.get("end_date", date.today().isoformat())

    total_income = float(db.execute(
        "SELECT COALESCE(SUM(p.amount),0) as s FROM payments p "
        "WHERE p.payment_date BETWEEN ? AND ? AND p.is_refunded=0",
        (start_date, end_date),
    ).fetchone()["s"] or 0)

    total_expenses = float(db.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM expenses "
        "WHERE expense_date BETWEEN ? AND ?",
        (start_date, end_date),
    ).fetchone()["s"] or 0)

    net_profit = total_income - total_expenses
    profit_margin = (net_profit / total_income * 100) if total_income > 0 else 0

    expenses_by_category = [
        {"category": r["category"], "total": float(r["total"] or 0), "count": r["count"]}
        for r in db.execute(
            "SELECT category, SUM(amount) as total, COUNT(*) as count "
            "FROM expenses WHERE expense_date BETWEEN ? AND ? "
            "GROUP BY category ORDER BY total DESC",
            (start_date, end_date),
        ).fetchall()
    ]

    # Monthly P&L
    monthly_pl = []
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    current = start.replace(day=1)
    while current <= end:
        ms = current.strftime("%Y-%m-%d")
        me = (current.replace(year=current.year + 1, month=1, day=1) - timedelta(days=1)
              if current.month == 12
              else current.replace(month=current.month + 1, day=1) - timedelta(days=1))
        me_s = me.strftime("%Y-%m-%d")

        mi = float(db.execute(
            "SELECT COALESCE(SUM(p.amount),0) as s FROM payments p "
            "WHERE p.payment_date >= ? AND p.payment_date <= ? AND p.is_refunded=0",
            (ms, me_s),
        ).fetchone()["s"] or 0)

        mx = float(db.execute(
            "SELECT COALESCE(SUM(amount),0) as s FROM expenses "
            "WHERE expense_date >= ? AND expense_date <= ?",
            (ms, me_s),
        ).fetchone()["s"] or 0)

        mp = mi - mx
        monthly_pl.append({
            "month": ms[:7],
            "month_name": f"{MONTH_NAMES_FR[current.month]} {current.year}",
            "income": mi, "expenses": mx,
            "profit": mp,
            "margin": (mp / mi * 100) if mi > 0 else 0,
        })
        current = (current.replace(year=current.year + 1, month=1)
                   if current.month == 12
                   else current.replace(month=current.month + 1))

    monthly_pl.reverse()

    return render_template(
        "finance/accounting.html",
        start_date=start_date, end_date=end_date,
        total_income=total_income, total_expenses=total_expenses,
        net_profit=net_profit, profit_margin=profit_margin,
        expenses_by_category=expenses_by_category, monthly_pl=monthly_pl,
    )


# ─── Expenses CRUD ───────────────────────────────────────────────────
@bp.route("/depenses")
@login_required
def expenses():
    """Liste des dépenses avec filtres."""
    db = get_db_connection()

    start_date = request.args.get(
        "start_date", (date.today() - timedelta(days=30)).isoformat())
    end_date = request.args.get("end_date", date.today().isoformat())
    category_filter = request.args.get("category", "")

    query = ("SELECT ex.*, e.title as event_title FROM expenses ex "
             "LEFT JOIN events e ON ex.event_id = e.id WHERE 1=1")
    params = []
    if start_date:
        query += " AND ex.expense_date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND ex.expense_date <= ?"
        params.append(end_date)
    if category_filter:
        query += " AND ex.category = ?"
        params.append(category_filter)
    query += " ORDER BY ex.expense_date DESC"
    all_expenses = db.execute(query, params).fetchall()

    total_expenses_sum = sum(float(e["amount"]) for e in all_expenses)
    today = date.today()
    month_start = today.replace(day=1).isoformat()
    month_exp = float(db.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM expenses WHERE expense_date >= ?",
        (month_start,),
    ).fetchone()["s"] or 0)

    expenses_by_category = [
        {"category": r["category"], "total": float(r["total"] or 0), "count": r["count"]}
        for r in db.execute(
            "SELECT category, SUM(amount) as total, COUNT(*) as count "
            "FROM expenses WHERE expense_date >= ? AND expense_date <= ? "
            "GROUP BY category ORDER BY total DESC",
            (start_date, end_date),
        ).fetchall()
    ]

    recent_events = db.execute(
        "SELECT id, title, event_date FROM events ORDER BY event_date DESC LIMIT 20"
    ).fetchall()

    return render_template(
        "finance/expenses.html",
        expenses=all_expenses,
        start_date=start_date, end_date=end_date,
        category_filter=category_filter,
        categories=EXPENSE_CATEGORIES,
        total_expenses=total_expenses_sum,
        expenses_this_month=month_exp,
        avg_expense=total_expenses_sum / len(all_expenses) if all_expenses else 0,
        expenses_by_category=expenses_by_category,
        recent_events=recent_events,
        today_str=today.isoformat(),
    )


@bp.route("/depenses/ajouter", methods=["POST"])
@login_required
def add_expense():
    """Ajouter une dépense."""
    try:
        db = get_db_connection()
        expense_date = request.form.get("expense_date", date.today().isoformat())
        category = request.form.get("category", "")
        description = request.form.get("description", "").strip()
        amount = request.form.get("amount", 0, type=float)
        event_id = request.form.get("event_id", type=int) or None
        method = request.form.get("method", "espèces")
        reference = request.form.get("reference", "").strip()
        notes = request.form.get("notes", "").strip()

        if not category:
            flash("La catégorie est requise", "danger")
            return redirect(url_for("finance.expenses"))
        if amount <= 0:
            flash("Le montant doit être supérieur à 0", "danger")
            return redirect(url_for("finance.expenses"))

        if category == "Autre" and description:
            description = f"Autre: {description}"

        db.execute(
            "INSERT INTO expenses (expense_date, category, description, amount, "
            "event_id, method, reference, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (expense_date, category, description, amount, event_id, method, reference, notes),
        )
        db.commit()
        flash("Dépense enregistrée!", "success")
    except (DatabaseError, ValueError):
        db.rollback()
        logger.exception("Failed to add expense")
        flash("Erreur lors de l'enregistrement de la dépense.", "danger")
    return redirect(url_for("finance.expenses"))


@bp.route("/depense/<int:expense_id>/supprimer", methods=["POST"])
@login_required
def delete_expense(expense_id):
    """Supprimer une dépense."""
    try:
        db = get_db_connection()
        expense = db.execute(
            "SELECT event_id FROM expenses WHERE id=?", (expense_id,)
        ).fetchone()
        if expense:
            db.execute("DELETE FROM expenses WHERE id=?", (expense_id,))
            db.commit()
            flash("Dépense supprimée", "success")
            if expense["event_id"]:
                return redirect(url_for("bookings.event_detail",
                                        event_id=expense["event_id"]))
        else:
            flash("Dépense introuvable", "danger")
    except DatabaseError:
        db.rollback()
        logger.exception("Failed to delete expense %s", expense_id)
        flash("Erreur lors de la suppression.", "danger")
    return redirect(url_for("finance.expenses"))


# ─── Export: Events ──────────────────────────────────────────────────
@bp.route("/export/events.ods")
@login_required
def export_events():
    db = get_db_connection()
    sf = request.args.get("status", "")
    search = request.args.get("q", "").strip()
    query = ("SELECT e.*, c.name as client_name, v.name as venue_name, "
             "(SELECT COALESCE(SUM(p.amount),0) FROM payments p "
             "WHERE p.event_id=e.id AND p.is_refunded=0) as total_paid "
             "FROM events e JOIN clients c ON e.client_id=c.id "
             "JOIN venues v ON e.venue_id=v.id WHERE 1=1")
    params = []
    if sf:
        query += " AND e.status=?"
        params.append(sf)
    if search:
        query += " AND (e.title LIKE ? OR c.name LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    query += " ORDER BY e.event_date DESC"
    events = db.execute(query, params).fetchall()
    ods = export_events_ods(events, datetime.now().strftime("%Y-%m-%d %H:%M"))
    resp = make_response(ods)
    resp.headers["Content-Type"] = "application/vnd.oasis.opendocument.spreadsheet"
    resp.headers["Content-Disposition"] = (
        f"attachment; filename=evenements_{date.today().isoformat()}.ods")
    return resp


# ─── Export: Clients ─────────────────────────────────────────────────
@bp.route("/export/clients.ods")
@login_required
def export_clients():
    db = get_db_connection()
    search = request.args.get("q", "").strip()
    query = ("SELECT c.*, "
             "(SELECT COUNT(*) FROM events WHERE client_id=c.id) as event_count, "
             "(SELECT COALESCE(SUM(CASE WHEN p.is_refunded=0 THEN p.amount ELSE 0 END),0) "
             "FROM payments p JOIN events e ON p.event_id=e.id WHERE e.client_id=c.id) as total_paid, "
             "(SELECT COALESCE(SUM(e.total_amount),0) FROM events e "
             "WHERE e.client_id=c.id) as total_owed FROM clients c WHERE 1=1")
    params = []
    if search:
        query += " AND (c.name LIKE ? OR c.phone LIKE ? OR c.email LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    query += " ORDER BY c.created_at DESC"
    clients = db.execute(query, params).fetchall()
    ods = export_clients_ods(clients, datetime.now().strftime("%Y-%m-%d %H:%M"))
    resp = make_response(ods)
    resp.headers["Content-Type"] = "application/vnd.oasis.opendocument.spreadsheet"
    resp.headers["Content-Disposition"] = (
        f"attachment; filename=clients_{date.today().isoformat()}.ods")
    return resp


# ─── Export: Payments ────────────────────────────────────────────────
@bp.route("/export/payments.ods")
@login_required
def export_payments():
    db = get_db_connection()
    sd = request.args.get("start_date", "")
    ed = request.args.get("end_date", "")
    query = ("SELECT p.*, e.title, e.event_date, c.name as client_name "
             "FROM payments p JOIN events e ON p.event_id = e.id "
             "JOIN clients c ON e.client_id = c.id WHERE 1=1")
    params = []
    if sd:
        query += " AND p.payment_date >= ?"
        params.append(sd)
    if ed:
        query += " AND p.payment_date <= ?"
        params.append(ed + " 23:59:59")
    query += " ORDER BY p.payment_date DESC"
    payments = db.execute(query, params).fetchall()
    ods = export_payments_ods(payments, datetime.now().strftime("%Y-%m-%d %H:%M"))
    resp = make_response(ods)
    resp.headers["Content-Type"] = "application/vnd.oasis.opendocument.spreadsheet"
    resp.headers["Content-Disposition"] = (
        f"attachment; filename=paiements_{date.today().isoformat()}.ods")
    return resp


# ─── Export: Finances ────────────────────────────────────────────────
@bp.route("/export/finances.ods")
@login_required
def export_finances():
    db = get_db_connection()
    sd = request.args.get("start_date", (date.today() - timedelta(days=365)).isoformat())
    ed = request.args.get("end_date", date.today().isoformat())

    ef = db.execute(
        "SELECT e.id, e.title, e.event_date, e.event_type, e.status, e.total_amount, "
        "c.name as client_name, "
        "COALESCE(SUM(CASE WHEN el.is_cost=0 THEN el.amount ELSE 0 END), 0) as total_revenue, "
        "COALESCE(SUM(CASE WHEN el.is_cost=1 THEN el.amount ELSE 0 END), 0) as total_costs, "
        "COALESCE((SELECT SUM(p.amount) FROM payments p "
        "WHERE p.event_id=e.id AND p.is_refunded=0), 0) as total_paid "
        "FROM events e JOIN clients c ON e.client_id = c.id "
        "LEFT JOIN event_lines el ON el.event_id = e.id "
        "WHERE e.event_date BETWEEN ? AND ? AND e.status != 'annulé' "
        "GROUP BY e.id ORDER BY e.event_date DESC",
        (sd, ed),
    ).fetchall()

    tr = db.execute(
        "SELECT COALESCE(SUM(p.amount),0) as s FROM payments p "
        "WHERE p.payment_date BETWEEN ? AND ? AND p.is_refunded=0",
        (sd, ed),
    ).fetchone()["s"]

    to_ = db.execute(
        "SELECT COALESCE(SUM(e.total_amount - COALESCE(p.paid_total, 0)), 0) as s "
        "FROM events e LEFT JOIN (SELECT event_id, SUM(amount) as paid_total "
        "FROM payments WHERE is_refunded=0 GROUP BY event_id) p ON p.event_id = e.id "
        "WHERE e.event_date BETWEEN ? AND ? AND e.status NOT IN ('annulé', 'terminé')",
        (sd, ed),
    ).fetchone()["s"]

    ods = export_financials_ods(
        ef, {"total_revenue": tr, "total_outstanding": to_,
             "period_start": sd, "period_end": ed},
        datetime.now().strftime("%Y-%m-%d %H:%M"))
    resp = make_response(ods)
    resp.headers["Content-Type"] = "application/vnd.oasis.opendocument.spreadsheet"
    resp.headers["Content-Disposition"] = (
        f"attachment; filename=finances_{sd}_{ed}.ods")
    return resp


# ─── Export: Expenses ────────────────────────────────────────────────
@bp.route("/export/expenses.ods")
@login_required
def export_expenses():
    db = get_db_connection()
    sd = request.args.get("start_date", (date.today() - timedelta(days=365)).isoformat())
    ed = request.args.get("end_date", date.today().isoformat())
    cat = request.args.get("category", "")
    query = ("SELECT ex.*, e.title as event_title FROM expenses ex "
             "LEFT JOIN events e ON ex.event_id = e.id WHERE 1=1")
    params = []
    if sd:
        query += " AND ex.expense_date >= ?"
        params.append(sd)
    if ed:
        query += " AND ex.expense_date <= ?"
        params.append(ed)
    if cat:
        query += " AND ex.category = ?"
        params.append(cat)
    query += " ORDER BY ex.expense_date DESC"
    exps = db.execute(query, params).fetchall()
    ods = export_expenses_ods(exps, datetime.now().strftime("%Y-%m-%d %H:%M"))
    resp = make_response(ods)
    resp.headers["Content-Type"] = "application/vnd.oasis.opendocument.spreadsheet"
    resp.headers["Content-Disposition"] = (
        f"attachment; filename=depenses_{sd}_{ed}.ods")
    return resp


# ─── Export: P&L ─────────────────────────────────────────────────────
@bp.route("/export/pl.ods")
@login_required
def export_pl():
    db = get_db_connection()
    sd = request.args.get("start_date", (date.today() - timedelta(days=365)).isoformat())
    ed = request.args.get("end_date", date.today().isoformat())

    monthly_data = []
    current = datetime.strptime(sd, "%Y-%m-%d").replace(day=1)
    end = datetime.strptime(ed, "%Y-%m-%d")
    while current <= end:
        ms = current.strftime("%Y-%m-%d")
        me = (current.replace(year=current.year + 1, month=1, day=1) - timedelta(days=1)
              if current.month == 12
              else current.replace(month=current.month + 1, day=1) - timedelta(days=1))
        me_s = me.strftime("%Y-%m-%d")
        mi = float(db.execute(
            "SELECT COALESCE(SUM(p.amount),0) as s FROM payments p "
            "WHERE p.payment_date >= ? AND p.payment_date <= ? AND p.is_refunded=0",
            (ms, me_s),
        ).fetchone()["s"] or 0)
        mx = float(db.execute(
            "SELECT COALESCE(SUM(amount),0) as s FROM expenses "
            "WHERE expense_date >= ? AND expense_date <= ?",
            (ms, me_s),
        ).fetchone()["s"] or 0)
        monthly_data.append({
            "month": f"{MONTH_NAMES_FR[current.month]} {current.year}",
            "income": mi, "expenses": mx,
        })
        current = (current.replace(year=current.year + 1, month=1)
                   if current.month == 12
                   else current.replace(month=current.month + 1))
    monthly_data.reverse()
    ods = export_pl_report_ods(monthly_data, datetime.now().strftime("%Y-%m-%d %H:%M"))
    resp = make_response(ods)
    resp.headers["Content-Type"] = "application/vnd.oasis.opendocument.spreadsheet"
    resp.headers["Content-Disposition"] = (
        f"attachment; filename=rapport_pl_{sd}_{ed}.ods")
    return resp

"""Samba Fête — Finance routes (SQLAlchemy ORM).

Financial reports, accounting dashboard, expense management,
and all ODS/CSV export endpoints.
"""
import csv
import io
import logging
from datetime import date, datetime, timedelta

from flask import Blueprint, flash, make_response, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import func, case

from app.auth.decorators import admin_required
from app.models import db, Event, Client, EventLine, Payment, Expense, Venue, Setting
from app.bookings.helpers import MONTH_NAMES_FR
from export_functions import (
    export_events_ods, export_clients_ods, export_payments_ods,
    export_financials_ods, export_expenses_ods, export_pl_report_ods,
)

logger = logging.getLogger(__name__)
bp = Blueprint("finance", __name__, template_folder="../templates")
EXPENSE_CATEGORIES = ["Serveurs", "Nettoyeurs", "Sécurité", "Autre"]


# ─── Dashboard ───────────────────────────────────────────────────────
@bp.route("/")
@login_required
def dashboard():
    from app.bookings.helpers import check_pending_events
    today = date.today()
    first_day = today.replace(day=1)
    last_day = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1) if today.month == 12 else today.replace(month=today.month + 1, day=1) - timedelta(days=1)

    pm = today.month - 1 if today.month > 1 else 12
    py = today.year if today.month > 1 else today.year - 1
    pf = date(py, pm, 1)
    pl = date(py + 1, 1, 1) - timedelta(days=1) if pm == 12 else date(py, pm + 1, 1) - timedelta(days=1)

    events_this_month = Event.query.filter(Event.event_date.between(first_day.isoformat(), last_day.isoformat()), Event.status != "annulé").count()
    revenue_month = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).join(Event).filter(
        Payment.payment_date.between(first_day.isoformat(), last_day.isoformat()),
        Event.status != "annulé", Payment.is_refunded == 0).scalar()
    last_month_revenue = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).join(Event).filter(
        Payment.payment_date.between(pf.isoformat(), pl.isoformat()),
        Event.status != "annulé", Payment.is_refunded == 0).scalar()
    month_expenses = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.expense_date.between(first_day.isoformat(), last_day.isoformat())).scalar()
    month_profit = float(revenue_month) - float(month_expenses)
    revenue_pct_change = ((float(revenue_month) - float(last_month_revenue)) / float(last_month_revenue) * 100) if float(last_month_revenue) > 0 else (100.0 if float(revenue_month) > 0 else 0.0)

    upcoming = Event.query.join(Client).join(Venue, Event.venue_id == Venue.id).filter(
        Event.event_date >= today.isoformat(), Event.status.notin_(["annulé", "terminé"])
    ).order_by(Event.event_date).limit(5).all()
    recent_payments = Payment.query.join(Event).join(Client).filter(
        Payment.is_refunded == 0).order_by(Payment.payment_date.desc()).limit(5).all()

    pending_count = Event.query.filter(Event.status == "en attente", Event.event_date >= today.isoformat()).count()
    next_event = Event.query.join(Client).filter(
        Event.event_date >= today.isoformat(), Event.status.notin_(["annulé", "terminé"])
    ).order_by(Event.event_date).first()

    # Chart data
    chart_labels, chart_revenues, chart_expenses, chart_profits = [], [], [], []
    for i in range(5, -1, -1):
        m, y = today.month - i, today.year
        while m <= 0: m, y = m + 12, y - 1
        mf, ml = date(y, m, 1), (date(y + 1, 1, 1) - timedelta(days=1) if m == 12 else date(y, m + 1, 1) - timedelta(days=1))
        mr = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).join(Event).filter(
            Payment.payment_date.between(mf.isoformat(), ml.isoformat()), Event.status != "annulé", Payment.is_refunded == 0).scalar()
        me = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
            Expense.expense_date.between(mf.isoformat(), ml.isoformat())).scalar()
        chart_labels.append(MONTH_NAMES_FR[m][:3])
        chart_revenues.append(float(mr)); chart_expenses.append(float(me)); chart_profits.append(float(mr) - float(me))

    upcoming_with_revenue = []
    for ev in upcoming:
        ev.paid = ev.total_paid
        upcoming_with_revenue.append(ev)

    return render_template(
        "finance/index.html",
        events_this_month=events_this_month, revenue_month=revenue_month,
        upcoming=upcoming, total_clients=Client.query.count(),
        total_events=Event.query.filter(Event.status != "annulé").count(),
        recent_payments=recent_payments, today=today,
        hall_name=Setting.get("hall_name", "Samba Fête"), currency=Setting.get("currency", "DA"),
        month_name=MONTH_NAMES_FR[today.month], pending_needs_attention=check_pending_events(),
        last_month_revenue=last_month_revenue, month_expenses=month_expenses,
        month_profit=month_profit, revenue_pct_change=revenue_pct_change,
        pending_count=pending_count, next_event=next_event,
        chart_labels=chart_labels, chart_revenues=chart_revenues,
        chart_expenses=chart_expenses, chart_profits=chart_profits,
        upcoming_with_revenue=upcoming_with_revenue,
    )


# ─── Financial Reports ───────────────────────────────────────────────
@bp.route("/finances")
@login_required
def financials():
    sd = request.args.get("start_date", (date.today() - timedelta(days=365)).isoformat())
    ed = request.args.get("end_date", date.today().isoformat())
    export_csv = request.args.get("export", type=int)

    total_revenue = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).join(Event).filter(
        Payment.payment_date.between(sd, ed), Payment.is_refunded == 0).scalar()
    total_refunded = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.payment_date.between(sd, ed), Payment.is_refunded == 1).scalar()

    revenue_by_type = db.session.query(
        Event.event_type, func.coalesce(func.sum(Payment.amount), 0).label("revenue"),
        func.count(Event.id.distinct()).label("count")
    ).outerjoin(Payment, (Payment.event_id == Event.id) & (Payment.is_refunded == 0)).filter(
        Event.event_date.between(sd, ed), Event.status != "annulé"
    ).group_by(Event.event_type).order_by(func.sum(Payment.amount).desc()).all()

    top_clients = db.session.query(
        Client.id, Client.name,
        func.coalesce(func.sum(Event.total_amount), 0).label("total_billed"),
        func.coalesce(func.sum(case((Payment.is_refunded == 0, Payment.amount), else_=0)), 0).label("total_paid"),
    ).join(Event, Client.id == Event.client_id).outerjoin(Payment, Payment.event_id == Event.id).filter(Event.event_date.between(sd, ed)).group_by(Client.id, Client.name).having(
        func.sum(Event.total_amount) > 0).order_by(func.sum(Event.total_amount).desc()).limit(10).all()

    payments = Payment.query.join(Event).join(Client).filter(
        Payment.payment_date.between(sd, ed)).order_by(Payment.payment_date.desc()).all()

    ef_raw = db.session.query(
        Event.id, Event.title, Event.event_date, Event.event_type, Event.status, Event.total_amount,
        Client.name.label("client_name"),
        func.coalesce(func.sum(case((EventLine.is_cost == 0, EventLine.amount), else_=0)), 0).label("total_revenue"),
        func.coalesce(func.sum(case((EventLine.is_cost == 1, EventLine.amount), else_=0)), 0).label("total_costs"),
    ).join(Client).outerjoin(EventLine).filter(
        Event.event_date.between(sd, ed), Event.status != "annulé"
    ).group_by(Event.id).order_by(Event.event_date.desc()).all()

    ef_list = []
    for r in ef_raw:
        rev, costs = float(r.total_revenue), float(r.total_costs)
        paid = float(db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(Payment.event_id == r.id, Payment.is_refunded == 0).scalar())
        ef_list.append({"id": r.id, "title": r.title, "event_date": r.event_date, "event_type": r.event_type,
                        "status": r.status, "total_amount": float(r.total_amount), "client_name": r.client_name,
                        "total_revenue": rev, "total_costs": costs, "total_paid": paid,
                        "profit": rev - costs, "remaining": round(float(r.total_amount) - paid, 2)})

    if export_csv:
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["Date", "Événement", "Client", "Type", "Revenus", "Coûts", "Bénéfice", "Payé", "Reste", "Statut"])
        for e in ef_list: w.writerow([e["event_date"][:10], e["title"], e["client_name"], e["event_type"], e["total_revenue"], e["total_costs"], e["profit"], e["total_paid"], e["remaining"], e["status"]])
        resp = make_response(out.getvalue())
        resp.headers["Content-Type"] = "text/csv"; resp.headers["Content-Disposition"] = f"attachment; filename=finances_{sd}_{ed}.csv"
        return resp

    total_outstanding = sum(e["remaining"] for e in ef_list)
    return render_template("finance/financials.html", start_date=sd, end_date=ed, total_revenue=total_revenue,
                           total_outstanding=total_outstanding, total_refunded=total_refunded,
                           total_profit=sum(e["profit"] for e in ef_list), revenue_by_type=revenue_by_type,
                           top_clients=top_clients, payments=payments, event_financials=ef_list)


# ─── Accounting ──────────────────────────────────────────────────────
@bp.route("/comptabilite")
@login_required
def accounting():
    sd = request.args.get("start_date", (date.today() - timedelta(days=365)).isoformat())
    ed = request.args.get("end_date", date.today().isoformat())
    total_income = float(db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(Payment.payment_date.between(sd, ed), Payment.is_refunded == 0).scalar() or 0)
    total_expenses = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(Expense.expense_date.between(sd, ed)).scalar() or 0)
    net_profit = total_income - total_expenses

    by_cat = [{"category": r.category, "total": float(r.total or 0), "count": r.count} for r in
              db.session.query(Expense.category, func.sum(Expense.amount).label("total"), func.count().label("count")).filter(
                  Expense.expense_date.between(sd, ed)).group_by(Expense.category).order_by(func.sum(Expense.amount).desc()).all()]

    monthly_pl = []
    cur = datetime.strptime(sd, "%Y-%m-%d").replace(day=1)
    end = datetime.strptime(ed, "%Y-%m-%d")
    while cur <= end:
        ms, me = cur.strftime("%Y-%m-%d"), ((cur.replace(year=cur.year + 1, month=1, day=1) - timedelta(days=1)) if cur.month == 12 else (cur.replace(month=cur.month + 1, day=1) - timedelta(days=1))).strftime("%Y-%m-%d")
        mi = float(db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(Payment.payment_date.between(ms, me), Payment.is_refunded == 0).scalar() or 0)
        mx = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(Expense.expense_date.between(ms, me)).scalar() or 0)
        monthly_pl.append({"month": ms[:7], "month_name": f"{MONTH_NAMES_FR[cur.month]} {cur.year}", "income": mi, "expenses": mx, "profit": mi - mx, "margin": ((mi - mx) / mi * 100) if mi > 0 else 0})
        cur = cur.replace(year=cur.year + 1, month=1) if cur.month == 12 else cur.replace(month=cur.month + 1)
    monthly_pl.reverse()

    return render_template("finance/accounting.html", start_date=sd, end_date=ed, total_income=total_income,
                           total_expenses=total_expenses, net_profit=net_profit,
                           profit_margin=(net_profit / total_income * 100) if total_income > 0 else 0,
                           expenses_by_category=by_cat, monthly_pl=monthly_pl)


# ─── Expenses CRUD ───────────────────────────────────────────────────
@bp.route("/depenses")
@login_required
def expenses():
    sd = request.args.get("start_date", (date.today() - timedelta(days=30)).isoformat())
    ed = request.args.get("end_date", date.today().isoformat())
    cat = request.args.get("category", "")
    q = Expense.query
    if sd: q = q.filter(Expense.expense_date >= sd)
    if ed: q = q.filter(Expense.expense_date <= ed)
    if cat: q = q.filter(Expense.category == cat)
    all_exp = q.order_by(Expense.expense_date.desc()).all()
    total = sum(float(e.amount) for e in all_exp)
    month_start = date.today().replace(day=1).isoformat()
    month_exp = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(Expense.expense_date >= month_start).scalar() or 0)

    by_cat = [{"category": r.category, "total": float(r.total or 0), "count": r.count} for r in
              db.session.query(Expense.category, func.sum(Expense.amount).label("total"), func.count().label("count")).filter(
                  Expense.expense_date.between(sd, ed)).group_by(Expense.category).all()]

    return render_template("finance/expenses.html", expenses=all_exp, start_date=sd, end_date=ed,
                           category_filter=cat, categories=EXPENSE_CATEGORIES, total_expenses=total,
                           expenses_this_month=month_exp, avg_expense=total / len(all_exp) if all_exp else 0,
                           expenses_by_category=by_cat, recent_events=Event.query.order_by(Event.event_date.desc()).limit(20).all(),
                           today_str=date.today().isoformat())


@bp.route("/depenses/ajouter", methods=["POST"])
@login_required
def add_expense():
    try:
        cat = request.form.get("category", "")
        amount = request.form.get("amount", 0, type=float)
        if not cat: flash("La catégorie est requise", "danger"); return redirect(url_for("finance.expenses"))
        if amount <= 0: flash("Le montant doit être > 0", "danger"); return redirect(url_for("finance.expenses"))
        desc = request.form.get("description", "").strip()
        if cat == "Autre" and desc: desc = f"Autre: {desc}"
        db.session.add(Expense(expense_date=request.form.get("expense_date", date.today().isoformat()), category=cat,
                               description=desc, amount=amount, event_id=request.form.get("event_id", type=int) or None,
                               method=request.form.get("method", "espèces"), reference=request.form.get("reference", "").strip(),
                               notes=request.form.get("notes", "").strip()))
        db.session.commit(); flash("Dépense enregistrée!", "success")
    except Exception: db.session.rollback(); flash("Erreur.", "danger")
    return redirect(url_for("finance.expenses"))


@bp.route("/depense/<int:expense_id>/supprimer", methods=["POST"])
@login_required
def delete_expense(expense_id):
    try:
        exp = Expense.query.get_or_404(expense_id)
        eid = exp.event_id
        db.session.delete(exp); db.session.commit(); flash("Dépense supprimée", "success")
        if eid: return redirect(url_for("bookings.event_detail", event_id=eid))
    except Exception: db.session.rollback(); flash("Erreur.", "danger")
    return redirect(url_for("finance.expenses"))


# ─── Exports ─────────────────────────────────────────────────────────
@admin_required
@bp.route("/export/events.ods")
@login_required
def export_events():
    events = Event.query.join(Client).join(Venue, Event.venue_id == Venue.id).order_by(Event.event_date.desc()).all()
    ods = export_events_ods([_event_dict(e) for e in events], datetime.now().strftime("%Y-%m-%d %H:%M"))
    resp = make_response(ods); resp.headers["Content-Type"] = "application/vnd.oasis.opendocument.spreadsheet"
    resp.headers["Content-Disposition"] = f"attachment; filename=evenements_{date.today().isoformat()}.ods"; return resp

@admin_required
@bp.route("/export/clients.ods")
@login_required
def export_clients():
    clients = Client.query.order_by(Client.created_at.desc()).all()
    ods = export_clients_ods([_client_dict(c) for c in clients], datetime.now().strftime("%Y-%m-%d %H:%M"))
    resp = make_response(ods); resp.headers["Content-Type"] = "application/vnd.oasis.opendocument.spreadsheet"
    resp.headers["Content-Disposition"] = f"attachment; filename=clients_{date.today().isoformat()}.ods"; return resp

@admin_required
@bp.route("/export/payments.ods")
@login_required
def export_payments():
    sd, ed = request.args.get("start_date", ""), request.args.get("end_date", "")
    q = Payment.query.join(Event).join(Client)
    if sd: q = q.filter(Payment.payment_date >= sd)
    if ed: q = q.filter(Payment.payment_date <= ed + " 23:59:59")
    ods = export_payments_ods([_payment_dict(p) for p in q.order_by(Payment.payment_date.desc()).all()], datetime.now().strftime("%Y-%m-%d %H:%M"))
    resp = make_response(ods); resp.headers["Content-Type"] = "application/vnd.oasis.opendocument.spreadsheet"
    resp.headers["Content-Disposition"] = f"attachment; filename=paiements_{date.today().isoformat()}.ods"; return resp

@admin_required
@bp.route("/export/finances.ods")
@login_required
def export_finances():
    sd = request.args.get("start_date", (date.today() - timedelta(days=365)).isoformat())
    ed = request.args.get("end_date", date.today().isoformat())
    tr = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(Payment.payment_date.between(sd, ed), Payment.is_refunded == 0).scalar()
    to_ = db.session.query(func.coalesce(func.sum(Event.total_amount), 0) - func.coalesce(func.sum(Payment.amount), 0)).select_from(Event).outerjoin(Payment, (Payment.event_id == Event.id) & (Payment.is_refunded == 0)).filter(Event.event_date.between(sd, ed), Event.status.notin_(["annulé", "terminé"])).scalar()
    ods = export_financials_ods([], {"total_revenue": tr, "total_outstanding": to_}, datetime.now().strftime("%Y-%m-%d %H:%M"))
    resp = make_response(ods); resp.headers["Content-Type"] = "application/vnd.oasis.opendocument.spreadsheet"
    resp.headers["Content-Disposition"] = f"attachment; filename=finances_{sd}_{ed}.ods"; return resp

@admin_required
@bp.route("/export/expenses.ods")
@login_required
def export_expenses():
    sd = request.args.get("start_date", (date.today() - timedelta(days=365)).isoformat())
    ed = request.args.get("end_date", date.today().isoformat())
    q = Expense.query.filter(Expense.expense_date.between(sd, ed))
    ods = export_expenses_ods([_expense_dict(e) for e in q.order_by(Expense.expense_date.desc()).all()], datetime.now().strftime("%Y-%m-%d %H:%M"))
    resp = make_response(ods); resp.headers["Content-Type"] = "application/vnd.oasis.opendocument.spreadsheet"
    resp.headers["Content-Disposition"] = f"attachment; filename=depenses_{sd}_{ed}.ods"; return resp

@admin_required
@bp.route("/export/pl.ods")
@login_required
def export_pl():
    sd = request.args.get("start_date", (date.today() - timedelta(days=365)).isoformat())
    ed = request.args.get("end_date", date.today().isoformat())
    monthly = []
    cur = datetime.strptime(sd, "%Y-%m-%d").replace(day=1)
    end = datetime.strptime(ed, "%Y-%m-%d")
    while cur <= end:
        ms = cur.strftime("%Y-%m-%d")
        me = ((cur.replace(year=cur.year + 1, month=1, day=1) - timedelta(days=1)) if cur.month == 12 else (cur.replace(month=cur.month + 1, day=1) - timedelta(days=1))).strftime("%Y-%m-%d")
        mi = float(db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(Payment.payment_date.between(ms, me), Payment.is_refunded == 0).scalar() or 0)
        mx = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(Expense.expense_date.between(ms, me)).scalar() or 0)
        monthly.append({"month": f"{MONTH_NAMES_FR[cur.month]} {cur.year}", "income": mi, "expenses": mx})
        cur = cur.replace(year=cur.year + 1, month=1) if cur.month == 12 else cur.replace(month=cur.month + 1)
    monthly.reverse()
    ods = export_pl_report_ods(monthly, datetime.now().strftime("%Y-%m-%d %H:%M"))
    resp = make_response(ods); resp.headers["Content-Type"] = "application/vnd.oasis.opendocument.spreadsheet"
    resp.headers["Content-Disposition"] = f"attachment; filename=rapport_pl_{sd}_{ed}.ods"; return resp


# ─── Dict converters for export functions ─────────────────────────────
def _event_dict(e):
    return {c.name: getattr(e, c.name) for c in e.__table__.columns} | {"client_name": e.client.name, "venue_name": e.venue.name, "total_paid": e.total_paid}

def _client_dict(c):
    d = {k: getattr(c, k) for k in ["id", "name", "phone", "phone2", "email", "address", "created_at"]}
    d["event_count"] = c.event_count; d["total_paid"] = c.total_paid; d["total_owed"] = c.total_owed; return d

def _payment_dict(p):
    return {c.name: getattr(p, c.name) for c in p.__table__.columns} | {"title": p.event.title, "event_date": p.event.event_date, "client_name": p.event.client.name}

def _expense_dict(e):
    d = {c.name: getattr(e, c.name) for c in e.__table__.columns}
    d["event_title"] = e.event.title if e.event else ""; return d

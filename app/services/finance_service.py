"""Samba Fête — Finance service.

Business logic for expenses, financial reports, dashboard KPIs.
"""
import logging
from datetime import date, timedelta

from sqlalchemy import func

from app.models import db, Event, Client, Payment, Expense, Setting, AuditLog

logger = logging.getLogger(__name__)


class FinanceService:
    """Encapsulates all finance/reporting business logic."""

    @staticmethod
    def get_dashboard_kpis():
        """Return dict of all dashboard KPIs. Consolidates ~15 queries."""
        today = date.today()
        first = today.replace(day=1)
        last = (today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
                if today.month == 12
                else today.replace(month=today.month + 1, day=1) - timedelta(days=1))

        pm = today.month - 1 if today.month > 1 else 12
        py = today.year if today.month > 1 else today.year - 1
        pf = date(py, pm, 1)
        pl = (date(py + 1, 1, 1) - timedelta(days=1) if pm == 12
              else date(py, pm + 1, 1) - timedelta(days=1))

        events_month = Event.query.filter(
            Event.event_date.between(first.isoformat(), last.isoformat()),
            Event.status != "annulé").count()

        revenue_month = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).join(Event).filter(
            Payment.payment_date.between(first.isoformat(), last.isoformat()),
            Event.status != "annulé", Payment.is_refunded == 0).scalar()

        last_month_rev = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).join(Event).filter(
            Payment.payment_date.between(pf.isoformat(), pl.isoformat()),
            Event.status != "annulé", Payment.is_refunded == 0).scalar()

        month_expenses = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
            Expense.expense_date.between(first.isoformat(), last.isoformat())).scalar()

        rev_pct = ((float(revenue_month) - float(last_month_rev)) / float(last_month_rev) * 100
                   if float(last_month_rev) > 0 else (100.0 if float(revenue_month) > 0 else 0.0))

        return {
            "events_this_month": events_month,
            "revenue_month": revenue_month,
            "last_month_revenue": last_month_rev,
            "month_expenses": month_expenses,
            "month_profit": float(revenue_month) - float(month_expenses),
            "revenue_pct_change": rev_pct,
            "total_clients": Client.query.count(),
            "total_events": Event.query.filter(Event.status != "annulé").count(),
            "pending_count": Event.query.filter(
                Event.status == "en attente", Event.event_date >= today.isoformat()).count(),
            "hall_name": Setting.get("hall_name", "Samba Fête"),
            "currency": Setting.get("currency", "DA"),
        }

    @staticmethod
    def get_chart_data(months=6):
        """Revenue/expenses/profit for last N months."""
        today = date.today()
        labels, revenues, expenses, profits = [], [], [], []
        for i in range(months - 1, -1, -1):
            m, y = today.month - i, today.year
            while m <= 0:
                m += 12; y -= 1
            mf = date(y, m, 1)
            ml = date(y + 1, 1, 1) - timedelta(days=1) if m == 12 else date(y, m + 1, 1) - timedelta(days=1)
            rev = float(db.session.query(func.coalesce(func.sum(Payment.amount), 0)).join(Event).filter(
                Payment.payment_date.between(mf.isoformat(), ml.isoformat()),
                Event.status != "annulé", Payment.is_refunded == 0).scalar() or 0)
            exp = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
                Expense.expense_date.between(mf.isoformat(), ml.isoformat())).scalar() or 0)
            labels.append(["", "Jan", "Fév", "Mar", "Avr", "Mai", "Jun",
                           "Jul", "Aoû", "Sep", "Oct", "Nov", "Déc"][m])
            revenues.append(rev)
            expenses.append(exp)
            profits.append(rev - exp)
        return {"labels": labels, "revenues": revenues, "expenses": expenses, "profits": profits}

    @staticmethod
    def add_expense(data):
        """Add expense with validation. Returns (expense, error)."""
        amount = data.get("amount", 0, type=float)
        category = data.get("category", "")

        if not category:
            return None, "La catégorie est requise"
        if amount <= 0:
            return None, "Le montant doit être > 0"

        desc = data.get("description", "").strip()
        if category == "Autre" and desc:
            desc = f"Autre: {desc}"

        expense = Expense(
            expense_date=data.get("expense_date", date.today().isoformat()),
            category=category, description=desc, amount=amount,
            event_id=data.get("event_id", type=int) or None,
            method=data.get("method", "espèces"),
            reference=data.get("reference", "").strip(),
            notes=data.get("notes", "").strip(),
        )
        db.session.add(expense)
        db.session.commit()
        AuditLog.log("expense.create", entity_type="expense", entity_id=expense.id,
                     details=f"category={category}, amount={amount}")
        return expense, None

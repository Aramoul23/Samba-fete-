"""Samba Fête — SQLAlchemy ORM models.

Matches the existing PostgreSQL/SQLite schema exactly.
Column names, types, and defaults preserved for seamless migration.
"""
from datetime import datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


# ══════════════════════════════════════════════════════════════════════
# User
# ══════════════════════════════════════════════════════════════════════

class User(UserMixin, db.Model):
    """User model — compatible with Flask-Login."""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.Text, unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    role = db.Column(db.Text, nullable=False, default="manager")
    is_active = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"

    # ── Flask-Login helpers ──────────────────────────────────────────
    @property
    def is_admin(self):
        return self.role == "admin"

    def set_password(self, password):
        """Hash and store the password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verify password against stored hash."""
        return check_password_hash(self.password_hash, password)

    # ── Convenience queries ──────────────────────────────────────────
    @classmethod
    def get_by_username(cls, username):
        return cls.query.filter_by(username=username).first()

    @classmethod
    def get_all_ordered(cls):
        return cls.query.order_by(cls.id).all()


# ══════════════════════════════════════════════════════════════════════
# Venue
# ══════════════════════════════════════════════════════════════════════

class Venue(db.Model):
    __tablename__ = "venues"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.Text, nullable=False)
    capacity_men = db.Column(db.Integer, default=0)
    capacity_women = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Integer, default=1)

    def __repr__(self):
        return f"<Venue {self.name}>"


# ══════════════════════════════════════════════════════════════════════
# Client
# ══════════════════════════════════════════════════════════════════════

class Client(db.Model):
    __tablename__ = "clients"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.Text, nullable=False)
    phone = db.Column(db.Text, nullable=False)
    phone2 = db.Column(db.Text)
    email = db.Column(db.Text)
    address = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    events = db.relationship("Event", backref="client", lazy="dynamic",
                             foreign_keys="Event.client_id")

    def __repr__(self):
        return f"<Client {self.name} ({self.phone})>"

    @property
    def event_count(self):
        return self.events.count()

    @property
    def total_owed(self):
        return sum(e.total_amount for e in self.events)

    @property
    def total_paid(self):
        return sum(
            p.amount for e in self.events
            for p in e.payments if not p.is_refunded
        )


# ══════════════════════════════════════════════════════════════════════
# Event (Booking)
# ══════════════════════════════════════════════════════════════════════

class Event(db.Model):
    """Main booking/event model."""
    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.Text, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False)
    venue_id = db.Column(db.Integer, db.ForeignKey("venues.id"), nullable=False)
    venue_id2 = db.Column(db.Integer, db.ForeignKey("venues.id"))
    event_type = db.Column(db.Text, nullable=False)
    event_date = db.Column(db.Text, nullable=False)  # TEXT to match existing schema
    time_slot = db.Column(db.Text, nullable=False)
    guests_men = db.Column(db.Integer, default=0)
    guests_women = db.Column(db.Integer, default=0)
    status = db.Column(db.Text, default="en attente")
    notes = db.Column(db.Text)
    total_amount = db.Column(db.Float, default=0)
    deposit_required = db.Column(db.Float, default=20000)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow)

    # Relationships
    venue = db.relationship("Venue", foreign_keys=[venue_id], backref="events")
    venue2 = db.relationship("Venue", foreign_keys=[venue_id2])
    service_lines = db.relationship("EventLine", backref="event", lazy="dynamic",
                                    cascade="all, delete-orphan")
    payments = db.relationship("Payment", backref="event", lazy="dynamic",
                               cascade="all, delete-orphan")
    expenses = db.relationship("Expense", backref="event", lazy="dynamic",
                               cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        db.Index("ix_events_event_date", "event_date"),
        db.Index("ix_events_status", "status"),
        db.Index("ix_events_client_id", "client_id"),
        db.Index("ix_events_venue_id", "venue_id"),
    )

    def __repr__(self):
        return f"<Event {self.title} ({self.event_date})>"

    @property
    def total_paid(self):
        """Total non-refunded payments."""
        return sum(p.amount for p in self.payments if not p.is_refunded)

    @property
    def remaining(self):
        """Amount still owed."""
        return round(self.total_amount - self.total_paid, 2)

    @property
    def total_revenue(self):
        """Sum of non-cost service lines."""
        return sum(sl.amount for sl in self.service_lines if not sl.is_cost)

    @property
    def total_costs(self):
        """Sum of cost service lines."""
        return sum(sl.amount for sl in self.service_lines if sl.is_cost)

    @property
    def profit(self):
        return self.total_revenue - self.total_costs


# ══════════════════════════════════════════════════════════════════════
# EventLine (Service Line Item)
# ══════════════════════════════════════════════════════════════════════

class EventLine(db.Model):
    """Individual service/cost line for an event."""
    __tablename__ = "event_lines"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id", ondelete="CASCADE"),
                         nullable=False)
    description = db.Column(db.Text, nullable=False)
    amount = db.Column(db.Float, default=0)
    is_cost = db.Column(db.Integer, default=0)

    __table_args__ = (
        db.Index("ix_event_lines_event_id", "event_id"),
    )

    def __repr__(self):
        kind = "cost" if self.is_cost else "revenue"
        return f"<EventLine {self.description}: {self.amount} ({kind})>"


# ══════════════════════════════════════════════════════════════════════
# Payment
# ══════════════════════════════════════════════════════════════════════

class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id", ondelete="CASCADE"),
                         nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_type = db.Column(db.Text, default="Acompte")
    method = db.Column(db.Text, default="Espèces")
    reference = db.Column(db.Text)
    notes = db.Column(db.Text)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    is_refunded = db.Column(db.Integer, default=0)

    __table_args__ = (
        db.Index("ix_payments_event_id", "event_id"),
        db.Index("ix_payments_payment_date", "payment_date"),
    )

    def __repr__(self):
        ref = " [REFUNDED]" if self.is_refunded else ""
        return f"<Payment {self.amount} DA for event {self.event_id}{ref}>"


# ══════════════════════════════════════════════════════════════════════
# Expense
# ══════════════════════════════════════════════════════════════════════

class Expense(db.Model):
    __tablename__ = "expenses"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id", ondelete="CASCADE"))
    category = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, default="")
    amount = db.Column(db.Float, default=0)
    expense_date = db.Column(db.Text, default=lambda: datetime.now().strftime("%Y-%m-%d"))
    method = db.Column(db.Text, default="espèces")
    reference = db.Column(db.Text)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.Index("ix_expenses_expense_date", "expense_date"),
        db.Index("ix_expenses_event_id", "event_id"),
        db.Index("ix_expenses_category", "category"),
    )

    def __repr__(self):
        return f"<Expense {self.category}: {self.amount} DA ({self.expense_date})>"


# ══════════════════════════════════════════════════════════════════════
# Setting (key-value store)
# ══════════════════════════════════════════════════════════════════════

class Setting(db.Model):
    """Application settings as key-value pairs."""
    __tablename__ = "settings"

    key = db.Column(db.Text, primary_key=True)
    value = db.Column(db.Text)

    def __repr__(self):
        return f"<Setting {self.key}={self.value}>"

    @classmethod
    def get(cls, key, default=""):
        """Get a setting value."""
        row = db.session.get(cls, key)
        return row.value if row else default

    @classmethod
    def set(cls, key, value):
        """Set or update a setting value."""
        row = db.session.get(cls, key)
        if row:
            row.value = value
        else:
            row = cls(key=key, value=value)
            db.session.add(row)
        db.session.commit()


# ══════════════════════════════════════════════════════════════════════
# Audit Trail
# ══════════════════════════════════════════════════════════════════════

class AuditLog(db.Model):
    """Financial and operational audit trail.

    Records every significant action for compliance and debugging.
    Never delete from this table.
    """
    __tablename__ = "audit_log"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    username = db.Column(db.Text)  # Denormalized for when user is deleted
    action = db.Column(db.Text, nullable=False, index=True)  # e.g., "payment.create", "event.delete"
    entity_type = db.Column(db.Text, index=True)  # e.g., "event", "payment", "expense"
    entity_id = db.Column(db.Integer)
    details = db.Column(db.Text)  # JSON with before/after or description
    ip_address = db.Column(db.Text)

    __table_args__ = (
        db.Index("ix_audit_log_entity", "entity_type", "entity_id"),
    )

    def __repr__(self):
        return f"<AuditLog {self.action} by {self.username} at {self.timestamp}>"

    @classmethod
    def log(cls, action, user=None, entity_type=None, entity_id=None, details=None, ip=None):
        """Create an audit log entry."""
        entry = cls(
            user_id=user.id if user else None,
            username=user.username if user else "system",
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
            ip_address=ip,
        )
        db.session.add(entry)
        # Don't commit here — let the caller handle transaction

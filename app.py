from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response
from models import get_db, init_db, get_setting, set_setting
from datetime import datetime, date, timedelta
from contract_generator import generate_contract_pdf
from receipt_generator import generate_receipt_html
from export_functions import export_events_ods, export_clients_ods, export_payments_ods, export_financials_ods, export_expenses_ods, export_pl_report_ods
import calendar
import csv
import io
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(32).hex())

# ─── Helpers ────────────────────────────────────────────────────────
TIME_SLOTS = ['Déjeuner', 'Après-midi', 'Dîner']
EVENT_TYPES = ['Mariage', 'Fiançailles', 'Anniversaire', 'Conférence', 'Autre']
EVENT_STATUSES = ['en attente', 'confirmé', 'changé de date', 'terminé', 'annulé']
PAYMENT_METHODS = ['espèces', 'chèque', 'virement', 'carte']
MONTH_NAMES_FR = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                  'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']

DEFAULT_VENUES = [
    {'name': 'Grande Salle', 'capacity_men': 200, 'capacity_women': 200},
    {'name': 'Salle VIP', 'capacity_men': 80, 'capacity_women': 80},
    {'name': 'Salle de Conférence', 'capacity_men': 50, 'capacity_women': 50},
]

def format_da(amount):
    try:
        return f"{float(amount):,.0f} DA".replace(",", " ")
    except (ValueError, TypeError):
        return "0 DA"

app.jinja_env.filters['format_da'] = format_da

def check_pending_events():
    """Check for events that have been 'en attente' for more than 48 hours."""
    db = get_db()
    now = datetime.now()
    threshold = (now - timedelta(hours=48)).strftime('%Y-%m-%d %H:%M:%S')
    future_date = (date.today() + timedelta(days=30)).isoformat()
    today = date.today().isoformat()
    
    pending_old = db.execute(
        "SELECT id, title, created_at, event_date FROM events "
        "WHERE status = 'en attente' "
        "AND event_date BETWEEN ? AND ? "
        "AND created_at < ?",
        (today, future_date, threshold)
    ).fetchall()
    
    db.close()
    return pending_old

def get_event_financials(event_id):
    """Get complete financial data for an event."""
    db = get_db()
    
    # Get revenue lines (income)
    revenue_lines = db.execute(
        "SELECT COALESCE(SUM(amount), 0) as total FROM event_lines WHERE event_id=? AND is_cost=0",
        (event_id,)
    ).fetchone()['total']
    
    # Get cost lines
    cost_lines = db.execute(
        "SELECT COALESCE(SUM(amount), 0) as total FROM event_lines WHERE event_id=? AND is_cost=1",
        (event_id,)
    ).fetchone()['total']
    
    # Get total paid (excluding refunded)
    total_paid = db.execute(
        "SELECT COALESCE(SUM(amount), 0) as total FROM payments WHERE event_id=? AND is_refunded=0",
        (event_id,)
    ).fetchone()['total']
    
    # Get total refunded
    total_refunded = db.execute(
        "SELECT COALESCE(SUM(amount), 0) as total FROM payments WHERE event_id=? AND is_refunded=1",
        (event_id,)
    ).fetchone()['total']
    
    # Get event total
    event = db.execute("SELECT total_amount FROM events WHERE id=?", (event_id,)).fetchone()
    event_total = event['total_amount'] if event else 0
    
    db.close()
    
    return {
        'revenue': float(revenue_lines),
        'costs': float(cost_lines),
        'profit': float(revenue_lines) - float(cost_lines),
        'paid': float(total_paid),
        'remaining': event_total - float(total_paid),
        'refunded': float(total_refunded)
    }

def ensure_default_data():
    """Ensure database has default venues and settings."""
    db = get_db()
    
    venue_count = db.execute("SELECT COUNT(*) as c FROM venues").fetchone()['c']
    
    if venue_count == 0:
        print("Initializing default venues...")
        for v in DEFAULT_VENUES:
            db.execute(
                "INSERT INTO venues (name, capacity_men, capacity_women, is_active) VALUES (?, ?, ?, 1)",
                (v['name'], v['capacity_men'], v['capacity_women'])
            )
        db.commit()
        print(f"Created {len(DEFAULT_VENUES)} default venues.")
    
    settings = db.execute("SELECT key FROM settings WHERE key IN ('hall_name', 'currency', 'deposit_min')").fetchall()
    existing_keys = {s['key'] for s in settings}
    
    if 'hall_name' not in existing_keys:
        set_setting('hall_name', 'Samba Fête')
    if 'currency' not in existing_keys:
        set_setting('currency', 'DA')
    if 'deposit_min' not in existing_keys:
        set_setting('deposit_min', '20000')
    
    db.close()
    print("Default data check complete.")

# ─── Dashboard ──────────────────────────────────────────────────────
@app.route('/')
def index():
    db = get_db()
    today = date.today()
    first_day = today.replace(day=1)
    if today.month == 12:
        last_day = today.replace(year=today.year+1, month=1, day=1) - timedelta(days=1)
    else:
        last_day = today.replace(month=today.month+1, day=1) - timedelta(days=1)

    events_this_month = db.execute(
        "SELECT COUNT(*) as c FROM events WHERE event_date BETWEEN ? AND ? AND status != 'annulé'",
        (first_day.isoformat(), last_day.isoformat())).fetchone()['c']

    revenue_month = db.execute(
        "SELECT COALESCE(SUM(p.amount),0) as s FROM payments p "
        "JOIN events e ON p.event_id=e.id "
        "WHERE p.payment_date BETWEEN ? AND ? AND e.status != 'annulé' AND p.is_refunded=0",
        (first_day.isoformat(), last_day.isoformat())).fetchone()['s']

    upcoming = db.execute(
        "SELECT e.*, c.name as client_name, v.name as venue_name FROM events e "
        "JOIN clients c ON e.client_id=c.id JOIN venues v ON e.venue_id=v.id "
        "WHERE e.event_date >= ? AND e.status NOT IN ('annulé', 'terminé') ORDER BY e.event_date ASC LIMIT 5",
        (today.isoformat(),)).fetchall()

    total_clients = db.execute("SELECT COUNT(*) as c FROM clients").fetchone()['c']
    total_events = db.execute("SELECT COUNT(*) as c FROM events WHERE status != 'annulé'").fetchone()['c']

    recent_payments = db.execute(
        "SELECT p.*, e.title, c.name as client_name FROM payments p "
        "JOIN events e ON p.event_id=e.id JOIN clients c ON e.client_id=c.id "
        "WHERE p.is_refunded=0 "
        "ORDER BY p.payment_date DESC LIMIT 5").fetchall()

    # --- V2 Dashboard Data ---
    # Last month revenue for % change comparison
    prev_month = today.month - 1 if today.month > 1 else 12
    prev_month_year = today.year if today.month > 1 else today.year - 1
    prev_first = date(prev_month_year, prev_month, 1)
    if prev_month == 12:
        prev_last = date(prev_month_year + 1, 1, 1) - timedelta(days=1)
    else:
        prev_last = date(prev_month_year, prev_month + 1, 1) - timedelta(days=1)
    
    last_month_revenue = db.execute(
        "SELECT COALESCE(SUM(p.amount),0) as s FROM payments p "
        "JOIN events e ON p.event_id=e.id "
        "WHERE p.payment_date BETWEEN ? AND ? AND e.status != 'annulé' AND p.is_refunded=0",
        (prev_first.isoformat(), prev_last.isoformat())).fetchone()['s']
    
    # This month expenses
    month_expenses = db.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM expenses WHERE expense_date BETWEEN ? AND ?",
        (first_day.isoformat(), last_day.isoformat())).fetchone()['s']
    
    # This month profit
    month_profit = float(revenue_month) - float(month_expenses)
    
    # Revenue % change
    if float(last_month_revenue) > 0:
        revenue_pct_change = ((float(revenue_month) - float(last_month_revenue)) / float(last_month_revenue)) * 100
    else:
        revenue_pct_change = 100.0 if float(revenue_month) > 0 else 0.0
    
    # Pending count
    pending_count = db.execute(
        "SELECT COUNT(*) as c FROM events WHERE status = 'en attente' AND event_date >= ?",
        (today.isoformat(),)).fetchone()['c']
    
    # Next event
    next_event = db.execute(
        "SELECT e.event_date, c.name as client_name FROM events e "
        "JOIN clients c ON e.client_id=c.id "
        "WHERE e.event_date >= ? AND e.status NOT IN ('annulé', 'terminé') "
        "ORDER BY e.event_date ASC LIMIT 1",
        (today.isoformat(),)).fetchone()
    
    # 6 months chart data
    chart_labels = []
    chart_revenues = []
    chart_expenses = []
    chart_profits = []
    
    for i in range(5, -1, -1):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        
        m_first = date(y, m, 1)
        if m == 12:
            m_last = date(y + 1, 1, 1) - timedelta(days=1)
        else:
            m_last = date(y, m + 1, 1) - timedelta(days=1)
        
        m_rev = db.execute(
            "SELECT COALESCE(SUM(p.amount),0) as s FROM payments p "
            "JOIN events e ON p.event_id=e.id "
            "WHERE p.payment_date BETWEEN ? AND ? AND e.status != 'annulé' AND p.is_refunded=0",
            (m_first.isoformat(), m_last.isoformat())).fetchone()['s']
        
        m_exp = db.execute(
            "SELECT COALESCE(SUM(amount),0) as s FROM expenses "
            "WHERE expense_date BETWEEN ? AND ?",
            (m_first.isoformat(), m_last.isoformat())).fetchone()['s']
        
        chart_labels.append(MONTH_NAMES_FR[m][:3])
        chart_revenues.append(float(m_rev))
        chart_expenses.append(float(m_exp))
        chart_profits.append(float(m_rev) - float(m_exp))
    
    # Upcoming events with revenue
    upcoming_with_revenue = []
    for ev in upcoming:
        ev_dict = ev
        ev_rev = db.execute(
            "SELECT COALESCE(SUM(amount),0) as s FROM payments WHERE event_id=? AND is_refunded=0",
            (ev['id'],)).fetchone()['s']
        ev_dict['paid'] = float(ev_rev)
        upcoming_with_revenue.append(ev_dict)
    
    hall_name = get_setting('hall_name', 'Samba Fête')
    currency = get_setting('currency', 'DA')
    pending_needs_attention = check_pending_events()

    db.close()
    return render_template('index.html', events_this_month=events_this_month,
                           revenue_month=revenue_month, upcoming=upcoming,
                           total_clients=total_clients, total_events=total_events,
                           recent_payments=recent_payments, today=today,
                           hall_name=hall_name, currency=currency,
                           month_name=MONTH_NAMES_FR[today.month],
                           pending_needs_attention=pending_needs_attention,
                           # V2 data
                           last_month_revenue=last_month_revenue,
                           month_expenses=month_expenses,
                           month_profit=month_profit,
                           revenue_pct_change=revenue_pct_change,
                           pending_count=pending_count,
                           next_event=next_event,
                           chart_labels=chart_labels,
                           chart_revenues=chart_revenues,
                           chart_expenses=chart_expenses,
                           chart_profits=chart_profits,
                           upcoming_with_revenue=upcoming_with_revenue)

# ─── Calendar ────────────────────────────────────────────────────────
@app.route('/calendrier')
def calendar_view():
    db = get_db()
    year = request.args.get('year', date.today().year, type=int)
    month = request.args.get('month', date.today().month, type=int)

    first = f"{year}-{month:02d}-01"
    if month == 12:
        last = f"{year+1}-01-01"
    else:
        last = f"{year}-{month+1:02d}-01"

    venue_filter = request.args.get('venue', type=int)
    
    query = "SELECT event_date, time_slot, title, status FROM events WHERE event_date >= ? AND event_date < ? AND status != 'annulé'"
    params = [first, last]
    
    if venue_filter:
        query += " AND (venue_id = ? OR venue_id2 = ?)"
        params.append(venue_filter)
        params.append(venue_filter)
    
    query += " ORDER BY event_date"
    booked = db.execute(query, params).fetchall()

    booked_dict = {}
    for b in booked:
        d = b['event_date']
        if d not in booked_dict:
            booked_dict[d] = []
        booked_dict[d].append(b)

    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)
    today_str = date.today().isoformat()

    venues = db.execute("SELECT * FROM venues WHERE is_active=1").fetchall()
    pending_needs_attention = check_pending_events()
    
    db.close()

    return render_template('calendar.html', year=year, month=month,
                           month_name=MONTH_NAMES_FR[month],
                           weeks=weeks, booked_dict=booked_dict,
                           today_str=today_str, venues=venues,
                           time_slots=TIME_SLOTS, venue_filter=venue_filter or '',
                           pending_needs_attention=pending_needs_attention)

# ─── Events ──────────────────────────────────────────────────────────
DEFAULT_SERVICES = {
    'location': {'name': 'Location de la salle', 'default_price': 0, 'required': True},
    'individuel': {'name': 'Service individuel', 'default_price': 5000},
    'cafe': {'name': 'Service café', 'default_price': 10000},
    'groupe': {'name': 'Groupe interdit', 'default_price': 15000},
    'photo': {'name': 'Photo', 'default_price': 8000},
    'deco': {'name': 'Déco el Hana', 'default_price': 25000},
    'panneaux': {'name': 'Panneaux de réception', 'default_price': 12000},
    'table': {'name': "Table d'honneur", 'default_price': 7000},
}

@app.route('/evenement/nouveau', methods=['GET', 'POST'])
@app.route('/evenement/<int:event_id>/modifier', methods=['GET', 'POST'])
def event_form(event_id=None):
    db = get_db()
    event = None
    client = None
    event_lines = []
    custom_lines = []

    if event_id:
        event = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if not event:
            flash("Événement introuvable", "danger")
            db.close()
            return redirect(url_for('index'))
        client = db.execute("SELECT * FROM clients WHERE id=?", (event['client_id'],)).fetchone()
        all_lines = db.execute("SELECT * FROM event_lines WHERE event_id=?", (event_id,)).fetchall()

        predefined_names = [v['name'] for v in DEFAULT_SERVICES.values()] + ['Autre']
        for line in all_lines:
            if line['description'] in predefined_names:
                event_lines.append(line)
            else:
                custom_lines.append(line)

    venues = db.execute("SELECT * FROM venues WHERE is_active=1").fetchall()

    if request.method == 'POST':
        data = request.form
        title = data.get('title', '').strip()
        client_name = data.get('client_name', '').strip()
        client_phone = data.get('client_phone', '').strip()
        client_phone2 = data.get('client_phone2', '').strip()
        client_email = data.get('client_email', '').strip()
        client_address = data.get('client_address', '').strip()
        venue_id = data.get('venue_id', type=int)
        venue_id2 = data.get('venue_id2', type=int)
        event_type = data.get('event_type', 'Mariage')
        event_date = data.get('event_date')
        time_slot = data.get('time_slot', 'Soirée')
        guests_men = data.get('guests_men', 0, type=int)
        guests_women = data.get('guests_women', 0, type=int)
        # Default to 'en attente' for new events
        status = data.get('status', 'en attente') if not event_id else data.get('status', event['status'])
        notes = data.get('notes', '').strip()
        total_amount = data.get('total_amount', 0, type=float)
        deposit_required = data.get('deposit_required', 20000, type=float)

        line_descs = request.form.getlist('line_desc[]')
        line_amounts = request.form.getlist('line_amount[]')
        line_costs = request.form.getlist('line_is_cost[]')

        service_location = data.get('service_location')
        price_location = data.get('price_location', 0, type=float)
        service_individuel = data.get('service_individuel')
        price_individuel = data.get('price_individuel', 0, type=float)
        service_cafe = data.get('service_cafe')
        price_cafe = data.get('price_cafe', 0, type=float)
        service_groupe = data.get('service_groupe')
        price_groupe = data.get('price_groupe', 0, type=float)
        service_photo = data.get('service_photo')
        price_photo = data.get('price_photo', 0, type=float)
        service_deco = data.get('service_deco')
        price_deco = data.get('price_deco', 0, type=float)
        service_panneaux = data.get('service_panneaux')
        price_panneaux = data.get('price_panneaux', 0, type=float)
        service_table = data.get('service_table')
        price_table = data.get('price_table', 0, type=float)
        service_autre = data.get('service_autre')
        price_autre = data.get('price_autre', 0, type=float)
        autre_name = data.get('autre_name', '').strip() or 'Autre'

        errors = []
        if not title:
            errors.append("Le titre est requis")
        if not client_name:
            errors.append("Le nom du client est requis")
        if not client_phone:
            errors.append("Le téléphone est requis")
        if not event_date:
            errors.append("La date est requise")
        if not venue_id:
            errors.append("Le lieu est requis")

        if errors:
            for e in errors:
                flash(e, 'danger')
            db.close()
            return render_template('event_form.html', event=event, client=client,
                                   event_lines=event_lines, custom_lines=custom_lines, venues=venues,
                                   time_slots=TIME_SLOTS, event_types=EVENT_TYPES,
                                   statuses=EVENT_STATUSES, event_id=event_id)

        if client:
            db.execute("UPDATE clients SET name=?, phone=?, phone2=?, email=?, address=? WHERE id=?",
                       (client_name, client_phone, client_phone2, client_email, client_address, client['id']))
            client_id = client['id']
        else:
            cur = db.execute("INSERT INTO clients (name, phone, phone2, email, address) VALUES (?,?,?,?,?)",
                            (client_name, client_phone, client_phone2, client_email, client_address))
            client_id = cur.lastrowid

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        if event:
            db.execute("UPDATE events SET title=?, client_id=?, venue_id=?, venue_id2=?, event_type=?, event_date=?, "
                       "time_slot=?, guests_men=?, guests_women=?, status=?, notes=?, "
                       "total_amount=?, deposit_required=?, updated_at=? WHERE id=?",
                       (title, client_id, venue_id, venue_id2, event_type, event_date, time_slot,
                        guests_men, guests_women, status, notes, total_amount, deposit_required, now_str, event_id))
            db.execute("DELETE FROM event_lines WHERE event_id=?", (event_id,))
        else:
            cur = db.execute("INSERT INTO events (title, client_id, venue_id, venue_id2, event_type, event_date, "
                            "time_slot, guests_men, guests_women, status, notes, total_amount, deposit_required, "
                            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (title, client_id, venue_id, venue_id2, event_type, event_date, time_slot,
                             guests_men, guests_women, status, notes, total_amount, deposit_required, now_str, now_str))
            event_id = cur.lastrowid

        # Insert service lines
        if price_location > 0:
            db.execute("INSERT INTO event_lines (event_id, description, amount, is_cost) VALUES (?,?,?,0)",
                      (event_id, 'Location de la salle', price_location))
        if service_individuel and price_individuel > 0:
            db.execute("INSERT INTO event_lines (event_id, description, amount, is_cost) VALUES (?,?,?,0)",
                      (event_id, 'Service individuel', price_individuel))
        if service_cafe and price_cafe > 0:
            db.execute("INSERT INTO event_lines (event_id, description, amount, is_cost) VALUES (?,?,?,0)",
                      (event_id, 'Service café', price_cafe))
        if service_groupe and price_groupe > 0:
            db.execute("INSERT INTO event_lines (event_id, description, amount, is_cost) VALUES (?,?,?,0)",
                      (event_id, 'Groupe interdit', price_groupe))
        if service_photo and price_photo > 0:
            db.execute("INSERT INTO event_lines (event_id, description, amount, is_cost) VALUES (?,?,?,0)",
                      (event_id, 'Photo', price_photo))
        if service_deco and price_deco > 0:
            db.execute("INSERT INTO event_lines (event_id, description, amount, is_cost) VALUES (?,?,?,0)",
                      (event_id, 'Déco el Hana', price_deco))
        if service_panneaux and price_panneaux > 0:
            db.execute("INSERT INTO event_lines (event_id, description, amount, is_cost) VALUES (?,?,?,0)",
                      (event_id, 'Panneaux de réception', price_panneaux))
        if service_table and price_table > 0:
            db.execute("INSERT INTO event_lines (event_id, description, amount, is_cost) VALUES (?,?,?,0)",
                      (event_id, "Table d'honneur", price_table))
        if service_autre and price_autre > 0:
            db.execute("INSERT INTO event_lines (event_id, description, amount, is_cost) VALUES (?,?,?,0)",
                      (event_id, autre_name or 'Autre', price_autre))

        for i, desc in enumerate(line_descs):
            if desc.strip():
                amount = float(line_amounts[i]) if i < len(line_amounts) else 0
                is_cost = 1 if str(i) in line_costs else 0
                db.execute("INSERT INTO event_lines (event_id, description, amount, is_cost) VALUES (?,?,?,?)",
                          (event_id, desc.strip(), amount, is_cost))

        db.commit()
        db.close()
        flash("Événement enregistré avec succès!", "success")
        return redirect(url_for('event_detail', event_id=event_id))

    db.close()
    return render_template('event_form.html', event=event, client=client,
                           event_lines=event_lines, custom_lines=custom_lines, venues=venues,
                           time_slots=TIME_SLOTS, event_types=EVENT_TYPES,
                           statuses=EVENT_STATUSES, event_id=event_id)

@app.route('/evenement/<int:event_id>')
def event_detail(event_id):
    db = get_db()
    event = db.execute(
        "SELECT e.*, c.name as client_name, c.id as client_id, c.phone, c.phone2, c.email, c.address, "
        "v.name as venue_name, v.capacity_men, v.capacity_women, "
        "v2.name as venue2_name FROM events e "
        "JOIN clients c ON e.client_id=c.id JOIN venues v ON e.venue_id=v.id "
        "LEFT JOIN venues v2 ON e.venue_id2=v2.id "
        "WHERE e.id=?", (event_id,)).fetchone()
    if not event:
        flash("Événement introuvable", "danger")
        db.close()
        return redirect(url_for('index'))

    event_lines = db.execute("SELECT * FROM event_lines WHERE event_id=?", (event_id,)).fetchall()
    payments = db.execute(
        "SELECT * FROM payments WHERE event_id=? ORDER BY payment_date DESC", 
        (event_id,)
    ).fetchall()
    
    # Calculate financials (excluding refunded payments)
    total_paid = db.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM payments WHERE event_id=? AND is_refunded=0",
        (event_id,)
    ).fetchone()['s']
    
    total_refunded = db.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM payments WHERE event_id=? AND is_refunded=1",
        (event_id,)
    ).fetchone()['s']
    
    deposit = db.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM payments WHERE event_id=? AND payment_type='acompte' AND is_refunded=0",
        (event_id,)
    ).fetchone()['s']
    
    # Revenue and costs from event lines
    total_revenue = db.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM event_lines WHERE event_id=? AND is_cost=0",
        (event_id,)
    ).fetchone()['s']
    
    total_costs = db.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM event_lines WHERE event_id=? AND is_cost=1",
        (event_id,)
    ).fetchone()['s']
    
    profit = float(total_revenue) - float(total_costs)

    # Get expenses linked to this event
    event_expenses = db.execute(
        "SELECT * FROM expenses WHERE event_id=? ORDER BY expense_date DESC",
        (event_id,)
    ).fetchall()
    total_expenses = db.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM expenses WHERE event_id=?",
        (event_id,)
    ).fetchone()['s']

    # Adjusted profit = revenue - costs - expenses
    adjusted_profit = profit - float(total_expenses)

    # Check if event is pending for more than 48h
    needs_confirmation = False
    if event['status'] == 'en attente':
        try:
            created_at = event['created_at'] if 'created_at' in event.keys() else None
            if created_at:
                created = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
                if (datetime.now() - created) > timedelta(hours=48):
                    needs_confirmation = True
        except (ValueError, TypeError):
            pass

    db.close()
    return render_template('event_detail.html', event=event, event_lines=event_lines,
                           payments=payments, total_paid=total_paid, deposit=deposit,
                           total_refunded=total_refunded, total_revenue=total_revenue,
                           total_costs=total_costs, profit=profit,
                           needs_confirmation=needs_confirmation, statuses=EVENT_STATUSES,
                           event_expenses=event_expenses, total_expenses=float(total_expenses),
                           adjusted_profit=adjusted_profit, today_str=date.today().isoformat())

@app.route('/evenement/<int:event_id>/paiement', methods=['POST'])
def add_payment(event_id):
    try:
        db = get_db()
        data = request.form
        amount = data.get('amount', 0, type=float)
        method = data.get('method', 'espèces')
        payment_type = data.get('payment_type', 'acompte')
        reference = data.get('reference', '').strip()
        notes = data.get('notes', '').strip()

        if amount <= 0:
            flash("Montant invalide", "danger")
        else:
            db.execute(
                "INSERT INTO payments (event_id, amount, method, payment_type, reference, notes) VALUES (?,?,?,?,?,?)",
                (event_id, amount, method, payment_type, reference, notes)
            )
            db.commit()
            flash("Paiement enregistré!", "success")
        db.close()
    except Exception as e:
        flash(f"Erreur: {str(e)}", "danger")
    return redirect(url_for('event_detail', event_id=event_id))

@app.route('/evenement/<int:event_id>/paiement/<int:payment_id>/rembourser', methods=['POST'])
def refund_payment(event_id, payment_id):
    """Mark a payment as refunded (audit trail - never delete)."""
    try:
        db = get_db()
        reason = request.form.get('refund_reason', '').strip()

        payment = db.execute(
            "SELECT * FROM payments WHERE id=? AND event_id=?",
            (payment_id, event_id)
        ).fetchone()

        if not payment:
            flash("Paiement introuvable", "danger")
        elif payment['is_refunded']:
            flash("Ce paiement a déjà été remboursé", "warning")
        else:
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            # Append refund info to notes (cross-db compatible concatenation)
            existing_notes = payment.get('notes', '') or ''
            refund_note = f" [REMBOURSÉ: {reason}]" if reason else " [REMBOURSÉ]"
            new_notes = existing_notes + refund_note
            db.execute(
                "UPDATE payments SET is_refunded=1, notes=? WHERE id=?",
                (new_notes, payment_id)
            )
            db.commit()
            flash("Paiement marqué comme remboursé", "success")
        db.close()
    except Exception as e:
        flash(f"Erreur: {str(e)}", "danger")
    return redirect(url_for('event_detail', event_id=event_id))

@app.route('/evenement/<int:event_id>/statut', methods=['POST'])
def update_event_status(event_id):
    """Update event status with proper flow."""
    try:
        db = get_db()
        new_status = request.form.get('status', '')
        new_date = request.form.get('new_date', '').strip()

        if new_status not in EVENT_STATUSES:
            flash("Statut invalide", "danger")
            db.close()
            return redirect(url_for('event_detail', event_id=event_id))

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if new_status == 'changé de date' and new_date:
            db.execute("UPDATE events SET status=?, event_date=?, updated_at=? WHERE id=?",
                      (new_status, new_date, now_str, event_id))
            flash(f"Date changée à {new_date}. Statut mis à jour.", "success")
        else:
            db.execute("UPDATE events SET status=?, updated_at=? WHERE id=?",
                      (new_status, now_str, event_id))

            status_messages = {
                'confirmé': "Événement confirmé!",
                'en attente': "Statut remis à 'en attente'",
                'changé de date': "Statut mis à jour",
                'terminé': "Événement marqué comme terminé",
                'annulé': "Événement annulé"
            }
            flash(status_messages.get(new_status, "Statut mis à jour"), "success")

        db.commit()
        db.close()
    except Exception as e:
        flash(f"Erreur: {str(e)}", "danger")
    return redirect(url_for('event_detail', event_id=event_id))

@app.route('/evenement/<int:event_id>/supprimer', methods=['POST'])
def delete_event(event_id):
    try:
        db = get_db()
        db.execute("DELETE FROM event_lines WHERE event_id=?", (event_id,))
        db.execute("DELETE FROM payments WHERE event_id=?", (event_id,))
        db.execute("DELETE FROM expenses WHERE event_id=?", (event_id,))
        db.execute("DELETE FROM events WHERE id=?", (event_id,))
        db.commit()
        db.close()
        flash("Événement supprimé", "success")
    except Exception as e:
        flash(f"Erreur lors de la suppression: {str(e)}", "danger")
    return redirect(url_for('index'))

@app.route('/evenement/<int:event_id>/depense', methods=['POST'])
def add_event_expense(event_id):
    """Add expenses linked to an event - handles multiple categories."""
    try:
        db = get_db()
        expense_date = request.form.get('expense_date', date.today().isoformat())
        
        categories_added = 0
        
        # Fixed categories
        for cat_key, cat_name, default_price in [
            ('serveurs', 'Serveurs', 15000),
            ('nettoyeurs', 'Nettoyeurs', 8000),
            ('securite', 'Sécurité', 10000),
        ]:
            if request.form.get(f'cat_{cat_key}'):
                amount = request.form.get(f'amount_{cat_key}', default_price, type=float)
                if amount > 0:
                    db.execute(
                        "INSERT INTO expenses (expense_date, category, description, amount, event_id, method) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (expense_date, cat_name, cat_name, amount, event_id, 'espèces')
                    )
                    categories_added += 1
        
        # Custom "Autre" category
        if request.form.get('cat_autre'):
            autre_name = request.form.get('autre_name', '').strip() or 'Autre'
            autre_amount = request.form.get('amount_autre', 0, type=float)
            if autre_amount > 0:
                db.execute(
                    "INSERT INTO expenses (expense_date, category, description, amount, event_id, method) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (expense_date, 'Autre', f'Autre: {autre_name}', autre_amount, event_id, 'espèces')
                )
                categories_added += 1
        
        if categories_added > 0:
            db.commit()
            flash(f"{categories_added} dépense(s) enregistrée(s)!", "success")
        else:
            flash("Sélectionnez au moins une catégorie avec un montant", "warning")
        db.close()
    except Exception as e:
        flash(f"Erreur: {str(e)}", "danger")
    return redirect(url_for('event_detail', event_id=event_id))

@app.route('/depense/<int:expense_id>/supprimer', methods=['POST'])
def delete_expense(expense_id):
    """Delete an expense."""
    try:
        db = get_db()
        expense = db.execute("SELECT event_id FROM expenses WHERE id=?", (expense_id,)).fetchone()
        if expense:
            event_id = expense['event_id']
            db.execute("DELETE FROM expenses WHERE id=?", (expense_id,))
            db.commit()
            db.close()
            flash("Dépense supprimée", "success")
            if event_id:
                return redirect(url_for('event_detail', event_id=event_id))
        else:
            db.close()
            flash("Dépense introuvable", "danger")
    except Exception as e:
        flash(f"Erreur: {str(e)}", "danger")
    return redirect(url_for('expenses'))

@app.route('/evenements')
def event_list():
    db = get_db()
    status_filter = request.args.get('status', '')
    search = request.args.get('q', '').strip()

    query = ("SELECT e.*, c.name as client_name, v.name as venue_name FROM events e "
             "JOIN clients c ON e.client_id=c.id JOIN venues v ON e.venue_id=v.id WHERE 1=1")
    params = []

    if status_filter:
        query += " AND e.status=?"
        params.append(status_filter)
    if search:
        query += " AND (e.title LIKE ? OR c.name LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%'])

    query += " ORDER BY e.event_date DESC"
    events = db.execute(query, params).fetchall()
    db.close()
    return render_template('event_list.html', events=events, statuses=EVENT_STATUSES,
                           status_filter=status_filter, search=search)

# ─── Financial Reports ──────────────────────────────────────────────
@app.route('/finances')
def financials():
    db = get_db()
    
    # Date range filter
    start_date = request.args.get('start_date', (date.today() - timedelta(days=365)).isoformat())
    end_date = request.args.get('end_date', date.today().isoformat())
    
    # Check for CSV export
    export_csv = request.args.get('export', type=int)
    
    # Total revenue (excluding refunded)
    total_revenue = db.execute(
        "SELECT COALESCE(SUM(p.amount),0) as s FROM payments p "
        "JOIN events e ON p.event_id=e.id "
        "WHERE p.payment_date BETWEEN ? AND ? AND p.is_refunded=0",
        (start_date, end_date)
    ).fetchone()['s']
    
    # Total outstanding (event totals minus paid)
    total_outstanding = db.execute(
        "SELECT COALESCE(SUM(e.total_amount - COALESCE(p.paid_total, 0)), 0) as s "
        "FROM events e "
        "LEFT JOIN (SELECT event_id, SUM(amount) as paid_total FROM payments WHERE is_refunded=0 GROUP BY event_id) p ON p.event_id = e.id "
        "WHERE e.event_date BETWEEN ? AND ? AND e.status NOT IN ('annulé', 'terminé')",
        (start_date, end_date)
    ).fetchone()['s']
    
    # Total refunded
    total_refunded = db.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM payments "
        "WHERE payment_date BETWEEN ? AND ? AND is_refunded=1",
        (start_date, end_date)
    ).fetchone()['s']
    
    # Revenue by event type
    revenue_by_type = db.execute(
        "SELECT e.event_type, "
        "  COALESCE(SUM(p.amount), 0) as revenue, "
        "  COUNT(DISTINCT e.id) as count "
        "FROM events e "
        "LEFT JOIN payments p ON p.event_id = e.id AND p.is_refunded = 0 "
        "WHERE e.event_date BETWEEN ? AND ? AND e.status != 'annulé' "
        "GROUP BY e.event_type "
        "ORDER BY revenue DESC",
        (start_date, end_date)
    ).fetchall()
    
    # Top clients by revenue
    top_clients = db.execute(
        "SELECT c.id, c.name, "
        "  COALESCE(SUM(e.total_amount), 0) as total_billed, "
        "  COALESCE(SUM(CASE WHEN p.is_refunded=0 THEN p.amount ELSE 0 END), 0) as total_paid, "
        "  COALESCE(SUM(e.total_amount), 0) - COALESCE(SUM(CASE WHEN p.is_refunded=0 THEN p.amount ELSE 0 END), 0) as total_remaining "
        "FROM clients c "
        "JOIN events e ON e.client_id = c.id "
        "LEFT JOIN payments p ON p.event_id = e.id "
        "WHERE e.event_date BETWEEN ? AND ? "
        "GROUP BY c.id, c.name "
        "HAVING COALESCE(SUM(e.total_amount), 0) > 0 "
        "ORDER BY total_billed DESC "
        "LIMIT 10",
        (start_date, end_date)
    ).fetchall()
    
    # All payments in period
    payments = db.execute(
        "SELECT p.*, e.title, e.event_date, c.name as client_name "
        "FROM payments p "
        "JOIN events e ON p.event_id = e.id "
        "JOIN clients c ON e.client_id = c.id "
        "WHERE p.payment_date BETWEEN ? AND ? "
        "ORDER BY p.payment_date DESC",
        (start_date, end_date)
    ).fetchall()
    
    # Event financials
    event_financials = db.execute(
        "SELECT e.id, e.title, e.event_date, e.event_type, e.status, e.total_amount, "
        "  c.name as client_name, "
        "  COALESCE(SUM(CASE WHEN el.is_cost=0 THEN el.amount ELSE 0 END), 0) as total_revenue, "
        "  COALESCE(SUM(CASE WHEN el.is_cost=1 THEN el.amount ELSE 0 END), 0) as total_costs, "
        "  COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.event_id=e.id AND p.is_refunded=0), 0) as total_paid "
        "FROM events e "
        "JOIN clients c ON e.client_id = c.id "
        "LEFT JOIN event_lines el ON el.event_id = e.id "
        "WHERE e.event_date BETWEEN ? AND ? AND e.status != 'annulé' "
        "GROUP BY e.id, e.title, e.event_date, e.event_type, e.status, e.total_amount, c.name "
        "ORDER BY e.event_date DESC",
        (start_date, end_date)
    ).fetchall()
    
    # Calculate totals for each event
    event_financials_list = []
    for ef in event_financials:
        ef_dict = ef
        ef_dict['profit'] = ef_dict['total_revenue'] - ef_dict['total_costs']
        ef_dict['remaining'] = ef_dict['total_amount'] - ef_dict['total_paid']
        event_financials_list.append(ef_dict)
    
    # Total profit (revenue - costs across all events)
    total_profit = sum(ef['profit'] for ef in event_financials_list)
    
    db.close()
    
    # Handle CSV export
    if export_csv:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Date', 'Événement', 'Client', 'Type', 'Revenus', 'Coûts', 'Bénéfice', 'Payé', 'Reste', 'Statut'])
        for ef in event_financials_list:
            writer.writerow([
                ef['event_date'][:10], ef['title'], ef['client_name'], ef['event_type'],
                ef['total_revenue'], ef['total_costs'], ef['profit'],
                ef['total_paid'], ef['remaining'], ef['status']
            ])
        
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        response.headers['Content-Disposition'] = f'attachment; filename=finances_{start_date}_{end_date}.csv'
        return response
    
    return render_template('financials.html',
                           start_date=start_date, end_date=end_date,
                           total_revenue=total_revenue,
                           total_outstanding=total_outstanding,
                           total_refunded=total_refunded,
                           total_profit=total_profit,
                           revenue_by_type=revenue_by_type,
                           top_clients=top_clients,
                           payments=payments,
                           event_financials=event_financials_list)

# ─── Clients ─────────────────────────────────────────────────────────
@app.route('/clients')
def client_list():
    db = get_db()
    search = request.args.get('q', '').strip()

    query = ("SELECT c.*, "
             "(SELECT COUNT(*) FROM events WHERE client_id=c.id) as event_count, "
             "(SELECT COALESCE(SUM(CASE WHEN p.is_refunded=0 THEN p.amount ELSE 0 END),0) FROM payments p JOIN events e ON p.event_id=e.id WHERE e.client_id=c.id) as total_paid, "
             "(SELECT COALESCE(SUM(e.total_amount),0) FROM events e WHERE e.client_id=c.id) as total_owed "
             "FROM clients c WHERE 1=1")
    params = []

    if search:
        query += " AND (c.name LIKE ? OR c.phone LIKE ? OR c.email LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])

    query += " ORDER BY c.created_at DESC"
    clients = db.execute(query, params).fetchall()
    db.close()
    return render_template('client_list.html', clients=clients, search=search)

@app.route('/client/<int:client_id>')
def client_detail(client_id):
    db = get_db()
    client = db.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
    if not client:
        flash("Client introuvable", "danger")
        db.close()
        return redirect(url_for('client_list'))

    events = db.execute(
        "SELECT e.*, v.name as venue_name FROM events e "
        "JOIN venues v ON e.venue_id=v.id WHERE e.client_id=? ORDER BY e.event_date DESC",
        (client_id,)).fetchall()

    total_owed = db.execute(
        "SELECT COALESCE(SUM(total_amount),0) as s FROM events WHERE client_id=?",
        (client_id,)).fetchone()['s']
    
    total_paid = db.execute(
        "SELECT COALESCE(SUM(CASE WHEN p.is_refunded=0 THEN p.amount ELSE 0 END),0) as s "
        "FROM payments p JOIN events e ON p.event_id=e.id WHERE e.client_id=?",
        (client_id,)).fetchone()['s']

    # Get all payments for timeline (chronological)
    all_payments = db.execute(
        "SELECT p.*, e.title as event_title, e.id as event_id "
        "FROM payments p "
        "JOIN events e ON p.event_id=e.id "
        "WHERE e.client_id=? "
        "ORDER BY p.payment_date DESC",
        (client_id,)).fetchall()

    # Detailed financials per event
    event_financials = {}
    for ev in events:
        # Revenue from lines
        revenue = db.execute(
            "SELECT COALESCE(SUM(amount),0) as s FROM event_lines WHERE event_id=? AND is_cost=0",
            (ev['id'],)).fetchone()['s']
        
        # Costs from lines
        costs = db.execute(
            "SELECT COALESCE(SUM(amount),0) as s FROM event_lines WHERE event_id=? AND is_cost=1",
            (ev['id'],)).fetchone()['s']
        
        # Paid (excluding refunded)
        paid = db.execute(
            "SELECT COALESCE(SUM(amount),0) as s FROM payments WHERE event_id=? AND is_refunded=0",
            (ev['id'],)).fetchone()['s']
        
        event_financials[ev['id']] = {
            'revenue': float(revenue),
            'costs': float(costs),
            'profit': float(revenue) - float(costs),
            'paid': float(paid),
            'remaining': ev['total_amount'] - float(paid)
        }

    db.close()
    return render_template('client_detail.html', client=client, events=events,
                           total_owed=total_owed, total_paid=total_paid,
                           all_payments=all_payments, event_financials=event_financials)

# ─── Expenses ────────────────────────────────────────────────────────
EXPENSE_CATEGORIES = ['Serveurs', 'Nettoyeurs', 'Sécurité', 'Autre']

@app.route('/depenses', methods=['GET'])
def expenses():
    """Expense list with filters."""
    db = get_db()
    
    start_date = request.args.get('start_date', (date.today() - timedelta(days=30)).isoformat())
    end_date = request.args.get('end_date', date.today().isoformat())
    category_filter = request.args.get('category', '')
    
    query = "SELECT ex.*, e.title as event_title FROM expenses ex LEFT JOIN events e ON ex.event_id = e.id WHERE 1=1"
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
    expenses = db.execute(query, params).fetchall()
    
    # Calculate totals
    total_expenses = sum(float(e['amount']) for e in expenses)
    
    # This month's expenses
    today = date.today()
    month_start = today.replace(day=1).isoformat()
    month_expenses = db.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM expenses WHERE expense_date >= ?",
        (month_start,)
    ).fetchone()['s']
    
    # Average expense
    avg_expense = total_expenses / len(expenses) if expenses else 0
    
    # Expenses by category
    expenses_by_category = db.execute(
        "SELECT category, SUM(amount) as total, COUNT(*) as count "
        "FROM expenses WHERE expense_date >= ? AND expense_date <= ? "
        "GROUP BY category ORDER BY total DESC",
        (start_date, end_date)
    ).fetchall()
    
    # Recent events for dropdown
    recent_events = db.execute(
        "SELECT id, title, event_date FROM events ORDER BY event_date DESC LIMIT 20"
    ).fetchall()
    
    db.close()
    
    return render_template('expenses.html',
                           expenses=expenses,
                           start_date=start_date, end_date=end_date,
                           category_filter=category_filter,
                           categories=EXPENSE_CATEGORIES,
                           total_expenses=total_expenses,
                           expenses_this_month=float(month_expenses),
                           avg_expense=avg_expense,
                           expenses_by_category=expenses_by_category,
                           recent_events=recent_events,
                           today_str=date.today().isoformat())

@app.route('/depenses/ajouter', methods=['POST'])
def add_expense():
    """Add a new expense."""
    try:
        db = get_db()

        expense_date = request.form.get('expense_date', date.today().isoformat())
        category = request.form.get('category', '')
        description = request.form.get('description', '').strip()
        amount = request.form.get('amount', 0, type=float)
        event_id = request.form.get('event_id', type=int) or None
        method = request.form.get('method', 'espèces')
        reference = request.form.get('reference', '').strip()
        notes = request.form.get('notes', '').strip()

        if not category:
            flash("La catégorie est requise", "danger")
            db.close()
            return redirect(url_for('expenses'))
        if amount <= 0:
            flash("Le montant doit être supérieur à 0", "danger")
            db.close()
            return redirect(url_for('expenses'))

        # For 'Autre' category, use description as custom name
        if category == 'Autre' and description:
            description = f"Autre: {description}"

        db.execute(
            "INSERT INTO expenses (expense_date, category, description, amount, event_id, method, reference, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (expense_date, category, description, amount, event_id, method, reference, notes)
        )
        db.commit()
        db.close()

        flash("Dépense enregistrée!", "success")
    except Exception as e:
        flash(f"Erreur: {str(e)}", "danger")
    return redirect(url_for('expenses'))

# ─── Accounting Dashboard ───────────────────────────────────────────
@app.route('/comptabilite')
def accounting():
    """Accounting dashboard with P&L."""
    db = get_db()
    
    start_date = request.args.get('start_date', (date.today() - timedelta(days=365)).isoformat())
    end_date = request.args.get('end_date', date.today().isoformat())
    
    # Total income (payments received in period)
    total_income = db.execute(
        "SELECT COALESCE(SUM(p.amount),0) as s FROM payments p "
        "WHERE p.payment_date BETWEEN ? AND ? AND p.is_refunded=0",
        (start_date, end_date)
    ).fetchone()['s']
    
    # Total expenses
    total_expenses = db.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM expenses "
        "WHERE expense_date BETWEEN ? AND ?",
        (start_date, end_date)
    ).fetchone()['s']
    
    # Net profit
    net_profit = float(total_income) - float(total_expenses)
    profit_margin = (net_profit / float(total_income) * 100) if total_income > 0 else 0
    
    # Expenses by category
    expenses_by_category = db.execute(
        "SELECT category, SUM(amount) as total, COUNT(*) as count "
        "FROM expenses WHERE expense_date BETWEEN ? AND ? "
        "GROUP BY category ORDER BY total DESC",
        (start_date, end_date)
    ).fetchall()
    
    # Monthly P&L (last 12 months or within date range)
    monthly_pl = []
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    
    current = start.replace(day=1)
    while current <= end:
        month_start = current.strftime('%Y-%m-%d')
        if current.month == 12:
            month_end = current.replace(year=current.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = current.replace(month=current.month + 1, day=1) - timedelta(days=1)
        month_end_str = month_end.strftime('%Y-%m-%d')
        
        # Income for this month
        month_income = db.execute(
            "SELECT COALESCE(SUM(p.amount),0) as s FROM payments p "
            "WHERE p.payment_date >= ? AND p.payment_date <= ? AND p.is_refunded=0",
            (month_start, month_end_str)
        ).fetchone()['s']
        
        # Expenses for this month
        month_expenses = db.execute(
            "SELECT COALESCE(SUM(amount),0) as s FROM expenses "
            "WHERE expense_date >= ? AND expense_date <= ?",
            (month_start, month_end_str)
        ).fetchone()['s']
        
        month_profit = float(month_income) - float(month_expenses)
        month_margin = (month_profit / float(month_income) * 100) if month_income > 0 else 0
        
        monthly_pl.append({
            'month': month_start[:7],
            'month_name': f"{MONTH_NAMES_FR[current.month]} {current.year}",
            'income': float(month_income),
            'expenses': float(month_expenses),
            'profit': month_profit,
            'margin': month_margin
        })
        
        # Move to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    
    monthly_pl.reverse()  # Most recent first
    
    db.close()
    
    return render_template('accounting.html',
                           start_date=start_date, end_date=end_date,
                           total_income=float(total_income),
                           total_expenses=float(total_expenses),
                           net_profit=net_profit,
                           profit_margin=profit_margin,
                           expenses_by_category=expenses_by_category,
                           monthly_pl=monthly_pl)

# ─── Contract PDF ────────────────────────────────────────────────────
@app.route('/evenement/<int:event_id>/contrat')
def generate_contract(event_id):
    db = get_db()
    event = db.execute(
        "SELECT e.*, c.name as client_name, c.phone, c.phone2, c.email, c.address, "
        "v.name as venue_name, v.capacity_men, v.capacity_women, "
        "v2.name as venue2_name FROM events e "
        "JOIN clients c ON e.client_id=c.id JOIN venues v ON e.venue_id=v.id "
        "LEFT JOIN venues v2 ON e.venue_id2=v2.id "
        "WHERE e.id=?", (event_id,)).fetchone()

    if not event:
        flash("Événement introuvable", "danger")
        db.close()
        return redirect(url_for('index'))

    payments = db.execute("SELECT * FROM payments WHERE event_id=? AND is_refunded=0 ORDER BY payment_date DESC", (event_id,)).fetchall()
    total_paid = db.execute("SELECT COALESCE(SUM(amount),0) as s FROM payments WHERE event_id=? AND is_refunded=0",
                           (event_id,)).fetchone()['s']
    event_lines = db.execute("SELECT * FROM event_lines WHERE event_id=?", (event_id,)).fetchall()

    db.close()

    pdf_bytes = generate_contract_pdf(
        event,
        [ payments],
        total_paid,
        [ event_lines]
    )

    response = make_response(pdf_bytes)
    response.headers['Content-Type'] = 'application/pdf'
    safe_title = event['title'].replace(' ', '_')[:30]
    response.headers['Content-Disposition'] = f'inline; filename=contrat_{safe_title}_{event_id}.pdf'
    return response

# ─── Receipt ─────────────────────────────────────────────────────────
@app.route('/evenement/<int:event_id>/recu/<int:payment_id>')
def generate_receipt(event_id, payment_id):
    db = get_db()
    event = db.execute(
        "SELECT e.*, c.name as client_name, c.phone, c.address, "
        "v.name as venue_name FROM events e "
        "JOIN clients c ON e.client_id=c.id JOIN venues v ON e.venue_id=v.id "
        "WHERE e.id=?", (event_id,)).fetchone()

    if not event:
        flash("Événement introuvable", "danger")
        db.close()
        return redirect(url_for('index'))

    payment = db.execute("SELECT * FROM payments WHERE id=? AND event_id=?",
                         (payment_id, event_id)).fetchone()
    if not payment:
        flash("Paiement introuvable", "danger")
        db.close()
        return redirect(url_for('event_detail', event_id=event_id))

    total_paid_before = db.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM payments WHERE event_id=? AND payment_date < ? AND is_refunded=0",
        (event_id, payment['payment_date'])).fetchone()['s']
    total_paid_after = total_paid_before + payment['amount']
    remaining = event['total_amount'] - total_paid_after
    receipt_no = f"{payment['payment_date'][:4]}-{payment_id:04d}"

    db.close()

    html = generate_receipt_html(
        event, payment, total_paid_before, total_paid_after,
        remaining, receipt_no
    )
    response = make_response(html)
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    return response

# ─── Settings ────────────────────────────────────────────────────────
@app.route('/parametres', methods=['GET', 'POST'])
def settings():
    db = get_db()
    if request.method == 'POST':
        for venue_id in request.form.getlist('venue_id'):
            cap_m = request.form.get(f'capacity_men_{venue_id}', 0, type=int)
            cap_w = request.form.get(f'capacity_women_{venue_id}', 0, type=int)
            db.execute("UPDATE venues SET capacity_men=?, capacity_women=? WHERE id=?",
                      (cap_m, cap_w, venue_id))

        deposit_min = request.form.get('deposit_min', 20000, type=float)
        hall_name = request.form.get('hall_name', 'Samba Fête')
        currency = request.form.get('currency', 'DA')
        set_setting('deposit_min', str(deposit_min))
        set_setting('hall_name', hall_name)
        set_setting('currency', currency)

        new_name = request.form.get('new_venue_name', '').strip()
        if new_name:
            new_cap_m = request.form.get('new_venue_cap_m', 0, type=int)
            new_cap_w = request.form.get('new_venue_cap_w', 0, type=int)
            db.execute("INSERT INTO venues (name, capacity_men, capacity_women) VALUES (?,?,?)",
                      (new_name, new_cap_m, new_cap_w))

        db.commit()
        flash("Paramètres enregistrés!", "success")

    venues = db.execute("SELECT * FROM venues ORDER BY id").fetchall()
    settings_rows = db.execute("SELECT key, value FROM settings").fetchall()
    settings_dict = {row['key']: row['value'] for row in settings_rows}
    deposit_min = settings_dict.get('deposit_min', '20000')
    hall_name = settings_dict.get('hall_name', 'Samba Fête')
    currency = settings_dict.get('currency', 'DA')
    db.close()
    return render_template('settings.html', venues=venues, deposit_min=deposit_min,
                           hall_name=hall_name, currency=currency)

@app.route('/parametres/lieu/<int:venue_id>/supprimer', methods=['POST'])
def delete_venue(venue_id):
    db = get_db()
    count = db.execute("SELECT COUNT(*) as c FROM events WHERE venue_id=?", (venue_id,)).fetchone()['c']
    if count > 0:
        flash("Impossible de supprimer: ce lieu a des événements", "danger")
    else:
        db.execute("DELETE FROM venues WHERE id=?", (venue_id,))
        db.commit()
        flash("Lieu supprimé", "success")
    db.close()
    return redirect(url_for('settings'))

# ─── API endpoints ───────────────────────────────────────────────────
@app.route('/api/calendar-events')
def api_calendar_events():
    db = get_db()
    year = request.args.get('year', date.today().year, type=int)
    month = request.args.get('month', date.today().month, type=int)

    first = f"{year}-{month:02d}-01"
    if month == 12:
        last = f"{year+1}-01-01"
    else:
        last = f"{year}-{month+1:02d}-01"

    events = db.execute(
        "SELECT e.id, e.title, e.event_date, e.time_slot, e.status, c.name as client_name, "
        "v.name as venue_name, COALESCE(v2.name, '') as venue2_name "
        "FROM events e JOIN clients c ON e.client_id=c.id JOIN venues v ON e.venue_id=v.id "
        "LEFT JOIN venues v2 ON e.venue_id2=v2.id "
        "WHERE e.event_date >= ? AND e.event_date < ? AND e.status != 'annulé' "
        "ORDER BY e.event_date",
        (first, last)).fetchall()

    result = [ events]
    db.close()
    return jsonify(result)

# ─── Export Endpoints ───────────────────────────────────────────────
@app.route('/export/events.ods')
def export_events():
    """Export events to ODS format."""
    db = get_db()
    
    # Get filter params
    status_filter = request.args.get('status', '')
    search = request.args.get('q', '').strip()
    
    query = ("SELECT e.*, c.name as client_name, v.name as venue_name, "
             "(SELECT COALESCE(SUM(p.amount),0) FROM payments p WHERE p.event_id=e.id AND p.is_refunded=0) as total_paid "
             "FROM events e "
             "JOIN clients c ON e.client_id=c.id JOIN venues v ON e.venue_id=v.id WHERE 1=1")
    params = []
    
    if status_filter:
        query += " AND e.status=?"
        params.append(status_filter)
    if search:
        query += " AND (e.title LIKE ? OR c.name LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%'])
    
    query += " ORDER BY e.event_date DESC"
    events = db.execute(query, params).fetchall()
    db.close()
    
    export_date = datetime.now().strftime('%Y-%m-%d %H:%M')
    ods_content = export_events_ods([ events], export_date)
    
    response = make_response(ods_content)
    response.headers['Content-Type'] = 'application/vnd.oasis.opendocument.spreadsheet'
    response.headers['Content-Disposition'] = f'attachment; filename=evenements_{date.today().isoformat()}.ods'
    return response


@app.route('/export/clients.ods')
def export_clients():
    """Export clients to ODS format."""
    db = get_db()
    
    search = request.args.get('q', '').strip()
    
    query = ("SELECT c.*, "
             "(SELECT COUNT(*) FROM events WHERE client_id=c.id) as event_count, "
             "(SELECT COALESCE(SUM(CASE WHEN p.is_refunded=0 THEN p.amount ELSE 0 END),0) FROM payments p JOIN events e ON p.event_id=e.id WHERE e.client_id=c.id) as total_paid, "
             "(SELECT COALESCE(SUM(e.total_amount),0) FROM events e WHERE e.client_id=c.id) as total_owed "
             "FROM clients c WHERE 1=1")
    params = []
    
    if search:
        query += " AND (c.name LIKE ? OR c.phone LIKE ? OR c.email LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
    
    query += " ORDER BY c.created_at DESC"
    clients = db.execute(query, params).fetchall()
    db.close()
    
    export_date = datetime.now().strftime('%Y-%m-%d %H:%M')
    ods_content = export_clients_ods([ clients], export_date)
    
    response = make_response(ods_content)
    response.headers['Content-Type'] = 'application/vnd.oasis.opendocument.spreadsheet'
    response.headers['Content-Disposition'] = f'attachment; filename=clients_{date.today().isoformat()}.ods'
    return response


@app.route('/export/payments.ods')
def export_payments():
    """Export payments to ODS format."""
    db = get_db()
    
    # Get all payments with related info
    payments = db.execute(
        "SELECT p.*, e.title, e.event_date, c.name as client_name "
        "FROM payments p "
        "JOIN events e ON p.event_id = e.id "
        "JOIN clients c ON e.client_id = c.id "
        "ORDER BY p.payment_date DESC"
    ).fetchall()
    db.close()
    
    export_date = datetime.now().strftime('%Y-%m-%d %H:%M')
    ods_content = export_payments_ods([ payments], export_date)
    
    response = make_response(ods_content)
    response.headers['Content-Type'] = 'application/vnd.oasis.opendocument.spreadsheet'
    response.headers['Content-Disposition'] = f'attachment; filename=paiements_{date.today().isoformat()}.ods'
    return response


@app.route('/export/finances.ods')
def export_finances():
    """Export financial report to ODS format."""
    db = get_db()
    
    start_date = request.args.get('start_date', (date.today() - timedelta(days=365)).isoformat())
    end_date = request.args.get('end_date', date.today().isoformat())
    
    # Get event financials
    event_financials = db.execute(
        "SELECT e.id, e.title, e.event_date, e.event_type, e.status, e.total_amount, "
        "  c.name as client_name, "
        "  COALESCE(SUM(CASE WHEN el.is_cost=0 THEN el.amount ELSE 0 END), 0) as total_revenue, "
        "  COALESCE(SUM(CASE WHEN el.is_cost=1 THEN el.amount ELSE 0 END), 0) as total_costs, "
        "  COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.event_id=e.id AND p.is_refunded=0), 0) as total_paid "
        "FROM events e "
        "JOIN clients c ON e.client_id = c.id "
        "LEFT JOIN event_lines el ON el.event_id = e.id "
        "WHERE e.event_date BETWEEN ? AND ? AND e.status != 'annulé' "
        "GROUP BY e.id, e.title, e.event_date, e.event_type, e.status, e.total_amount, c.name "
        "ORDER BY e.event_date DESC",
        (start_date, end_date)
    ).fetchall()
    
    # Summary stats
    total_revenue = db.execute(
        "SELECT COALESCE(SUM(p.amount),0) as s FROM payments p "
        "WHERE p.payment_date BETWEEN ? AND ? AND p.is_refunded=0",
        (start_date, end_date)
    ).fetchone()['s']
    
    total_outstanding = db.execute(
        "SELECT COALESCE(SUM(e.total_amount - COALESCE(p.paid_total, 0)), 0) as s "
        "FROM events e "
        "LEFT JOIN (SELECT event_id, SUM(amount) as paid_total FROM payments WHERE is_refunded=0 GROUP BY event_id) p "
        "ON p.event_id = e.id "
        "WHERE e.event_date BETWEEN ? AND ? AND e.status NOT IN ('annulé', 'terminé')",
        (start_date, end_date)
    ).fetchone()['s']
    
    db.close()
    
    summary_stats = {
        'total_revenue': total_revenue,
        'total_outstanding': total_outstanding,
        'period_start': start_date,
        'period_end': end_date
    }
    
    export_date = datetime.now().strftime('%Y-%m-%d %H:%M')
    ods_content = export_financials_ods(
        [ event_financials], 
        summary_stats, 
        export_date
    )
    
    response = make_response(ods_content)
    response.headers['Content-Type'] = 'application/vnd.oasis.opendocument.spreadsheet'
    response.headers['Content-Disposition'] = f'attachment; filename=finances_{start_date}_{end_date}.ods'
    return response


@app.route('/export/expenses.ods')
def export_expenses():
    """Export expenses to ODS format."""
    db = get_db()
    
    start_date = request.args.get('start_date', (date.today() - timedelta(days=365)).isoformat())
    end_date = request.args.get('end_date', date.today().isoformat())
    category_filter = request.args.get('category', '')
    
    query = "SELECT ex.*, e.title as event_title FROM expenses ex LEFT JOIN events e ON ex.event_id = e.id WHERE 1=1"
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
    expenses = db.execute(query, params).fetchall()
    db.close()
    
    export_date = datetime.now().strftime('%Y-%m-%d %H:%M')
    ods_content = export_expenses_ods([ expenses], export_date)
    
    response = make_response(ods_content)
    response.headers['Content-Type'] = 'application/vnd.oasis.opendocument.spreadsheet'
    response.headers['Content-Disposition'] = f'attachment; filename=depenses_{start_date}_{end_date}.ods'
    return response


@app.route('/export/pl.ods')
def export_pl():
    """Export Profit & Loss report to ODS format."""
    db = get_db()
    
    start_date = request.args.get('start_date', (date.today() - timedelta(days=365)).isoformat())
    end_date = request.args.get('end_date', date.today().isoformat())
    
    # Build monthly data
    monthly_data = []
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    
    current = start.replace(day=1)
    while current <= end:
        month_start = current.strftime('%Y-%m-%d')
        if current.month == 12:
            month_end = current.replace(year=current.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = current.replace(month=current.month + 1, day=1) - timedelta(days=1)
        month_end_str = month_end.strftime('%Y-%m-%d')
        
        month_income = db.execute(
            "SELECT COALESCE(SUM(p.amount),0) as s FROM payments p "
            "WHERE p.payment_date >= ? AND p.payment_date <= ? AND p.is_refunded=0",
            (month_start, month_end_str)
        ).fetchone()['s']
        
        month_expenses = db.execute(
            "SELECT COALESCE(SUM(amount),0) as s FROM expenses "
            "WHERE expense_date >= ? AND expense_date <= ?",
            (month_start, month_end_str)
        ).fetchone()['s']
        
        monthly_data.append({
            'month': f"{MONTH_NAMES_FR[current.month]} {current.year}",
            'income': float(month_income),
            'expenses': float(month_expenses)
        })
        
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    
    monthly_data.reverse()
    
    db.close()
    
    export_date = datetime.now().strftime('%Y-%m-%d %H:%M')
    ods_content = export_pl_report_ods(monthly_data, export_date)
    
    response = make_response(ods_content)
    response.headers['Content-Type'] = 'application/vnd.oasis.opendocument.spreadsheet'
    response.headers['Content-Disposition'] = f'attachment; filename=rapport_pl_{start_date}_{end_date}.ods'
    return response


# ─── Init and Run ────────────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    ensure_default_data()
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
# Force redeploy Wed Mar 25 19:34:15 WAT 2026

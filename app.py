from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response
from models import get_db, init_db, get_setting, set_setting
from datetime import datetime, date, timedelta
from contract_generator import generate_contract_pdf
from receipt_generator import generate_receipt_html
import calendar
import json

app = Flask(__name__)
app.secret_key = 'samba-fete-secret-key-2024'

# ─── Helpers ────────────────────────────────────────────────────────
TIME_SLOTS = ['Après-midi', 'Soirée', 'Nuit']
EVENT_TYPES = ['Mariage', 'Fiançailles', 'Anniversaire', 'Conférence', 'Autre']
EVENT_STATUSES = ['confirmé', 'en attente', 'annulé', 'terminé']
PAYMENT_METHODS = ['espèces', 'chèque', 'virement', 'carte']
MONTH_NAMES_FR = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                  'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
MONTH_NAMES_SHORT = ['', 'Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Jun', 'Jul', 'Aoû', 'Sep', 'Oct', 'Nov', 'Déc']

def format_da(amount):
    try:
        return f"{float(amount):,.0f} DA".replace(",", " ")
    except (ValueError, TypeError):
        return "0 DA"

app.jinja_env.filters['format_da'] = format_da

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

    # Previous month for comparison
    if today.month == 1:
        prev_first = today.replace(year=today.year-1, month=12, day=1)
        prev_last = today.replace(year=today.year-1, month=12, day=31)
    else:
        prev_first = today.replace(month=today.month-1, day=1)
        if today.month - 1 == 12:
            prev_last = today.replace(year=today.year-1, month=12, day=31)
        else:
            prev_last = today.replace(month=today.month, day=1) - timedelta(days=1)

    # Revenue this month
    revenue_month = db.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM payments p JOIN events e ON p.event_id=e.id "
        "WHERE p.date BETWEEN ? AND ? AND e.status != 'annulé'",
        (first_day.isoformat(), last_day.isoformat())).fetchone()['s']

    # Revenue last month
    revenue_prev_month = db.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM payments p JOIN events e ON p.event_id=e.id "
        "WHERE p.date BETWEEN ? AND ? AND e.status != 'annulé'",
        (prev_first.isoformat(), prev_last.isoformat())).fetchone()['s']

    # Revenue change percentage
    if revenue_prev_month > 0:
        revenue_change = round(((revenue_month - revenue_prev_month) / revenue_prev_month) * 100, 1)
    elif revenue_month > 0:
        revenue_change = 100.0
    else:
        revenue_change = 0.0

    # Events this month
    events_this_month = db.execute(
        "SELECT COUNT(*) as c FROM events WHERE event_date BETWEEN ? AND ? AND status != 'annulé'",
        (first_day.isoformat(), last_day.isoformat())).fetchone()['c']

    # Pending events count
    pending_count = db.execute(
        "SELECT COUNT(*) as c FROM events WHERE status = 'en attente' AND event_date >= ?",
        (today.isoformat(),)).fetchone()['c']

    # Events next 7 days
    next_week = today + timedelta(days=7)
    next_week_events = db.execute(
        "SELECT COUNT(*) as c FROM events WHERE event_date BETWEEN ? AND ? AND status != 'annulé'",
        (today.isoformat(), next_week.isoformat())).fetchone()['c']

    # Upcoming 5 events
    upcoming = db.execute(
        "SELECT e.*, c.name as client_name, v.name as venue_name FROM events e "
        "JOIN clients c ON e.client_id=c.id JOIN venues v ON e.venue_id=v.id "
        "WHERE e.event_date >= ? AND e.status != 'annulé' ORDER BY e.event_date ASC LIMIT 5",
        (today.isoformat(),)).fetchall()

    # Recent payments (5)
    recent_payments = db.execute(
        "SELECT p.*, e.title, c.name as client_name FROM payments p "
        "JOIN events e ON p.event_id=e.id JOIN clients c ON e.client_id=c.id "
        "ORDER BY p.date DESC LIMIT 5").fetchall()

    # ─── Chart Data: Monthly Revenue (last 6 months) ───
    monthly_revenue_labels = []
    monthly_revenue_data = []
    for i in range(5, -1, -1):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        first = f"{y}-{m:02d}-01"
        if m == 12:
            last = f"{y+1}-01-01"
        else:
            last = f"{y}-{m+1:02d}-01"
        rev = db.execute(
            "SELECT COALESCE(SUM(amount),0) as s FROM payments p JOIN events e ON p.event_id=e.id "
            "WHERE p.date >= ? AND p.date < ? AND e.status != 'annulé'",
            (first, last)).fetchone()['s']
        monthly_revenue_labels.append(MONTH_NAMES_SHORT[m])
        monthly_revenue_data.append(float(rev))

    # ─── Chart Data: Event Types breakdown ───
    event_type_labels = []
    event_type_data = []
    for et in EVENT_TYPES:
        count = db.execute(
            "SELECT COUNT(*) as c FROM events WHERE event_type=? AND status != 'annulé'",
            (et,)).fetchone()['c']
        if count > 0:
            event_type_labels.append(et)
            event_type_data.append(count)

    # ─── Events by status for mini chart ───
    status_counts = {}
    for st in EVENT_STATUSES:
        c = db.execute("SELECT COUNT(*) as c FROM events WHERE status=?", (st,)).fetchone()['c']
        status_counts[st] = c

    total_clients = db.execute("SELECT COUNT(*) as c FROM clients").fetchone()['c']
    total_events = db.execute("SELECT COUNT(*) as c FROM events WHERE status != 'annulé'").fetchone()['c']

    hall_name = get_setting('hall_name', 'Samba Fête')
    currency = get_setting('currency', 'DA')

    # Check if there are pending events for contract generation button
    has_pending = pending_count > 0

    db.close()
    return render_template('index.html',
                           events_this_month=events_this_month,
                           revenue_month=revenue_month,
                           revenue_change=revenue_change,
                           pending_count=pending_count,
                           next_week_events=next_week_events,
                           upcoming=upcoming,
                           total_clients=total_clients,
                           total_events=total_events,
                           recent_payments=recent_payments,
                           today=today,
                           hall_name=hall_name,
                           currency=currency,
                           month_name=MONTH_NAMES_FR[today.month],
                           monthly_revenue_labels=json.dumps(monthly_revenue_labels),
                           monthly_revenue_data=json.dumps(monthly_revenue_data),
                           event_type_labels=json.dumps(event_type_labels),
                           event_type_data=json.dumps(event_type_data),
                           status_counts=status_counts,
                           has_pending=has_pending)

# ─── Calendar ────────────────────────────────────────────────────────
@app.route('/calendrier')
def calendar_view():
    db = get_db()
    year = request.args.get('year', date.today().year, type=int)
    month = request.args.get('month', date.today().month, type=int)

    # Get booked dates for this month
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
        booked_dict[d].append(dict(b))

    # Build calendar grid
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)
    today_str = date.today().isoformat()

    venues = db.execute("SELECT * FROM venues WHERE is_active=1").fetchall()
    db.close()

    return render_template('calendar.html', year=year, month=month,
                           month_name=MONTH_NAMES_FR[month],
                           weeks=weeks, booked_dict=booked_dict,
                           today_str=today_str, venues=venues,
                           time_slots=TIME_SLOTS, venue_filter=venue_filter or '')

# ─── Events ──────────────────────────────────────────────────────────
# Default service definitions
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

        # Separate predefined services from custom lines
        predefined_names = [v['name'] for v in DEFAULT_SERVICES.values()] + ['Autre']
        for line in all_lines:
            if line['description'] in predefined_names:
                event_lines.append(dict(line))
            else:
                custom_lines.append(dict(line))

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
        status = data.get('status', 'confirmé')
        notes = data.get('notes', '').strip()
        total_amount = data.get('total_amount', 0, type=float)
        deposit_required = data.get('deposit_required', 20000, type=float)

        # Line items (additional custom lines)
        line_descs = request.form.getlist('line_desc[]')
        line_amounts = request.form.getlist('line_amount[]')
        line_costs = request.form.getlist('line_is_cost[]')

        # Services
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

        # Create or update client
        if client:
            db.execute("UPDATE clients SET name=?, phone=?, phone2=?, email=?, address=? WHERE id=?",
                       (client_name, client_phone, client_phone2, client_email, client_address, client['id']))
            client_id = client['id']
        else:
            cur = db.execute("INSERT INTO clients (name, phone, phone2, email, address) VALUES (?,?,?,?,?)",
                            (client_name, client_phone, client_phone2, client_email, client_address))
            client_id = cur.lastrowid

        # Create or update event
        if event:
            db.execute("UPDATE events SET title=?, client_id=?, venue_id=?, venue_id2=?, event_type=?, event_date=?, "
                       "time_slot=?, guests_men=?, guests_women=?, status=?, notes=?, "
                       "total_amount=?, deposit_required=? WHERE id=?",
                       (title, client_id, venue_id, venue_id2, event_type, event_date, time_slot,
                        guests_men, guests_women, status, notes, total_amount, deposit_required, event_id))
            # Remove old lines
            db.execute("DELETE FROM event_lines WHERE event_id=?", (event_id,))
        else:
            cur = db.execute("INSERT INTO events (title, client_id, venue_id, venue_id2, event_type, event_date, "
                            "time_slot, guests_men, guests_women, status, notes, total_amount, deposit_required) "
                            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (title, client_id, venue_id, venue_id2, event_type, event_date, time_slot,
                             guests_men, guests_women, status, notes, total_amount, deposit_required))
            event_id = cur.lastrowid

        # Insert service lines (predefined services)
        # Location de la salle (always added if price > 0)
        if price_location > 0:
            db.execute("INSERT INTO event_lines (event_id, description, amount, is_cost) VALUES (?,?,?,0)",
                      (event_id, 'Location de la salle', price_location))

        # Other services (only if checked and price > 0)
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

        # Insert custom line items
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
    payments = db.execute("SELECT * FROM payments WHERE event_id=? ORDER BY date DESC", (event_id,)).fetchall()
    total_paid = db.execute("SELECT COALESCE(SUM(amount),0) as s FROM payments WHERE event_id=?",
                           (event_id,)).fetchone()['s']
    deposit = db.execute("SELECT COALESCE(SUM(amount),0) as s FROM payments WHERE event_id=? AND payment_type='acompte'",
                        (event_id,)).fetchone()['s']

    db.close()
    return render_template('event_detail.html', event=event, event_lines=event_lines,
                           payments=payments, total_paid=total_paid, deposit=deposit)

@app.route('/evenement/<int:event_id>/paiement', methods=['POST'])
def add_payment(event_id):
    db = get_db()
    data = request.form
    amount = data.get('amount', 0, type=float)
    method = data.get('method', 'espèces')
    payment_type = data.get('payment_type', 'acompte')
    reference = data.get('reference', '').strip()

    if amount <= 0:
        flash("Montant invalide", "danger")
    else:
        db.execute("INSERT INTO payments (event_id, amount, method, payment_type, reference) VALUES (?,?,?,?,?)",
                  (event_id, amount, method, payment_type, reference))
        db.commit()
        flash("Paiement enregistré!", "success")

    db.close()
    return redirect(url_for('event_detail', event_id=event_id))

@app.route('/evenement/<int:event_id>/supprimer', methods=['POST'])
def delete_event(event_id):
    db = get_db()
    db.execute("DELETE FROM event_lines WHERE event_id=?", (event_id,))
    db.execute("DELETE FROM payments WHERE event_id=?", (event_id,))
    db.execute("DELETE FROM events WHERE id=?", (event_id,))
    db.commit()
    db.close()
    flash("Événement supprimé", "success")
    return redirect(url_for('index'))

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

# ─── Clients ─────────────────────────────────────────────────────────
@app.route('/clients')
def client_list():
    db = get_db()
    search = request.args.get('q', '').strip()

    query = ("SELECT c.*, "
             "(SELECT COUNT(*) FROM events WHERE client_id=c.id) as event_count, "
             "(SELECT COALESCE(SUM(p.amount),0) FROM payments p JOIN events e ON p.event_id=e.id WHERE e.client_id=c.id) as total_paid, "
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

    # Calculate totals
    total_owed = db.execute(
        "SELECT COALESCE(SUM(total_amount),0) as s FROM events WHERE client_id=?",
        (client_id,)).fetchone()['s']
    total_paid = db.execute(
        "SELECT COALESCE(SUM(p.amount),0) as s FROM payments p "
        "JOIN events e ON p.event_id=e.id WHERE e.client_id=?",
        (client_id,)).fetchone()['s']

    # Get payments per event
    event_payments = {}
    for ev in events:
        payments = db.execute(
            "SELECT * FROM payments WHERE event_id=? ORDER BY date DESC",
            (ev['id'],)).fetchall()
        event_paid = sum(p['amount'] for p in payments)
        event_payments[ev['id']] = {
            'payments': payments,
            'total_paid': event_paid,
            'remaining': ev['total_amount'] - event_paid
        }

    db.close()
    return render_template('client_detail.html', client=client, events=events,
                           total_owed=total_owed, total_paid=total_paid,
                           event_payments=event_payments)

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

    payments = db.execute("SELECT * FROM payments WHERE event_id=? ORDER BY date DESC", (event_id,)).fetchall()
    total_paid = db.execute("SELECT COALESCE(SUM(amount),0) as s FROM payments WHERE event_id=?",
                           (event_id,)).fetchone()['s']
    event_lines = db.execute("SELECT * FROM event_lines WHERE event_id=?", (event_id,)).fetchall()

    db.close()

    # Generate PDF
    pdf_bytes = generate_contract_pdf(
        dict(event),
        [dict(p) for p in payments],
        total_paid,
        [dict(l) for l in event_lines]
    )

    response = make_response(pdf_bytes)
    response.headers['Content-Type'] = 'application/pdf'
    safe_title = event['title'].replace(' ', '_')[:30]
    response.headers['Content-Disposition'] = f'inline; filename=contrat_{safe_title}_{event_id}.pdf'
    return response

# ─── Receipt (Reçu de Paiement) ─────────────────────────────────────
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

    # Calculate totals for the receipt
    total_paid_before = db.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM payments WHERE event_id=? AND date < ?",
        (event_id, payment['date'])).fetchone()['s']
    # Include current payment for "déjà payé"
    total_paid_after = total_paid_before + payment['amount']

    remaining = event['total_amount'] - total_paid_after

    # Receipt number
    receipt_no = f"{payment['date'][:4]}-{payment_id:04d}"

    db.close()

    html = generate_receipt_html(
        dict(event), dict(payment), total_paid_before, total_paid_after,
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
        # Update venue capacities
        for venue_id in request.form.getlist('venue_id'):
            cap_m = request.form.get(f'capacity_men_{venue_id}', 0, type=int)
            cap_w = request.form.get(f'capacity_women_{venue_id}', 0, type=int)
            db.execute("UPDATE venues SET capacity_men=?, capacity_women=? WHERE id=?",
                      (cap_m, cap_w, venue_id))

        # Global settings
        deposit_min = request.form.get('deposit_min', 20000, type=float)
        hall_name = request.form.get('hall_name', 'Samba Fête')
        currency = request.form.get('currency', 'DA')
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                   ('deposit_min', str(deposit_min)))
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                   ('hall_name', hall_name))
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                   ('currency', currency))

        # New venue
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

# ─── API endpoints for calendar ──────────────────────────────────────
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

    result = [dict(e) for e in events]
    db.close()
    return jsonify(result)

# ─── Init and Run ────────────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)

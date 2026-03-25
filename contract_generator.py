"""
Generate a beautiful print-ready contract PDF (French) for Samba Fête.
Uses WeasyPrint with HTML/CSS for elegant, modern design.
"""

from weasyprint import HTML
from io import BytesIO
from datetime import datetime

COMPANY_NAME = "Samba Fête"
COMPANY_ADDRESS = "102 ZAM, Nouvelle Ville, Constantine"
COMPANY_TEL = "0550 50 37 67"
COMPANY_RC = "034275305A"
COMPANY_NIF = "1635"

MONTHS_FR = {
    1: 'janvier', 2: 'février', 3: 'mars', 4: 'avril',
    5: 'mai', 6: 'juin', 7: 'juillet', 8: 'août',
    9: 'septembre', 10: 'octobre', 11: 'novembre', 12: 'décembre'
}

# Time slots for events
TIME_SLOTS = {
    'déjeuner': '10h00 — 18h00',
    'dejeuner': '10h00 — 18h00',
    'après-midi': '12h00 — 18h00',
    'apremidi': '12h00 — 18h00',
    'après midi': '12h00 — 18h00',
    'dîner': '12h00 — 00h00',
    'diner': '12h00 — 00h00',
    'nuit': '18h00 — 06h00',
    'nuit complète': '18h00 — 06h00',
}


def format_da(amount):
    try:
        return f"{float(amount):,.0f} DA".replace(",", " ")
    except (ValueError, TypeError):
        return "0 DA"


def format_date_fr(date_str):
    try:
        if isinstance(date_str, str):
            d = datetime.strptime(date_str[:10], '%Y-%m-%d')
        else:
            d = date_str
        return f"{d.day} {MONTHS_FR.get(d.month, '')} {d.year}"
    except Exception:
        return str(date_str)


def get_time_slot_display(slot_input):
    """Convert slot input to display format."""
    if not slot_input:
        return 'N/A'
    slot_lower = slot_input.lower().strip()
    for key, value in TIME_SLOTS.items():
        if key in slot_lower:
            return value
    return slot_input


def generate_contract_pdf(event, payments, total_paid, event_lines):
    """Generate a beautiful French contract PDF using WeasyPrint."""
    
    remaining = float(event.get('total_amount', 0)) - float(total_paid)
    contract_num = event.get('id', '000')
    if isinstance(contract_num, int):
        contract_num = f"{contract_num:04d}"
    
    time_display = get_time_slot_display(event.get('time_slot', ''))
    venue = event.get('venue_name', 'N/A')
    if event.get('venue2_name'):
        venue += f" + {event['venue2_name']}"
    
    total_guests = event.get('guests_men', 0) + event.get('guests_women', 0)
    
    # Build payment history rows
    payment_rows = ""
    for p in (payments or [])[:8]:
        payment_rows += f"""
        <tr>
            <td>{str(p.get('payment_date', ''))[:10]}</td>
            <td>{format_da(p.get('amount', 0))}</td>
            <td>{p.get('method', '')}</td>
            <td>{p.get('reference') or '—'}</td>
        </tr>"""
    
    # Build services rows
    services_rows = ""
    for line in (event_lines or []):
        services_rows += f"""
        <tr>
            <td>{line.get('description', '')}</td>
            <td>{format_da(line.get('amount', 0))}</td>
        </tr>"""
    
    if not services_rows:
        services_rows = """
        <tr>
            <td>Location de la salle</td>
            <td>{}</td>
        </tr>
        <tr>
            <td>Services inclus</td>
            <td>—</td>
        </tr>""".format(format_da(event.get('total_amount', 0)))
    
    # Phone info
    phone_info = f"Tél: {event.get('phone', 'N/A')}"
    if event.get('phone2'):
        phone_info += f" / {event['phone2']}"
    if event.get('email'):
        phone_info += f"<br>Email: {event['email']}"
    if event.get('address'):
        phone_info += f"<br>Adresse: {event['address']}"

    html_content = f"""
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<style>
@page {{
    size: A4;
    margin: 8mm 12mm 8mm 12mm;
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: 5.5pt;
    color: #1a1a1a;
    line-height: 1.1;
}}

.header {{
    text-align: center;
    padding-bottom: 2pt;
    border-bottom: 1pt solid #2d5a7b;
    margin-bottom: 1pt;
}}

.header h1 {{
    font-size: 14pt;
    font-weight: 400;
    color: #2d5a7b;
    letter-spacing: 2pt;
    margin-bottom: 0pt;
}}

.header .tagline {{
    font-size: 6.5pt;
    color: #555;
    letter-spacing: 1.5pt;
    text-transform: uppercase;
}}

.header .contact {{
    font-size: 6.5pt;
    color: #666;
    margin-top: 3pt;
}}

.info-bar {{
    display: flex;
    justify-content: space-around;
    background: #f5f5f5;
    padding: 2pt 6pt;
    border: 0.5pt solid #ccc;
    margin-bottom: 1pt;
}}

.info-bar .item {{ text-align: center; }}
.info-bar .label {{ font-size: 6pt; color: #666; text-transform: uppercase; }}
.info-bar .value {{ font-size: 8pt; font-weight: 600; color: #2d5a7b; }}

.parties {{
    display: flex;
    gap: 3pt;
    margin-bottom: 2pt;
}}

.party {{
    flex: 1;
    border: 0.5pt solid #999;
    padding: 2pt 4pt;
    border-left: 2pt solid #2d5a7b;
}}

.party.client {{ border-left-color: #5a8a6a; }}

.party .label {{ font-size: 6pt; color: #666; text-transform: uppercase; letter-spacing: 1pt; }}
.party .name {{ font-size: 8pt; font-weight: 600; color: #1a1a1a; margin: 2pt 0; }}
.party .details {{ font-size: 6.5pt; color: #444; line-height: 1.3; }}

.clause {{ margin-bottom: 1pt; }}

.clause-head {{
    display: flex;
    align-items: center;
    gap: 2pt;
    margin-bottom: 0.5pt;
}}

.clause-num {{
    background: #2d5a7b;
    color: white;
    padding: 1pt 6pt;
    border-radius: 3pt;
    font-size: 6.5pt;
    font-weight: 600;
}}

.clause-title {{
    font-size: 8pt;
    font-weight: 600;
    color: #1a1a1a;
}}

.clause p {{
    font-size: 6.5pt;
    color: #333;
    text-align: justify;
    line-height: 1.25;
}}

table {{
    width: 100%;
    border-collapse: collapse;
    margin: 2pt 0;
}}

th {{
    background: #e8e8e8;
    color: #1a1a1a;
    padding: 4pt 8pt;
    text-align: left;
    font-size: 6.5pt;
    text-transform: uppercase;
    font-weight: 600;
    border: 1pt solid #999;
}}

th:last-child {{ text-align: right; }}

td {{
    padding: 4pt 8pt;
    font-size: 6.5pt;
    color: #1a1a1a;
    border: 1pt solid #ccc;
    background: white;
}}

td:last-child {{ text-align: right; font-weight: 500; }}

.total-row td {{
    background: #f0f0f0;
    font-weight: 700;
    border-top: 2pt solid #2d5a7b;
}}

.payments {{
    display: flex;
    gap: 3pt;
    margin: 3pt 0;
}}

.pay-box {{
    flex: 1;
    border: 1pt solid #999;
    padding: 3pt;
    text-align: center;
    background: white;
}}

.pay-box.paid {{ border: 1pt solid #5a8a6a; background: #f5faf7; }}
.pay-box.due {{ border: 1pt solid #c97b5d; background: #fdf8f5; }}

.pay-box .pay-label {{ font-size: 6pt; color: #666; text-transform: uppercase; margin-bottom: 2pt; }}
.pay-box .pay-amount {{ font-size: 8pt; font-weight: 700; color: #1a1a1a; }}
.pay-box .pay-status {{ font-size: 6pt; margin-top: 1pt; }}
.pay-box.paid .pay-status {{ color: #5a8a6a; }}
.pay-box.due .pay-status {{ color: #c97b5d; }}

.obligations {{
    display: flex;
    gap: 5pt;
    margin: 3pt 0;
}}

.obligation {{
    flex: 1;
    border: 1pt solid #ccc;
    padding: 4pt 6pt;
}}

.obligation h4 {{
    font-size: 6.5pt;
    color: #2d5a7b;
    text-transform: uppercase;
    margin-bottom: 2pt;
    font-weight: 600;
}}

.obligation ul {{ list-style: none; }}
.obligation li {{
    font-size: 6.5pt;
    color: #333;
    padding: 1pt 0 1pt 10pt;
    position: relative;
}}
.obligation li::before {{
    content: "✓";
    position: absolute;
    left: 0;
    color: #2d5a7b;
    font-weight: bold;
}}

.signatures {{
    display: flex;
    justify-content: space-between;
    margin-top: 2pt;
    padding-top: 2pt;
    border-top: 0.5pt solid #999;
}}

.sig {{
    width: 45%;
    text-align: center;
}}

.sig .sig-label {{
    font-size: 5.5pt;
    color: #555;
    text-transform: uppercase;
    margin-bottom: 10pt;
}}

.sig .sig-name {{ font-size: 7pt; font-weight: 600; color: #1a1a1a; }}
.sig .sig-line {{ border-top: 0.5pt solid #333; width: 80%; margin: 3pt auto 2pt; }}
.sig .sig-detail {{ font-size: 5pt; color: #666; }}

.footer {{
    margin-top: 2pt;
    padding-top: 2pt;
    border-top: 0.5pt solid #ccc;
    text-align: center;
    font-size: 6pt;
    color: #888;
}}

.no-refund {{
    background: #fff8f5;
    border: 0.5pt solid #e5c9b8;
    padding: 2pt 4pt;
    margin: 1pt 0;
    font-size: 5.5pt;
    color: #8b4513;
}}
</style>
</head>
<body>

<div class="header">
    <h1>SAMBA FÊTE</h1>
    <div class="tagline">Location de Salle & Prestation de Services</div>
    <div class="contact">{COMPANY_ADDRESS} — Tél: {COMPANY_TEL} — RC: {COMPANY_RC} — NIF: {COMPANY_NIF}</div>
</div>

<div class="info-bar">
    <div class="item"><div class="label">Contrat N°</div><div class="value">SF-{contract_num}</div></div>
    <div class="item"><div class="label">Date</div><div class="value">{format_date_fr(datetime.now().date())}</div></div>
    <div class="item"><div class="label">Événement</div><div class="value">{format_date_fr(event.get('event_date', ''))}</div></div>
    <div class="item"><div class="label">Type</div><div class="value">{event.get('event_type', 'N/A')}</div></div>
</div>

<div class="parties">
    <div class="party">
        <div class="label">Le Prestataire</div>
        <div class="name">{COMPANY_NAME}</div>
        <div class="details">{COMPANY_ADDRESS}<br>Tél: {COMPANY_TEL}<br>RC: {COMPANY_RC} — NIF: {COMPANY_NIF}</div>
    </div>
    <div class="party client">
        <div class="label">Le Client</div>
        <div class="name">{event.get('client_name', 'N/A')}</div>
        <div class="details">{phone_info}</div>
    </div>
</div>

<div class="clause">
    <div class="clause-head"><span class="clause-num">01</span><span class="clause-title">Objet du Contrat</span></div>
    <p>Le présent contrat a pour objet la location de la salle <b>Samba Fête</b> et la fourniture de services liés à l'événement décrit ci-après. Le Client s'engage à respecter l'ensemble des termes et conditions stipulés dans le présent contrat. Toute prestation non mentionnée fera l'objet d'un avenant signé par les deux parties.</p>
</div>

<div class="clause">
    <div class="clause-head"><span class="clause-num">02</span><span class="clause-title">Description de l'Événement</span></div>
    <table>
        <tr><th style="width:22%">Type</th><td>{event.get('event_type', 'N/A')}</td><th style="width:15%">Date</th><td>{format_date_fr(event.get('event_date', ''))}</td></tr>
        <tr><th>Intitulé</th><td colspan="3">{event.get('title', 'N/A')}</td></tr>
        <tr><th>Créneau horaire</th><td>{time_display}</td><th>Salles</th><td>{venue}</td></tr>
        <tr><th>Invités (Hommes)</th><td>{event.get('guests_men', 0)}</td><th>Invités (Femmes)</th><td>{event.get('guests_women', 0)}</td></tr>
        <tr><th><strong>Total</strong></th><td colspan="3"><strong>{total_guests} personnes</strong></td></tr>
    </table>
</div>

<div class="clause">
    <div class="clause-head"><span class="clause-num">03</span><span class="clause-title">Prestations & Tarifs</span></div>
    <table>
        <thead><tr><th style="width:65%">Prestation</th><th style="width:35%">Montant</th></tr></thead>
        <tbody>
            {services_rows}
            <tr class="total-row"><td><strong>MONTANT TOTAL</strong></td><td><strong>{format_da(event.get('total_amount', 0))}</strong></td></tr>
        </tbody>
    </table>
</div>

<div class="clause">
    <div class="clause-head"><span class="clause-num">04</span><span class="clause-title">Conditions Financières</span></div>
    <div class="payments">
        <div class="pay-box"><div class="pay-label">Total</div><div class="pay-amount">{format_da(event.get('total_amount', 0)).replace(' DA', '')}</div><div class="pay-status">DA</div></div>
        <div class="pay-box paid"><div class="pay-label">Acompte versé</div><div class="pay-amount">{format_da(total_paid).replace(' DA', '')}</div><div class="pay-status">✓ Payé</div></div>
        <div class="pay-box {"due" if remaining > 0 else ""}"><div class="pay-label">Reste à payer</div><div class="pay-amount">{format_da(remaining).replace(' DA', '')}</div><div class="pay-status">{"Avant l'événement" if remaining > 0 else "✓ Soldé"}</div></div>
        <div class="pay-box"><div class="pay-label">Caution</div><div class="pay-amount">{format_da(event.get('deposit_required', 0)).replace(' DA', '')}</div><div class="pay-status">À restituer</div></div>
    </div>
</div>

<div class="clause">
    <div class="clause-head"><span class="clause-num">05</span><span class="clause-title">Caution & Restitution</span></div>
    <p>Le Client verse une caution de <b>{format_da(event.get('deposit_required', 0))}</b> à la signature. Cette caution sera restituée sous <b>48 heures</b> après l'événement, sous réserve de l'état des locaux. En cas de dégradation, le Prestataire se réserve le droit de retenir tout ou partie de la caution.</p>
</div>

<div class="clause">
    <div class="clause-head"><span class="clause-num">06</span><span class="clause-title">Obligations du Client</span></div>
    <div class="obligations">
        <div class="obligation">
            <h4>Responsabilités</h4>
            <ul>
                <li>Respecter le règlement intérieur</li>
                <li>Assurer la propreté des locaux</li>
                <li>Ne pas dépasser la capacité d'accueil</li>
                <li>Signaler toute anomalie avant le début</li>
            </ul>
        </div>
        <div class="obligation">
            <h4>Interdictions</h4>
            <ul>
                <li>Aucune substance illicite</li>
                <li>Comportements dangereux</li>
                <li>Accès réservé aux invités</li>
                <li>Non-respect = résiliation immédiate</li>
            </ul>
        </div>
    </div>
</div>

<div class="clause">
    <div class="clause-head"><span class="clause-num">07</span><span class="clause-title">Obligations du Prestataire</span></div>
    <p>Fournir la salle en bon état, nettoyage avant et après, tous les équipements mentionnés, garantir la sécurité des personnes et des biens, informer de tout changement affectant l'événement.</p>
</div>

<div class="no-refund">
    <strong>⚠ ARTICLE 8 — ANNULATION & REMBOURSEMENT</strong><br>
    En aucun cas, le Prestataire ne procédera au remboursement des sommes versées, quelle que soit la raison de l'annulation. L'acompte et toutes les sommes perçues sont définitivement acquis au Prestataire. Le Client peut modifier la date de l'événement sous réserve de disponibilité, sans frais supplémentaires, pourvu que la demande soit faite au moins 15 jours avant la date initiale.
</div>

<div class="signatures">
    <div class="sig">
        <div class="sig-label">Le Prestataire</div>
        <div class="sig-name">{COMPANY_NAME}</div>
        <div class="sig-line"></div>
        <div class="sig-detail">Cachet de l'entreprise</div>
    </div>
    <div class="sig">
        <div class="sig-label">Le Client</div>
        <div class="sig-name">{event.get('client_name', '')}</div>
        <div class="sig-line"></div>
        <div class="sig-detail">« Lu et approuvé »</div>
    </div>
</div>

<div class="footer">
    Fait en deux (2) exemplaires, Constantine, le {format_date_fr(datetime.now().date())} — Droit algérien — Tribunaux de Constantine
</div>

</body>
</html>
"""
    
    # Generate PDF
    pdf_bytes = HTML(string=html_content).write_pdf()
    return pdf_bytes


def generate_contract_to_file(event, payments, total_paid, event_lines, filepath):
    """Generate contract and save to file."""
    pdf_bytes = generate_contract_pdf(event, payments, total_paid, event_lines)
    with open(filepath, 'wb') as f:
        f.write(pdf_bytes)
    return filepath

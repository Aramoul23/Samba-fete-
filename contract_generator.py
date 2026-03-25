"""
Beautiful Wedding Contract PDF Generator for Samba Fête.
Elegant, print-optimized design with wedding hall branding.
"""

from weasyprint import HTML
from datetime import datetime

COMPANY_NAME = "SAMBA FÊTE"
COMPANY_TAGLINE = "Salle de Réception & Organisation d'Événements"
COMPANY_ADDRESS = "102 ZAM, Nouvelle Ville, Constantine"
COMPANY_TEL = "0550 50 37 67"
COMPANY_RC = "034275305A"
COMPANY_NIF = "1635"

MONTHS_FR = {
    1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
    5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
    9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'
}

TIME_SLOTS = {
    'déjeuner': '10h00 - 18h00',
    'dejeuner': '10h00 - 18h00',
    'après-midi': '12h00 - 18h00',
    'dîner': '12h00 - 00h00',
    'diner': '12h00 - 00h00',
    'nuit': '18h00 - 06h00',
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
    if not slot_input:
        return 'N/A'
    slot_lower = slot_input.lower().strip()
    for key, value in TIME_SLOTS.items():
        if key in slot_lower:
            value_display = value.replace(' - ', 'h – ').replace('h00', 'h')
            return value
    return slot_input

def generate_contract_pdf(event, payments, total_paid, event_lines):
    remaining = float(event.get('total_amount', 0)) - float(total_paid)
    contract_num = event.get('id', '000')
    if isinstance(contract_num, int):
        contract_num = f"{contract_num:04d}"
    
    time_display = get_time_slot_display(event.get('time_slot', ''))
    venue = event.get('venue_name', 'N/A')
    if event.get('venue2_name'):
        venue += f" + {event['venue2_name']}"
    
    total_guests = event.get('guests_men', 0) + event.get('guests_women', 0)
    
    services_rows = ""
    for line in (event_lines or []):
        services_rows += f"""
        <tr>
            <td>{line.get('description', '')}</td>
            <td class="amount">{format_da(line.get('amount', 0))}</td>
        </tr>"""
    
    if not services_rows:
        services_rows = f"""
        <tr>
            <td>Location de la salle</td>
            <td class="amount">{format_da(event.get('total_amount', 0))}</td>
        </tr>"""
    
    phone_info = f"{event.get('phone', 'N/A')}"
    if event.get('phone2'):
        phone_info += f" / {event['phone2']}"
    
    event_type = event.get('event_type', 'Événement')
    event_type_icon = {
        'Mariage': '💍',
        'Fiançailles': '💎',
        'Anniversaire': '🎂',
        'Conférence': '🏢',
    }.get(event_type, '✨')

    html_content = f"""
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<style>
@page {{ size: A4; margin: 0; }}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'Georgia', 'Times New Roman', serif; font-size: 9pt; color: #1a1a1a; line-height: 1.2; }}
.header {{ background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%); padding: 20px 25px 15px; text-align: center; position: relative; }}
.header::after {{ content: ''; position: absolute; bottom: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, #c9a227 0%, #e8d5a3 50%, #c9a227 100%); }}
.header-decoration {{ color: #c9a227; font-size: 24pt; margin-bottom: 5px; letter-spacing: 8px; }}
.header h1 {{ font-family: 'Georgia', serif; font-size: 22pt; font-weight: normal; color: #c9a227; letter-spacing: 6px; margin-bottom: 3px; text-transform: uppercase; }}
.header .tagline {{ font-size: 8pt; color: #a0a0a0; letter-spacing: 2px; text-transform: uppercase; }}
.header .contact {{ font-size: 7pt; color: #888; margin-top: 8px; letter-spacing: 1px; }}
.info-bar {{ background: #faf8f5; border-bottom: 1px solid #e8e0d5; padding: 8px 25px; display: flex; justify-content: space-between; align-items: center; }}
.info-bar .contract-num {{ font-size: 11pt; font-weight: bold; color: #1a1a1a; }}
.info-bar .contract-num span {{ color: #c9a227; }}
.info-bar .date {{ font-size: 8pt; color: #666; }}
.parties {{ display: flex; padding: 15px 25px; gap: 15px; background: white; }}
.party {{ flex: 1; padding: 10px 12px; border-radius: 4px; border: 1px solid #e8e0d5; }}
.party.prestataire {{ background: linear-gradient(135deg, #fdfcfa 0%, #f8f4ed 100%); border-left: 3px solid #c9a227; }}
.party.client {{ background: linear-gradient(135deg, #fdfcfa 0%, #f5eef0 100%); border-left: 3px solid #d4889a; }}
.party-label {{ font-size: 7pt; text-transform: uppercase; letter-spacing: 1.5px; color: #888; margin-bottom: 4px; }}
.party-name {{ font-size: 11pt; font-weight: bold; color: #1a1a1a; margin-bottom: 3px; }}
.party-detail {{ font-size: 7.5pt; color: #555; line-height: 1.4; }}
.event-section {{ padding: 12px 25px; background: #faf8f5; }}
.section-title {{ font-size: 9pt; font-weight: bold; color: #c9a227; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }}
.section-title::after {{ content: ''; flex: 1; height: 1px; background: linear-gradient(90deg, #e8e0d5, transparent); }}
.event-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }}
.event-item {{ background: white; padding: 8px 10px; border-radius: 4px; border: 1px solid #e8e0d5; }}
.event-item-label {{ font-size: 6.5pt; text-transform: uppercase; color: #888; letter-spacing: 0.5px; }}
.event-item-value {{ font-size: 9pt; font-weight: bold; color: #1a1a1a; margin-top: 2px; }}
.event-item.highlight {{ background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%); border-color: #c9a227; }}
.event-item.highlight .event-item-label {{ color: #c9a227; }}
.event-item.highlight .event-item-value {{ color: white; font-size: 12pt; }}
.services-section {{ padding: 12px 25px; background: white; }}
table {{ width: 100%; border-collapse: collapse; }}
th {{ background: #1a1a1a; color: #c9a227; padding: 6px 10px; text-align: left; font-size: 7.5pt; text-transform: uppercase; letter-spacing: 0.5px; font-weight: normal; }}
th:last-child {{ text-align: right; }}
td {{ padding: 5px 10px; font-size: 8pt; color: #333; border-bottom: 1px solid #f0ebe5; }}
td.amount {{ text-align: right; font-weight: 500; }}
tr.total-row td {{ background: linear-gradient(90deg, #fdfcfa 0%, #f8f4ed 100%); border-top: 2px solid #c9a227; font-weight: bold; font-size: 9pt; padding: 8px 10px; }}
.financial-section {{ padding: 12px 25px; background: #faf8f5; }}
.financial-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }}
.financial-box {{ background: white; padding: 10px; border-radius: 4px; text-align: center; border: 1px solid #e8e0d5; }}
.financial-box.paid {{ background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%); border-color: #86efac; }}
.financial-box.due {{ background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%); border-color: #fca5a5; }}
.financial-box.total {{ background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%); border-color: #c9a227; }}
.fin-label {{ font-size: 6.5pt; text-transform: uppercase; letter-spacing: 0.5px; color: #888; margin-bottom: 3px; }}
.fin-value {{ font-size: 12pt; font-weight: bold; color: #1a1a1a; }}
.financial-box.paid .fin-label, .financial-box.paid .fin-value {{ color: #166534; }}
.financial-box.due .fin-label, .financial-box.due .fin-value {{ color: #991b1b; }}
.financial-box.total .fin-label {{ color: #c9a227; }}
.financial-box.total .fin-value {{ color: white; font-size: 13pt; }}
.terms-section {{ padding: 10px 25px; background: white; }}
.terms-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
.term-box {{ padding: 8px 10px; border-radius: 4px; font-size: 7pt; line-height: 1.4; }}
.term-box.obligations {{ background: #f8fafc; border: 1px solid #e2e8f0; }}
.term-box.prohibitions {{ background: #fef2f2; border: 1px solid #fecaca; }}
.term-box h4 {{ font-size: 7.5pt; font-weight: bold; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px; }}
.term-box.obligations h4 {{ color: #1e40af; }}
.term-box.prohibitions h4 {{ color: #991b1b; }}
.term-box ul {{ list-style: none; padding-left: 0; }}
.term-box li {{ padding: 2px 0; padding-left: 12px; position: relative; }}
.term-box.obligations li::before {{ content: '✓'; position: absolute; left: 0; color: #22c55e; font-weight: bold; }}
.term-box.prohibitions li::before {{ content: '✗'; position: absolute; left: 0; color: #ef4444; font-weight: bold; }}
.cancel-box {{ margin: 0 25px 12px; padding: 10px 12px; background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); border: 1px solid #f59e0b; border-radius: 4px; font-size: 7.5pt; line-height: 1.4; }}
.cancel-box strong {{ color: #92400e; display: block; margin-bottom: 3px; text-transform: uppercase; letter-spacing: 0.5px; font-size: 7pt; }}
.signatures {{ display: flex; justify-content: space-between; padding: 15px 25px; margin: 0 25px; background: #faf8f5; border: 1px solid #e8e0d5; border-radius: 4px; }}
.sig-block {{ width: 42%; text-align: center; }}
.sig-line {{ border-top: 1px solid #333; margin-bottom: 5px; height: 35px; }}
.sig-label {{ font-size: 7pt; color: #666; text-transform: uppercase; letter-spacing: 1px; }}
.sig-name {{ font-size: 8.5pt; font-weight: bold; color: #1a1a1a; margin-top: 3px; }}
.footer {{ background: #1a1a1a; padding: 12px 25px; text-align: center; margin-top: 15px; }}
.footer-text {{ font-size: 7pt; color: #888; letter-spacing: 0.5px; }}
.footer-brand {{ font-size: 8pt; color: #c9a227; letter-spacing: 2px; margin-bottom: 3px; }}
</style>
</head>
<body>
<div class="header">
    <div class="header-decoration">✦ ✦ ✦</div>
    <h1>SAMBA FÊTE</h1>
    <div class="tagline">{COMPANY_TAGLINE}</div>
    <div class="contact">{COMPANY_ADDRESS} | Tél: {COMPANY_TEL} | RC: {COMPANY_RC} | NIF: {COMPANY_NIF}</div>
</div>
<div class="info-bar">
    <div class="contract-num">Contrat N° <span>SF-{contract_num}</span></div>
    <div class="date">Fait à Constantine, le {format_date_fr(datetime.now().date())}</div>
</div>
<div class="parties">
    <div class="party prestataire">
        <div class="party-label">Le Prestataire</div>
        <div class="party-name">{COMPANY_NAME}</div>
        <div class="party-detail">{COMPANY_ADDRESS}<br>Tél: {COMPANY_TEL}<br>RC: {COMPANY_RC} | NIF: {COMPANY_NIF}</div>
    </div>
    <div class="party client">
        <div class="party-label">Le Client</div>
        <div class="party-name">{event.get('client_name', 'N/A')}</div>
        <div class="party-detail">Tél: {phone_info}<br>{f"Email: {event.get('email', '')}" if event.get('email') else ''}</div>
    </div>
</div>
<div class="event-section">
    <div class="section-title">Détails de l'Événement</div>
    <div class="event-grid">
        <div class="event-item"><div class="event-item-label">Type</div><div class="event-item-value">{event_type} {event_type_icon}</div></div>
        <div class="event-item"><div class="event-item-label">Date</div><div class="event-item-value">{format_date_fr(event.get('event_date', ''))}</div></div>
        <div class="event-item"><div class="event-item-label">Horaire</div><div class="event-item-value">{time_display}</div></div>
        <div class="event-item"><div class="event-item-label">Salle(s)</div><div class="event-item-value">{venue}</div></div>
        <div class="event-item"><div class="event-item-label">Invités (Hommes)</div><div class="event-item-value">{event.get('guests_men', 0)}</div></div>
        <div class="event-item"><div class="event-item-label">Invités (Femmes)</div><div class="event-item-value">{event.get('guests_women', 0)}</div></div>
        <div class="event-item"><div class="event-item-label">Intitulé</div><div class="event-item-value" style="font-size:8pt;">{event.get('title', 'N/A')}</div></div>
        <div class="event-item highlight"><div class="event-item-label">Total Invités</div><div class="event-item-value">{total_guests} personnes</div></div>
    </div>
</div>
<div class="services-section">
    <div class="section-title">Prestations & Tarifs</div>
    <table>
        <thead><tr><th style="width:70%">Description</th><th style="width:30%">Montant</th></tr></thead>
        <tbody>
            {services_rows}
            <tr class="total-row"><td><strong>MONTANT TOTAL</strong></td><td class="amount"><strong>{format_da(event.get('total_amount', 0))}</strong></td></tr>
        </tbody>
    </table>
</div>
<div class="financial-section">
    <div class="section-title">Conditions Financières</div>
    <div class="financial-grid">
        <div class="financial-box total"><div class="fin-label">Total</div><div class="fin-value">{format_da(event.get('total_amount', 0))}</div></div>
        <div class="financial-box paid"><div class="fin-label">Acompte Payé</div><div class="fin-value">{format_da(total_paid)}</div></div>
        <div class="financial-box {'due' if remaining > 0 else 'paid'}"><div class="fin-label">Reste à Payer</div><div class="fin-value">{format_da(remaining)}</div></div>
        <div class="financial-box"><div class="fin-label">Caution</div><div class="fin-value">{format_da(event.get('deposit_required', 0))}</div></div>
    </div>
</div>
<div class="terms-section">
    <div class="terms-grid">
        <div class="term-box obligations">
            <h4>Obligations du Client</h4>
            <ul><li>Respecter le règlement intérieur</li><li>Assurer la propreté des locaux</li><li>Ne pas dépasser la capacité</li><li>Signaler les anomalies avant</li></ul>
        </div>
        <div class="term-box prohibitions">
            <h4>Interdictions</h4>
            <ul><li>Substances illicites interdites</li><li>Comportements dangereux</li><li>Accès réservé aux invités</li><li>Non-respect = résiliation</li></ul>
        </div>
    </div>
</div>
<div class="cancel-box">
    <strong>Politique d'Annulation</strong>
    L'acompte versé est non remboursable en cas d'annulation. Toute modification de date doit être effectuée au moins 15 jours avant l'événement, sous réserve de disponibilité.
</div>
<div class="signatures">
    <div class="sig-block"><div class="sig-line"></div><div class="sig-label">Le Prestataire</div><div class="sig-name">{COMPANY_NAME}</div></div>
    <div class="sig-block"><div class="sig-line"></div><div class="sig-label">Le Client</div><div class="sig-name">{event.get('client_name', '')}</div></div>
</div>
<div class="footer">
    <div class="footer-brand">✦ SAMBA FÊTE ✦</div>
    <div class="footer-text">Fait en deux exemplaires, Constantine - Droit algérien applicable - Tribunaux de Constantine</div>
</div>
</body>
</html>"""
    
    pdf_bytes = HTML(string=html_content).write_pdf()
    return pdf_bytes

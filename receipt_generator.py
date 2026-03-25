"""
Beautiful Payment Receipt PDF Generator for Samba Fête.
Elegant, print-optimized design with wedding hall branding.
"""

MONTH_NAMES_FR = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
    'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']

COMPANY_NAME = "SAMBA FÊTE"
COMPANY_TAGLINE = "Salle de Réception"
COMPANY_ADDRESS = "102 ZAM, Nouvelle Ville, Constantine"
COMPANY_TEL = "0550 50 37 67"

def format_da(amount):
    try:
        return f"{float(amount):,.0f} DA".replace(",", " ")
    except (ValueError, TypeError):
        return "0 DA"

def format_date_fr(date_str):
    try:
        date_str = str(date_str)
        d = date_str[:10]
        year, month, day = d.split('-')
        return f"{int(day)} {MONTH_NAMES_FR[int(month)]} {year}"
    except Exception:
        return str(date_str)

METHOD_NAMES = {
    'espèces': 'Espèces',
    'chèque': 'Chèque',
    'virement': 'Virement',
    'carte': 'Carte bancaire',
}

def generate_receipt_html(event, payment, total_paid_before, total_paid_after, remaining, receipt_no):
    method_name = METHOD_NAMES.get(payment.get('method', ''), payment.get('method', ''))
    
    payment_type = payment.get('payment_type', 'acompte').lower()
    payment_type_display = {'acompte': 'Acompte', 'solde': 'Solde', 'avance': 'Avance'}.get(payment_type, payment_type.capitalize())
    
    is_paid_off = remaining <= 0

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<style>
@page {{ size: A5; margin: 0; }}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'Georgia', 'Times New Roman', serif; background: #f5f3ef; color: #2c3e50; }}
.receipt {{ width: 148mm; min-height: 210mm; background: white; margin: 0 auto; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
.header {{ background: linear-gradient(135deg, #1e3a5f 0%, #2c3e50 100%); padding: 15px 15px 12px; text-align: center; position: relative; }}
.header::after {{ content: ''; position: absolute; bottom: 0; left: 0; right: 0; height: 2px; background: linear-gradient(90deg, #c9a227 0%, #e8d5a3 50%, #c9a227 100%); }}
.header-decoration {{ color: #c9a227; font-size: 12pt; letter-spacing: 6px; margin-bottom: 3px; }}
.header h1 {{ font-family: 'Georgia', serif; font-size: 16pt; font-weight: normal; color: #c9a227; letter-spacing: 4px; margin-bottom: 2px; text-transform: uppercase; }}
.header .tagline {{ font-size: 7pt; color: #888; letter-spacing: 1px; text-transform: uppercase; }}
.title-section {{ background: #f8f6f3; padding: 12px; text-align: center; border-bottom: 1px solid #e8e0d5; }}
.title-section h2 {{ font-size: 12pt; color: #2c3e50; font-weight: normal; letter-spacing: 2px; text-transform: uppercase; }}
.receipt-number {{ font-size: 10pt; color: #c9a227; font-weight: bold; margin-top: 3px; letter-spacing: 1px; }}
.event-section {{ padding: 10px 15px; border-bottom: 1px solid #e8e0d5; }}
.section-label {{ font-size: 7pt; text-transform: uppercase; letter-spacing: 1px; color: #888; margin-bottom: 6px; }}
.info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
.info-item {{ font-size: 8pt; }}
.info-item .label {{ color: #666; font-size: 6.5pt; text-transform: uppercase; }}
.info-item .value {{ font-weight: bold; color: #2c3e50; margin-top: 1px; }}
.center-amount {{ text-align: center; padding: 20px 15px; }}
.paid-amount-box {{ display: inline-block; background: linear-gradient(135deg, #166534 0%, #15803d 100%); color: white; padding: 12px 25px; border-radius: 6px; text-align: center; }}
.paid-amount-box .label {{ font-size: 8pt; opacity: 0.9; text-transform: uppercase; letter-spacing: 1px; }}
.paid-amount-box .value {{ font-size: 20pt; font-weight: bold; margin-top: 3px; }}
.paid-stamp {{ display: inline-block; background: #166534; color: white; padding: 3px 10px; border-radius: 3px; font-size: 7pt; text-transform: uppercase; letter-spacing: 1px; margin-top: 5px; }}
.amount-section {{ padding: 12px 15px; background: #f8f6f3; }}
.amount-details {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
.amount-box {{ background: white; padding: 8px; border-radius: 4px; text-align: center; border: 1px solid #e8e0d5; }}
.amount-box .label {{ font-size: 6pt; text-transform: uppercase; color: #888; margin-bottom: 2px; }}
.amount-box .value {{ font-size: 10pt; font-weight: bold; color: #2c3e50; }}
.amount-box.paid .value {{ color: #166534; }}
.amount-box.due .value {{ color: #991b1b; }}
.amount-box.total .value {{ font-size: 11pt; }}
.payment-section {{ padding: 10px 15px; border-top: 1px solid #e8e0d5; }}
.payment-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }}
.payment-item {{ font-size: 8pt; }}
.payment-item .label {{ color: #666; font-size: 6.5pt; text-transform: uppercase; }}
.payment-item .value {{ font-weight: bold; color: #2c3e50; margin-top: 1px; }}
.signatures {{ display: flex; justify-content: space-around; padding: 15px; margin: 10px 15px; background: #f8f6f3; border: 1px solid #e8e0d5; border-radius: 4px; }}
.sig-block {{ text-align: center; width: 40%; }}
.sig-line {{ border-top: 1px solid #333; margin-bottom: 4px; height: 30px; }}
.sig-label {{ font-size: 6.5pt; color: #666; text-transform: uppercase; letter-spacing: 0.5px; }}
.footer {{ background: #2c3e50; padding: 10px 15px; text-align: center; }}
.footer-brand {{ font-size: 8pt; color: #c9a227; letter-spacing: 2px; margin-bottom: 2px; }}
.footer-text {{ font-size: 6pt; color: #888; }}
@media print {{ body {{ background: white; padding: 0; }} .receipt {{ box-shadow: none; width: 100%; }} }}
</style>
</head>
<body>
<div class="receipt">
    <div class="header">
        <div class="header-decoration">✦ ✦</div>
        <h1>SAMBA FÊTE</h1>
        <div class="tagline">{COMPANY_TAGLINE}</div>
    </div>
    <div class="title-section">
        <h2>Reçu de Paiement</h2>
        <div class="receipt-number">N° {receipt_no}</div>
    </div>
    <div class="event-section">
        <div class="section-label">Détails de l'Événement</div>
        <div class="info-grid">
            <div class="info-item"><div class="label">Client</div><div class="value">{event.get('client_name', 'N/A')}</div></div>
            <div class="info-item"><div class="label">Type</div><div class="value">{event.get('event_type', 'N/A')}</div></div>
            <div class="info-item"><div class="label">Événement</div><div class="value">{event.get('title', 'N/A')}</div></div>
            <div class="info-item"><div class="label">Date</div><div class="value">{format_date_fr(event.get('event_date', ''))}</div></div>
        </div>
    </div>
    <div class="center-amount">
        <div class="paid-amount-box">
            <div class="label">Montant Reçu</div>
            <div class="value">{format_da(payment.get('amount', 0))}</div>
            <div class="paid-stamp">✓ Payé</div>
        </div>
    </div>
    <div class="amount-section">
        <div class="section-label">Récapitulatif Financier</div>
        <div class="amount-details">
            <div class="amount-box total"><div class="label">Montant Total</div><div class="value">{format_da(event.get('total_amount', 0))}</div></div>
            <div class="amount-box paid"><div class="label">Acompte Versé</div><div class="value">{format_da(total_paid_after)}</div></div>
            <div class="amount-box"><div class="label">Payé Avant</div><div class="value">{format_da(total_paid_before)}</div></div>
            <div class="amount-box {'due' if remaining > 0 else 'paid'}"><div class="label">Reste à Payer</div><div class="value">{format_da(max(remaining, 0))}</div></div>
        </div>
    </div>
    <div class="payment-section">
        <div class="section-label">Détails du Paiement</div>
        <div class="payment-grid">
            <div class="payment-item"><div class="label">Date de Paiement</div><div class="value">{format_date_fr(str(payment.get('payment_date', ''))[:10])}</div></div>
            <div class="payment-item"><div class="label">Mode de Paiement</div><div class="value">{method_name}</div></div>
            <div class="payment-item"><div class="label">Type de Paiement</div><div class="value">{payment_type_display}</div></div>
            {"<div class='payment-item'><div class='label'>Référence</div><div class='value'>" + str(payment.get('reference', '')) + "</div></div>" if payment.get('reference') else ''}
        </div>
    </div>
    <div class="signatures">
        <div class="sig-block"><div class="sig-line"></div><div class="sig-label">Signature Client</div></div>
        <div class="sig-block"><div class="sig-line"></div><div class="sig-label">Signature Admin</div></div>
    </div>
    <div class="footer">
        <div class="footer-brand">✦ SAMBA FÊTE ✦</div>
        <div class="footer-text">{COMPANY_ADDRESS} | Tél: {COMPANY_TEL}</div>
    </div>
</div>
</body>
</html>"""

    return html

def generate_receipt_pdf(event, payment, total_paid_before, total_paid_after, remaining, receipt_no):
    from weasyprint import HTML
    html_content = generate_receipt_html(event, payment, total_paid_before, total_paid_after, remaining, receipt_no)
    return HTML(string=html_content).write_pdf()

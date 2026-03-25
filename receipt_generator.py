"""Receipt generator for Samba Fête - generates printable HTML receipts."""

MONTH_NAMES_FR = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                  'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']

def format_da(amount):
    try:
        return f"{float(amount):,.0f} DA".replace(",", " ")
    except (ValueError, TypeError):
        return "0 DA"

def format_date_fr(date_str):
    """Convert YYYY-MM-DD to French date string."""
    try:
        d = date_str[:10]
        year, month, day = d.split('-')
        return f"{int(day)} {MONTH_NAMES_FR[int(month)]} {year}"
    except Exception:
        return date_str

METHOD_NAMES = {
    'espèces': 'Espèces',
    'chèque': 'Chèque',
    'virement': 'Virement',
    'carte': 'Carte',
}

def generate_receipt_html(event, payment, total_paid_before, total_paid_after,
                          remaining, receipt_no):
    method_name = METHOD_NAMES.get(payment['method'], payment['method'])

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reçu de Paiement N° {receipt_no}</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: 'Inter', 'Segoe UI', sans-serif;
            background: #f5f5f5;
            display: flex;
            justify-content: center;
            padding: 20px;
            color: #333;
        }}

        .receipt {{
            width: 400px;
            background: white;
            border: 3px solid #1a365d;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
        }}

        .receipt-header {{
            background: linear-gradient(135deg, #1a365d 0%, #2d5a9e 100%);
            color: white;
            text-align: center;
            padding: 20px 16px;
        }}

        .receipt-header h1 {{
            font-size: 22px;
            font-weight: 700;
            letter-spacing: 2px;
            margin-bottom: 6px;
        }}

        .receipt-header .address {{
            font-size: 12px;
            opacity: 0.9;
        }}

        .receipt-title {{
            text-align: center;
            padding: 16px;
            border-bottom: 2px dashed #ccc;
        }}

        .receipt-title h2 {{
            font-size: 18px;
            color: #1a365d;
            font-weight: 700;
        }}

        .receipt-title .receipt-no {{
            font-size: 14px;
            color: #666;
            margin-top: 4px;
        }}

        .receipt-section {{
            padding: 12px 20px;
            border-bottom: 1px solid #eee;
        }}

        .receipt-section:last-of-type {{
            border-bottom: none;
        }}

        .section-title {{
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            color: #1a365d;
            letter-spacing: 1px;
            margin-bottom: 8px;
        }}

        .info-row {{
            display: flex;
            justify-content: space-between;
            padding: 4px 0;
            font-size: 13px;
        }}

        .info-row .label {{
            color: #666;
        }}

        .info-row .value {{
            font-weight: 600;
            text-align: right;
        }}

        .amounts {{
            background: #f8fafc;
            padding: 16px 20px;
            border-top: 2px solid #1a365d;
            border-bottom: 2px solid #1a365d;
        }}

        .amount-row {{
            display: flex;
            justify-content: space-between;
            padding: 6px 0;
            font-size: 14px;
        }}

        .amount-row.total {{
            border-top: 2px solid #1a365d;
            margin-top: 8px;
            padding-top: 10px;
            font-size: 18px;
            font-weight: 700;
            color: #1a365d;
        }}

        .amount-row.remaining {{
            color: #c53030;
            font-weight: 600;
        }}

        .amount-row .label {{ color: #555; }}
        .amount-row .value {{ font-weight: 600; font-variant-numeric: tabular-nums; }}

        .signatures {{
            display: flex;
            justify-content: space-between;
            padding: 24px 20px 16px;
        }}

        .sig-box {{
            text-align: center;
            width: 45%;
        }}

        .sig-box .sig-line {{
            border-top: 1px solid #333;
            margin-bottom: 4px;
            height: 40px;
        }}

        .sig-box .sig-label {{
            font-size: 11px;
            color: #666;
        }}

        .receipt-footer {{
            background: #1a365d;
            color: white;
            text-align: center;
            padding: 10px;
            font-size: 11px;
        }}

        .paid-stamp {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%) rotate(-15deg);
            font-size: 60px;
            font-weight: 900;
            color: rgba(34, 197, 94, 0.15);
            letter-spacing: 8px;
            pointer-events: none;
            z-index: 0;
        }}

        .print-btn {{
            display: block;
            width: 200px;
            margin: 20px auto;
            padding: 12px 24px;
            background: #1a365d;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            text-align: center;
            text-decoration: none;
        }}

        .print-btn:hover {{
            background: #2d5a9e;
        }}

        @media print {{
            body {{
                background: white;
                padding: 0;
            }}
            .receipt {{
                border: 2px solid #000;
                box-shadow: none;
                width: 100%;
                max-width: 400px;
            }}
            .print-btn {{
                display: none !important;
            }}
        }}
    </style>
</head>
<body>
    <div>
        <div class="receipt" id="receipt">
            <div class="receipt-header">
                <h1>🎉 SAMBA FÊTE</h1>
                <div class="address">102 ZAM, Nouvelle Ville, Constantine</div>
                <div class="address" style="margin-top:2px;">Tél: 0550 50 37 67</div>
            </div>

            <div class="receipt-title">
                <h2>REÇU DE PAIEMENT</h2>
                <div class="receipt-no">N°: {receipt_no}</div>
            </div>

            <div class="receipt-section">
                <div class="section-title">Client &amp; Événement</div>
                <div class="info-row">
                    <span class="label">Client:</span>
                    <span class="value">{event['client_name']}</span>
                </div>
                <div class="info-row">
                    <span class="label">Événement:</span>
                    <span class="value">{event['title']}</span>
                </div>
                <div class="info-row">
                    <span class="label">Type:</span>
                    <span class="value">{event['event_type']}</span>
                </div>
                <div class="info-row">
                    <span class="label">Date événement:</span>
                    <span class="value">{format_date_fr(event['event_date'])}</span>
                </div>
            </div>

            <div class="amounts">
                <div class="amount-row">
                    <span class="label">Montant total</span>
                    <span class="value">{format_da(event['total_amount'])}</span>
                </div>
                <div class="amount-row">
                    <span class="label">Déjà payé (avant ce paiement)</span>
                    <span class="value">{format_da(total_paid_before)}</span>
                </div>
                <div class="amount-row" style="color: #059669;">
                    <span class="label">Montant reçu</span>
                    <span class="value" style="font-size: 18px;">{format_da(payment['amount'])}</span>
                </div>
                <div class="amount-row remaining">
                    <span class="label">Reste à payer</span>
                    <span class="value">{format_da(max(remaining, 0))}</span>
                </div>
            </div>

            <div class="receipt-section">
                <div class="section-title">Détails du Paiement</div>
                <div class="info-row">
                    <span class="label">Date:</span>
                    <span class="value">{format_date_fr(payment['date'])}</span>
                </div>
                <div class="info-row">
                    <span class="label">Mode:</span>
                    <span class="value">{method_name}</span>
                </div>
                <div class="info-row">
                    <span class="label">Type:</span>
                    <span class="value">{payment['payment_type'].capitalize()}</span>
                </div>
                {f'''<div class="info-row">
                    <span class="label">Référence:</span>
                    <span class="value">{payment['reference']}</span>
                </div>''' if payment.get('reference') else ''}
            </div>

            <div class="signatures">
                <div class="sig-box">
                    <div class="sig-line"></div>
                    <div class="sig-label">Signature client</div>
                </div>
                <div class="sig-box">
                    <div class="sig-line"></div>
                    <div class="sig-label">Signature admin</div>
                </div>
            </div>

            <div class="receipt-footer">
                SAMBA FÊTE - Salle de réception - Constantine
            </div>
        </div>

        <button class="print-btn" onclick="window.print()">
            🖨️ Imprimer le Reçu
        </button>
    </div>
</body>
</html>"""
    return html

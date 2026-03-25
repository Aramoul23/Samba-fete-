"""
Generate a professional venue rental contract PDF (French) for Samba Fête.
Uses ReportLab with Helvetica (no Arabic needed).
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib import colors
from io import BytesIO
from datetime import datetime

# Colors
GOLD = HexColor('#C9A84C')
DARK_NAVY = HexColor('#1B2A4A')
LIGHT_GRAY = HexColor('#F5F5F5')
MED_GRAY = HexColor('#E0E0E0')

COMPANY_NAME = "Samba Fête"
COMPANY_ADDRESS = "102 ZAM, Nouvelle Ville, Constantine"
COMPANY_TEL = "0550 50 37 67"

# French month names
MONTHS_FR = {
    1: 'janvier', 2: 'février', 3: 'mars', 4: 'avril',
    5: 'mai', 6: 'juin', 7: 'juillet', 8: 'août',
    9: 'septembre', 10: 'octobre', 11: 'novembre', 12: 'décembre'
}


def format_da(amount):
    try:
        return f"{float(amount):,.0f} DA".replace(",", " ")
    except (ValueError, TypeError):
        return "0 DA"


def format_date_fr(date_str):
    """Convert YYYY-MM-DD to French date string."""
    try:
        if isinstance(date_str, str):
            d = datetime.strptime(date_str[:10], '%Y-%m-%d')
        else:
            d = date_str
        return f"{d.day} {MONTHS_FR.get(d.month, '')} {d.year}"
    except Exception:
        return str(date_str)


def get_styles():
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        'ContractTitle', parent=styles['Title'],
        fontSize=18, textColor=DARK_NAVY, alignment=TA_CENTER,
        spaceAfter=2*mm, fontName='Helvetica-Bold'
    ))
    styles.add(ParagraphStyle(
        'ContractSubtitle', parent=styles['Normal'],
        fontSize=11, textColor=GOLD, alignment=TA_CENTER,
        spaceAfter=6*mm, fontName='Helvetica-BoldOblique'
    ))
    styles.add(ParagraphStyle(
        'ClauseTitle', parent=styles['Normal'],
        fontSize=11, textColor=colors.white,
        fontName='Helvetica-Bold', spaceAfter=0,
        spaceBefore=4*mm, leftIndent=0, rightIndent=0,
        backColor=DARK_NAVY, borderPadding=(2*mm, 3*mm, 2*mm, 3*mm)
    ))
    styles.add(ParagraphStyle(
        'ClauseText', parent=styles['Normal'],
        fontSize=9.5, leading=14, alignment=TA_JUSTIFY,
        fontName='Helvetica', spaceAfter=2*mm
    ))
    styles.add(ParagraphStyle(
        'InfoLabel', parent=styles['Normal'],
        fontSize=9, textColor=HexColor('#666666'), fontName='Helvetica'
    ))
    styles.add(ParagraphStyle(
        'InfoValue', parent=styles['Normal'],
        fontSize=10, textColor=DARK_NAVY, fontName='Helvetica-Bold'
    ))
    styles.add(ParagraphStyle(
        'SmallCenter', parent=styles['Normal'],
        fontSize=8, textColor=HexColor('#999999'), alignment=TA_CENTER,
        fontName='Helvetica'
    ))
    styles.add(ParagraphStyle(
        'SignatureLabel', parent=styles['Normal'],
        fontSize=9, alignment=TA_CENTER, fontName='Helvetica',
        spaceBefore=2*mm
    ))
    return styles


def generate_contract_pdf(event, payments, total_paid, event_lines):
    """Generate a French contract PDF for the given event."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=15*mm, bottomMargin=15*mm,
        leftMargin=18*mm, rightMargin=18*mm,
        title=f"Contrat - {event.get('title', 'Evenement')}",
        author="Samba Fête"
    )
    styles = get_styles()
    story = []

    # ─── HEADER ─────────────────────────────────────────────────────
    story.append(Paragraph("SAMBA FÊTE", styles['ContractTitle']))
    story.append(Paragraph(
        "CONTRAT DE LOCATION DE SALLE ET PRESTATION DE SERVICES",
        styles['ContractSubtitle']
    ))

    # Company info bar
    company_data = [[
        Paragraph(f"<b>{COMPANY_NAME}</b>", styles['ClauseText']),
        Paragraph(f"{COMPANY_ADDRESS}", styles['ClauseText']),
        Paragraph(f"Tél : {COMPANY_TEL}", styles['ClauseText']),
    ]]
    company_table = Table(company_data, colWidths=[55*mm, 70*mm, 50*mm])
    company_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BACKGROUND', (0,0), (-1,-1), LIGHT_GRAY),
        ('BOX', (0,0), (-1,-1), 0.5, MED_GRAY),
        ('TOPPADDING', (0,0), (-1,-1), 2*mm),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2*mm),
    ]))
    story.append(company_table)
    story.append(Spacer(1, 4*mm))

    # Contract reference
    story.append(Paragraph(
        f"<b>N° Contrat :</b> SF-{event.get('id', '000'):04d} &nbsp;&nbsp;&nbsp; "
        f"<b>Date :</b> {format_date_fr(datetime.now().date())}",
        styles['ClauseText']
    ))
    story.append(Spacer(1, 2*mm))

    # Divider
    story.append(HRFlowable(width="100%", thickness=1, color=GOLD, spaceAfter=4*mm))

    # ─── PARTIES ────────────────────────────────────────────────────
    story.append(Paragraph("<b>ENTRE LES SOUSSIGNÉS :</b>", styles['ClauseText']))
    story.append(Spacer(1, 2*mm))

    parties_data = [
        [
            Paragraph("<b>Le Prestataire :</b>", styles['ClauseText']),
            Paragraph("<b>Le Client :</b>", styles['ClauseText']),
        ],
        [
            Paragraph(
                f"<b>{COMPANY_NAME}</b><br/>"
                f"{COMPANY_ADDRESS}<br/>"
                f"Tél : {COMPANY_TEL}<br/>"
                f"<i>Ci-après dénommé « le Prestataire »</i>",
                styles['ClauseText']
            ),
            Paragraph(
                f"<b>{event.get('client_name', 'N/A')}</b><br/>"
                f"Tél : {event.get('phone', 'N/A')}"
                + (f"<br/>Tél 2 : {event['phone2']}" if event.get('phone2') else "")
                + (f"<br/>Email : {event.get('email', '')}" if event.get('email') else "")
                + (f"<br/>Adresse : {event.get('address', '')}" if event.get('address') else "")
                + f"<br/><i>Ci-après dénommé « le Client »</i>",
                styles['ClauseText']
            ),
        ],
    ]
    parties_table = Table(parties_data, colWidths=[87*mm, 87*mm])
    parties_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BACKGROUND', (0,0), (0,-1), LIGHT_GRAY),
        ('BACKGROUND', (1,0), (1,-1), LIGHT_GRAY),
        ('BOX', (0,0), (-1,-1), 0.5, MED_GRAY),
        ('INNERGRID', (0,0), (-1,-1), 0.5, MED_GRAY),
        ('TOPPADDING', (0,0), (-1,-1), 2*mm),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2*mm),
        ('LEFTPADDING', (0,0), (-1,-1), 3*mm),
        ('RIGHTPADDING', (0,0), (-1,-1), 3*mm),
    ]))
    story.append(parties_table)
    story.append(Spacer(1, 2*mm))
    story.append(HRFlowable(width="100%", thickness=1, color=GOLD, spaceAfter=4*mm))

    # ─── CLAUSES ────────────────────────────────────────────────────

    # Clause 1 — OBJET
    story.append(Paragraph("Clause 1 — OBJET", styles['ClauseTitle']))
    story.append(Paragraph(
        "Le présent contrat a pour objet la location de la salle <b>Samba Fête</b> ainsi que "
        "la fourniture de services liés à l'événement décrit ci-dessous. Le Client s'engage à "
        "respecter les termes et conditions stipulés dans le présent contrat. Toute prestation "
        "non mentionnée dans ce contrat fera l'objet d'un avenant signé par les deux parties.",
        styles['ClauseText']
    ))

    # Clause 2 — DESCRIPTION DE L'ÉVÉNEMENT
    story.append(Paragraph("Clause 2 — DESCRIPTION DE L'ÉVÉNEMENT", styles['ClauseTitle']))
    event_desc = [
        ["Type d'événement", event.get('event_type', 'N/A')],
        ["Titre / Intitulé", event.get('title', 'N/A')],
        ["Date de l'événement", format_date_fr(event.get('event_date', ''))],
        ["Créneau horaire", event.get('time_slot', 'N/A')],
        ["Salle / Lieu", event.get('venue_name', 'N/A') + (" + " + event.get('venue2_name', '') if event.get('venue2_name') else "")],
        ["Nombre d'invités (Hommes)", str(event.get('guests_men', 0))],
        ["Nombre d'invités (Femmes)", str(event.get('guests_women', 0))],
        ["Total invités", str(event.get('guests_men', 0) + event.get('guests_women', 0))],
    ]
    desc_data = [[
        Paragraph(f"<b>{r[0]}</b>", styles['ClauseText']),
        Paragraph(r[1], styles['ClauseText'])
    ] for r in event_desc]
    desc_table = Table(desc_data, colWidths=[60*mm, 114*mm])
    desc_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,-1), LIGHT_GRAY),
        ('BOX', (0,0), (-1,-1), 0.5, MED_GRAY),
        ('INNERGRID', (0,0), (-1,-1), 0.5, MED_GRAY),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 1.5*mm),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1.5*mm),
        ('LEFTPADDING', (0,0), (-1,-1), 2*mm),
    ]))
    story.append(desc_table)
    story.append(Spacer(1, 2*mm))

    # Services / line items
    if event_lines:
        story.append(Paragraph("<b>Prestations incluses :</b>", styles['ClauseText']))
        svc_header = [
            Paragraph("<b>Désignation</b>", styles['ClauseText']),
            Paragraph("<b>Montant</b>", styles['ClauseText']),
            Paragraph("<b>Type</b>", styles['ClauseText']),
        ]
        svc_rows = [svc_header]
        for line in event_lines:
            svc_rows.append([
                Paragraph(line.get('description', ''), styles['ClauseText']),
                Paragraph(format_da(line.get('amount', 0)), styles['ClauseText']),
                Paragraph("Coût" if line.get('is_cost') else "Revenu", styles['ClauseText']),
            ])
        svc_table = Table(svc_rows, colWidths=[100*mm, 45*mm, 29*mm])
        svc_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), DARK_NAVY),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('BOX', (0,0), (-1,-1), 0.5, MED_GRAY),
            ('INNERGRID', (0,0), (-1,-1), 0.5, MED_GRAY),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 1.5*mm),
            ('BOTTOMPADDING', (0,0), (-1,-1), 1.5*mm),
            ('LEFTPADDING', (0,0), (-1,-1), 2*mm),
        ]))
        story.append(svc_table)
        story.append(Spacer(1, 2*mm))

    # Clause 3 — CONDITIONS FINANCIÈRES
    story.append(Paragraph("Clause 3 — CONDITIONS FINANCIÈRES", styles['ClauseTitle']))
    remaining = event.get('total_amount', 0) - total_paid

    fin_data = [
        [Paragraph("<b>Montant total des prestations</b>", styles['ClauseText']),
         Paragraph(f"<b>{format_da(event.get('total_amount', 0))}</b>", styles['ClauseText'])],
        [Paragraph("<b>Acompte requis</b>", styles['ClauseText']),
         Paragraph(format_da(event.get('deposit_required', 0)), styles['ClauseText'])],
        [Paragraph("<b>Montant total payé à ce jour</b>", styles['ClauseText']),
         Paragraph(f"<font color='green'><b>{format_da(total_paid)}</b></font>", styles['ClauseText'])],
        [Paragraph("<b>Reste à payer</b>", styles['ClauseText']),
         Paragraph(
             f"<font color='red'><b>{format_da(remaining)}</b></font>" if remaining > 0
             else f"<font color='green'><b>Soldé</b></font>",
             styles['ClauseText']
         )],
    ]
    fin_table = Table(fin_data, colWidths=[100*mm, 74*mm])
    fin_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,-1), LIGHT_GRAY),
        ('BOX', (0,0), (-1,-1), 0.5, MED_GRAY),
        ('INNERGRID', (0,0), (-1,-1), 0.5, MED_GRAY),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 2*mm),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2*mm),
        ('LEFTPADDING', (0,0), (-1,-1), 2*mm),
        ('LINEBELOW', (0,-1), (-1,-1), 1.5, DARK_NAVY),
    ]))
    story.append(fin_table)

    # Payment history
    if payments:
        story.append(Spacer(1, 3*mm))
        story.append(Paragraph("<b>Historique des paiements :</b>", styles['ClauseText']))
        pay_header = [
            Paragraph("<b>Date</b>", styles['ClauseText']),
            Paragraph("<b>Montant</b>", styles['ClauseText']),
            Paragraph("<b>Méthode</b>", styles['ClauseText']),
            Paragraph("<b>Référence</b>", styles['ClauseText']),
        ]
        pay_rows = [pay_header]
        for p in payments[:8]:
            pay_rows.append([
                Paragraph(p.get('date', '')[:10], styles['ClauseText']),
                Paragraph(format_da(p.get('amount', 0)), styles['ClauseText']),
                Paragraph(p.get('method', ''), styles['ClauseText']),
                Paragraph(p.get('reference') or '—', styles['ClauseText']),
            ])
        pay_table = Table(pay_rows, colWidths=[40*mm, 40*mm, 47*mm, 47*mm])
        pay_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#2C3E6B')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('BOX', (0,0), (-1,-1), 0.5, MED_GRAY),
            ('INNERGRID', (0,0), (-1,-1), 0.3, MED_GRAY),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 1.5*mm),
            ('BOTTOMPADDING', (0,0), (-1,-1), 1.5*mm),
            ('LEFTPADDING', (0,0), (-1,-1), 2*mm),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, LIGHT_GRAY]),
        ]))
        story.append(pay_table)
    story.append(Spacer(1, 2*mm))

    # Clause 4 — CAUTION
    story.append(Paragraph("Clause 4 — CAUTION", styles['ClauseTitle']))
    story.append(Paragraph(
        f"Le Client verse une caution de <b>{format_da(event.get('deposit_required', 0))}</b> "
        "à la signature du présent contrat. Cette caution sera restituée intégralement au Client "
        "dans un délai de <b>48 heures</b> suivant la fin de l'événement, sous réserve de l'état "
        "des locaux. En cas de dégradation constatée, le Prestataire se réserve le droit de "
        "retenir tout ou partie de la caution pour couvrir les frais de remise en état.",
        styles['ClauseText']
    ))

    # Clause 5 — OBLIGATIONS DU CLIENT
    story.append(Paragraph("Clause 5 — OBLIGATIONS DU CLIENT", styles['ClauseTitle']))
    story.append(Paragraph(
        "Le Client s'engage à :<br/>"
        "• Respecter le règlement intérieur de la salle et les horaires convenus ;<br/>"
        "• Assurer la propreté des locaux et rendre la salle dans l'état où elle a été reçue ;<br/>"
        "• Ne pas dépasser la capacité d'accueil de la salle ;<br/>"
        "• Ne pas introduire de substances illicites ni engager de comportements dangereux ;<br/>"
        "• Régler l'intégralité du montant avant la date de l'événement ;<br/>"
        "• Signaler toute anomalie ou dommage constaté avant le début de l'événement.",
        styles['ClauseText']
    ))

    # Clause 6 — OBLIGATIONS DU LOCATEUR
    story.append(Paragraph("Clause 6 — OBLIGATIONS DU LOCATEUR", styles['ClauseTitle']))
    story.append(Paragraph(
        "Le Prestataire s'engage à :<br/>"
        "• Mettre à disposition la salle en bon état et dans les conditions convenues ;<br/>"
        "• Assurer le nettoyage des locaux avant et après l'événement ;<br/>"
        "• Fournir les équipements et services mentionnés dans le présent contrat ;<br/>"
        "• Garantir la sécurité des personnes et des biens pendant la durée de l'événement ;<br/>"
        "• Informer le Client de toute modification pouvant affecter le déroulement de l'événement.",
        styles['ClauseText']
    ))

    # Clause 7 — ANNULATION
    story.append(Paragraph("Clause 7 — ANNULATION", styles['ClauseTitle']))
    story.append(Paragraph(
        "<b>Annulation par le Client :</b> En cas d'annulation par le Client, l'acompte versé ne "
        "sera pas remboursé. Si le solde a été réglé intégralement, le Prestataire retiendra "
        "l'acompte et remboursera le surplus dans un délai de 30 jours.<br/><br/>"
        "<b>Annulation par le Prestataire :</b> En cas d'annulation imputable au Prestataire, "
        "l'intégralité des sommes versées sera remboursée au Client dans un délai de 15 jours. "
        "Le Prestataire se engage à proposer, dans la mesure du possible, une date de remplacement.<br/><br/>"
        "<b>Force majeure :</b> En cas de force majeure (catastrophe naturelle, pandémie, décision "
        "gouvernementale), les deux parties conviennent d'un report de l'événement sans frais supplémentaires.",
        styles['ClauseText']
    ))

    # Clause 8 — RÈGLEMENT INTÉRIEUR
    story.append(Paragraph("Clause 8 — RÈGLEMENT INTÉRIEUR", styles['ClauseTitle']))
    story.append(Paragraph(
        "Le Client et ses invités devront se conformer aux règles suivantes :<br/>"
        "• L'accès à la salle est strictement réservé aux personnes conviées ;<br/>"
        "• La musique devra être modérée après 23h00 et arrêtée à 00h00 ;<br/>"
        "• Le stationnement est autorisé uniquement dans les espaces désignés ;<br/>"
        "• Il est formellement interdit de fumer dans les salles closes ;<br/>"
        "• Tout objet oublié sera conservé pendant une durée maximale de 30 jours ;<br/>"
        "• Le non-respect du règlement intérieur pourra entraîner la résiliation immédiate du contrat.",
        styles['ClauseText']
    ))

    story.append(Spacer(1, 6*mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MED_GRAY, spaceAfter=4*mm))

    # ─── SIGNATURES ─────────────────────────────────────────────────
    story.append(Paragraph(
        "<b>Fait en deux (2) exemplaires originaux, à Constantine, le "
        f"{format_date_fr(datetime.now().date())}</b>",
        ParagraphStyle('PreSig', parent=styles['ClauseText'], alignment=TA_CENTER, spaceBefore=3*mm)
    ))
    story.append(Spacer(1, 12*mm))

    sig_data = [[
        Paragraph("<b>Le Prestataire</b>", styles['SignatureLabel']),
        Paragraph("<b>Le Client</b>", styles['SignatureLabel']),
    ], [
        Paragraph("<br/><br/><br/><br/>", styles['ClauseText']),
        Paragraph("<br/><br/><br/><br/>", styles['ClauseText']),
    ], [
        Paragraph("Samba Fête", styles['SignatureLabel']),
        Paragraph(event.get('client_name', ''), styles['SignatureLabel']),
    ], [
        Paragraph(COMPANY_ADDRESS, styles['SignatureLabel']),
        Paragraph(event.get('phone', ''), styles['SignatureLabel']),
    ]]
    sig_table = Table(sig_data, colWidths=[87*mm, 87*mm])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (0,-1), 'RIGHT'),
        ('ALIGN', (1,0), (1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('LEFTPADDING', (0,0), (-1,-1), 2*mm),
        ('RIGHTPADDING', (0,0), (-1,-1), 2*mm),
    ]))
    story.append(sig_table)

    # Footer
    story.append(Spacer(1, 10*mm))
    story.append(HRFlowable(width="100%", thickness=1, color=GOLD, spaceAfter=2*mm))
    story.append(Paragraph(
        f"{COMPANY_NAME} · {COMPANY_ADDRESS} · Tél : {COMPANY_TEL}",
        styles['SmallCenter']
    ))
    story.append(Paragraph(
        "Ce contrat est régi par le droit algérien. Tout litige sera soumis aux tribunaux compétents d'Alger.",
        styles['SmallCenter']
    ))

    # Build
    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes

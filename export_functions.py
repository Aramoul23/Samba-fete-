"""
Export utilities for Samba Fête
Generates ODS (OpenDocument Spreadsheet) files for data export.
"""

from odf.opendocument import OpenDocumentSpreadsheet
from odf.table import Table, TableRow, TableCell
from odf.text import P
from datetime import datetime


def format_da(amount):
    """Format amount as Algerian Dinar."""
    try:
        return f"{float(amount):,.0f} DA".replace(",", " ")
    except (ValueError, TypeError):
        return "0 DA"


def create_ods_document(sheet_name, headers, rows, totals=None):
    """Create an ODS document with the given data."""
    doc = OpenDocumentSpreadsheet()
    
    # Create table
    table = Table(name=sheet_name)
    
    # Header row
    header_row = TableRow()
    for header in headers:
        cell = TableCell(valuetype="string")
        cell.addElement(P(text=str(header)))
        header_row.addElement(cell)
    table.addElement(header_row)
    
    # Data rows
    for row_data in rows:
        row = TableRow()
        for i, cell_data in enumerate(row_data):
            if isinstance(cell_data, (int, float)):
                cell = TableCell(valuetype="float")
                cell.addElement(P(text=str(cell_data)))
            else:
                cell = TableCell(valuetype="string")
                cell.addElement(P(text=str(cell_data or '')))
            row.addElement(cell)
        table.addElement(row)
    
    # Totals row
    if totals:
        total_row = TableRow()
        for i in range(len(headers)):
            cell = TableCell()
            if i in totals:
                cell.addElement(P(text=str(totals[i])))
            elif i == 0:
                cell.addElement(P(text="TOTAL"))
            else:
                cell.addElement(P(text=''))
            total_row.addElement(cell)
        table.addElement(total_row)
    
    doc.spreadsheet.addElement(table)
    
    import io
    output = io.BytesIO()
    doc.write(output)
    return output.getvalue()


def export_events_ods(events, export_date):
    """Export events data to ODS format."""
    headers = ['#', 'Date', 'Titre', 'Client', 'Type', 'Lieu', 'Creneau', 'Hommes', 'Femmes', 'Total Invites', 'Montant', 'Paye', 'Reste', 'Statut']
    rows = []
    total_amount = total_paid = 0
    
    for i, event in enumerate(events, 1):
        invited = (event.get('guests_men', 0) or 0) + (event.get('guests_women', 0) or 0)
        amount = float(event.get('total_amount', 0) or 0)
        paid = float(event.get('total_paid', 0) or 0)
        total_amount += amount
        total_paid += paid
        rows.append([i, event.get('event_date', '')[:10], event.get('title', ''), event.get('client_name', ''),
                     event.get('event_type', ''), event.get('venue_name', ''), event.get('time_slot', ''),
                     event.get('guests_men', 0) or 0, event.get('guests_women', 0) or 0, invited,
                     amount, paid, amount - paid, event.get('status', '')])
    
    totals = {10: total_amount, 11: total_paid, 12: total_amount - total_paid}
    return create_ods_document('Evenements', headers, rows, totals)


def export_clients_ods(clients, export_date):
    """Export clients data to ODS format."""
    headers = ['#', 'Nom', 'Telephone', 'Telephone 2', 'Email', 'Adresse', 'Nb Evenements', 'Total Facture', 'Total Paye', 'Reste']
    rows = []
    total_billed = total_paid = 0
    
    for i, client in enumerate(clients, 1):
        billed = float(client.get('total_owed', 0) or 0)
        paid = float(client.get('total_paid', 0) or 0)
        total_billed += billed
        total_paid += paid
        rows.append([i, client.get('name', ''), client.get('phone', ''), client.get('phone2', '') or '',
                     client.get('email', '') or '', client.get('address', '') or '', client.get('event_count', 0) or 0,
                     billed, paid, billed - paid])
    
    totals = {7: total_billed, 8: total_paid, 9: total_billed - total_paid}
    return create_ods_document('Clients', headers, rows, totals)


def export_payments_ods(payments, export_date):
    """Export payments data to ODS format."""
    headers = ['#', 'Date', 'Client', 'Evenement', 'Montant', 'Methode', 'Type', 'Reference', 'Statut']
    rows = []
    total_amount = 0
    
    for i, payment in enumerate(payments, 1):
        amount = float(payment.get('amount', 0) or 0)
        is_refunded = payment.get('is_refunded', 0)
        if not is_refunded:
            total_amount += amount
        status = 'Rembourse' if is_refunded else 'Valide'
        rows.append([i, payment.get('date', '')[:10], payment.get('client_name', ''), payment.get('title', ''),
                     amount, payment.get('method', ''), payment.get('payment_type', ''),
                     payment.get('reference', '') or '', status])
    
    totals = {4: total_amount}
    return create_ods_document('Paiements', headers, rows, totals)


def export_expenses_ods(expenses, export_date):
    """Export expenses data to ODS format."""
    headers = ['#', 'Date', 'Categorie', 'Description', 'Montant', 'Fournisseur', 'Evenement', 'Methode', 'Reference']
    rows = []
    total_amount = 0
    
    for i, expense in enumerate(expenses, 1):
        amount = float(expense.get('amount', 0) or 0)
        total_amount += amount
        rows.append([i, expense.get('expense_date', ''), expense.get('category', ''),
                     expense.get('description', '') or '', amount, expense.get('vendor', '') or '',
                     expense.get('event_title', '') or '', expense.get('method', ''),
                     expense.get('reference', '') or ''])
    
    totals = {4: total_amount}
    return create_ods_document('Depenses', headers, rows, totals)


def export_financials_ods(event_financials, summary_stats, export_date):
    """Export financial report to ODS format."""
    headers = ['#', 'Date', 'Evenement', 'Client', 'Type', 'Revenus', 'Couts', 'Benefice', 'Paye', 'Reste', 'Statut']
    rows = []
    total_revenue = total_costs = total_paid = 0
    
    for i, ef in enumerate(event_financials, 1):
        revenue = float(ef.get('total_revenue', 0) or 0)
        costs = float(ef.get('total_costs', 0) or 0)
        paid = float(ef.get('total_paid', 0) or 0)
        total_revenue += revenue
        total_costs += costs
        total_paid += paid
        rows.append([i, ef.get('event_date', '')[:10], ef.get('title', ''), ef.get('client_name', ''),
                     ef.get('event_type', ''), revenue, costs, revenue - costs,
                     paid, float(ef.get('total_amount', 0) or 0) - paid, ef.get('status', '')])
    
    totals = {5: total_revenue, 6: total_costs, 7: total_revenue - total_costs,
              8: total_paid, 9: total_revenue - total_paid}
    return create_ods_document('Finances', headers, rows, totals)


def export_pl_report_ods(monthly_data, export_date):
    """Export Profit & Loss report to ODS format."""
    headers = ['Mois', 'Revenus', 'Depenses', 'Benefice Net', 'Marge %']
    rows = []
    total_income = total_expenses = 0
    
    for month in monthly_data:
        income = float(month.get('income', 0) or 0)
        expenses = float(month.get('expenses', 0) or 0)
        profit = income - expenses
        margin = (profit / income * 100) if income > 0 else 0
        total_income += income
        total_expenses += expenses
        rows.append([month.get('month', ''), income, expenses, profit, f"{margin:.1f}%"])
    
    total_profit = total_income - total_expenses
    total_margin = (total_profit / total_income * 100) if total_income > 0 else 0
    totals = {1: total_income, 2: total_expenses, 3: total_profit, 4: f"{total_margin:.1f}%"}
    return create_ods_document('P_L', headers, rows, totals)

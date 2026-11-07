"""Generate deterministic, fictional statement PDFs from the sample invoices."""
from pathlib import Path
from datetime import date, timedelta
from decimal import Decimal
import calendar
import csv
import json
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
ACCOUNT = 'DEMO-ACCOUNT-001'
D = Decimal

def build():
    with (DATA / 'invoices/sample_invoices_2025.csv').open(newline='', encoding='utf-8') as f:
        invoices = list(csv.DictReader(f))
    by_number = {int(r['invoice_number'][-3:]): r for r in invoices}
    entries = []

    def add(day, description, reference='', incoming='0', outgoing='0'):
        entries.append(dict(date=day, description=description, reference=reference,
                            incoming=D(str(incoming)), outgoing=D(str(outgoing))))

    special = {3, 5, 7, 9, 11, 13, 14, 24}
    for n, inv in by_number.items():
        if n in special:
            continue
        day = date.fromisoformat(inv['invoice_date']) + timedelta(days=12)
        add(day, inv['customer_name'], inv['invoice_number'], incoming=inv['total_amount'])

    add(date(2025, 2, 18), by_number[3]['customer_name'], by_number[3]['invoice_number'], incoming='4830')
    add(date(2025, 3, 4), by_number[3]['customer_name'], by_number[3]['invoice_number'], incoming='4830')
    add(date(2025, 3, 20), by_number[5]['customer_name'], by_number[5]['invoice_number'], incoming='4000')
    add(date(2025, 7, 20), by_number[9]['customer_name'], 'DEMO-2025-009 + DEMO-2025-013', incoming='19665')
    add(date(2025, 7, 10), by_number[7]['customer_name'], '', incoming='8640')
    add(date(2025, 4, 18), 'Internal transfer from own savings account', 'OWN-TRANSFER', incoming='8640')
    add(date(2025, 8, 12), 'Loan disbursement', 'DEMO-LOAN', incoming='20000')
    add(date(2026, 1, 12), by_number[24]['customer_name'], by_number[24]['invoice_number'], incoming='9775')

    # Small, illustrative operating outflows; this is not a full business ledger.
    for month in range(1, 13):
        add(date(2025, month, 2), 'Warehouse rent', f'RENT-{month:02}', outgoing='1200')
        add(date(2025, month, 15), 'Payment to Demo Grocery Supplier', f'SUPPLIER-{month:02}', outgoing=str(3000 + month * 175))
        add(date(2025, month, 28), 'Account service fee', f'FEE-{month:02}', outgoing='25')

    entries.sort(key=lambda r: (r['date'], r['reference'], r['description']))
    balance = D('40000.00')
    for i, e in enumerate(entries, 1):
        e['id'] = f'TX-{i:03}'
        e['opening'] = balance
        balance += e['incoming'] - e['outgoing']
        e['balance'] = balance
        assert balance >= 0

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='CellSmall', fontName='Helvetica', fontSize=8, leading=11))
    styles.add(ParagraphStyle(name='HeaderSmall', fontName='Helvetica-Bold', fontSize=8, leading=11, textColor=colors.white))
    styles.add(ParagraphStyle(name='MutedSmall', fontSize=9, leading=13, textColor=colors.HexColor('#536478')))

    def paragraph(value, style='CellSmall'):
        return Paragraph(escape(str(value)), styles[style])

    exported = []
    for year, month in [(2025, m) for m in range(1, 13)] + [(2026, 1)]:
        month_entries = [r for r in entries if (r['date'].year, r['date'].month) == (year, month)]
        assert month_entries
        folder = DATA / ('bank_statements' if year == 2025 else 'extra_period')
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f'statement_{year}-{month:02}.pdf'
        opening, closing = month_entries[0]['opening'], month_entries[-1]['balance']
        incoming = sum((r['incoming'] for r in month_entries), D('0'))
        outgoing = sum((r['outgoing'] for r in month_entries), D('0'))
        assert opening + incoming - outgoing == closing
        first = date(year, month, 1)
        last = date(year, month, calendar.monthrange(year, month)[1])
        story = [Paragraph('Demo Bank - Monthly Statement', styles['Title']),
                 paragraph('SYNTHETIC TEST DATA - NOT A REAL BANK DOCUMENT', 'MutedSmall'), Spacer(1, 13),
                 paragraph('Account holder: Demo Noor Wholesale'),
                 paragraph(f'Account reference: {ACCOUNT}'),
                 paragraph(f'Statement period: {first.isoformat()} to {last.isoformat()}'),
                 paragraph('Currency: SAR'), Spacer(1, 14)]
        summary = Table([['Opening balance', 'Total incoming', 'Total outgoing', 'Closing balance'],
                         [f'{v:,.2f}' for v in [opening, incoming, outgoing, closing]]], colWidths=[192]*4)
        summary.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#EAF0F7')),
                                    ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),10),
                                    ('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
        story.extend([summary, Spacer(1, 18)])
        headers = ['Date','Transaction ID','Description','Payment reference','Outgoing','Incoming','Balance']
        table_rows = [[paragraph(h,'HeaderSmall') for h in headers]]
        for r in month_entries:
            table_rows.append([paragraph(r['date'].isoformat()), paragraph(r['id']), paragraph(r['description']),
                               paragraph(r['reference'] or '-'), f"{r['outgoing']:,.2f}",
                               f"{r['incoming']:,.2f}", f"{r['balance']:,.2f}"])
            exported.append({'transaction_id':r['id'], 'transaction_date':r['date'].isoformat(),
                             'description':r['description'],'payment_reference':r['reference'],
                             'outgoing':str(r['outgoing']),'incoming':str(r['incoming']),
                             'balance':str(r['balance']), 'statement_file':path.relative_to(ROOT).as_posix(),
                             'page':1})
        table = Table(table_rows, colWidths=[68,67,170,165,89,89,120], repeatRows=1)
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#17324D')),
                                  ('VALIGN',(0,0),(-1,-1),'MIDDLE'),('FONTNAME',(0,1),(-1,-1),'Helvetica'),
                                  ('FONTSIZE',(0,1),(-1,-1),9),('ALIGN',(4,1),(-1,-1),'RIGHT'),
                                  ('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),
                                  ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F3F6FA')]),
                                  ('LINEBELOW',(0,-1),(-1,-1),0.5,colors.HexColor('#CCD5DF'))]))
        story += [table, Spacer(1, 16), paragraph('All names, references and transactions are fictional. Amounts are for software testing only.', 'MutedSmall')]
        def footer(canvas, doc):
            canvas.setFont('Helvetica',8)
            canvas.setFillColor(colors.HexColor('#536478'))
            canvas.drawString(36,22,'Qawafel assessment - synthetic sample')
            canvas.drawRightString(806,22,f'Page {doc.page}')
        SimpleDocTemplate(str(path), pagesize=landscape(A4), rightMargin=36,leftMargin=36,
                          topMargin=28,bottomMargin=36,title=f'Synthetic statement {year}-{month:02}',author='Demo Noor Wholesale').build(story,onFirstPage=footer,onLaterPages=footer)

    tests = ROOT/'tests'
    tests.mkdir(exist_ok=True)
    with (tests/'expected_transactions.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(exported[0])); writer.writeheader(); writer.writerows(exported)
    cases = [
        dict(id='full_payment', invoices=['DEMO-2025-001'], expected='One referenced incoming payment of SAR 8,280 on 2025-01-17. Suggested full amount, not confirmed settlement.'),
        dict(id='instalments', invoices=['DEMO-2025-003'], expected='Two referenced payments of SAR 4,830 on 2025-02-18 and 2025-03-04; combined SAR 9,660.'),
        dict(id='partial_payment', invoices=['DEMO-2025-005'], expected='Only SAR 4,000 is explicitly referenced against SAR 11,040 invoiced. SAR 7,040 is not covered by this suggestion; do not label it overdue automatically.'),
        dict(id='combined_payment', invoices=['DEMO-2025-009','DEMO-2025-013'], expected='One SAR 19,665 payment on 2025-07-20 references both invoices for the same customer. Proposed allocations: SAR 9,315 and SAR 10,350; count the transaction once.'),
        dict(id='ambiguous_amount', invoices=['DEMO-2025-007','DEMO-2025-011'], expected='A SAR 8,640 receipt on 2025-07-10 has no invoice reference. Both invoices have the same customer and amount. Show ambiguity; do not allocate the receipt in full to both.'),
        dict(id='no_identified_payment', invoices=['DEMO-2025-014'], expected='No observed referenced payment. Display No matching payment identified, not Unpaid.'),
        dict(id='non_sales_inflows', invoices=[], expected='Exclude the SAR 8,640 own-account transfer on 2025-04-18 and SAR 20,000 loan on 2025-08-12 from customer-payment suggestions.'),
        dict(id='outside_period', invoices=['DEMO-2025-024'], expected='No payment visible in 2025. A SAR 9,775 referenced payment appears on 2026-01-12 in the separate extra_period file. Keep outside the base 2025 package.'),
        dict(id='missing_statement', invoices=[], expected='Upload 2025 statements except statement_2025-04.pdf. Flag April coverage as missing for DEMO-ACCOUNT-001. Uploading April clears the coverage gap after revalidation.'),
        dict(id='duplicate_statement', invoices=[], expected='Attempt to upload statement_2025-03.pdf twice. Detect the duplicate and do not import its transactions twice.'),
    ]
    (tests/'test_cases.json').write_text(json.dumps(cases,indent=2)+'\n',encoding='utf-8')
    print(f'Generated 12 monthly statements + 1 optional outside-period statement, {len(exported)} transactions, and {len(cases)} documented test cases.')

if __name__=='__main__':
    build()

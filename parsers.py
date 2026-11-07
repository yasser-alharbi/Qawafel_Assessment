"""Read the documented invoice template and synthetic one-page bank layout."""
import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import openpyxl
import pdfplumber


def money(value):
    try:
        n = Decimal(str(value).replace(',', '').strip())
        if not n.is_finite() or n < 0 or n != n.quantize(Decimal('.01')):
            raise ValueError()
        return n
    except (InvalidOperation, ValueError):
        raise ValueError('Amounts must be non-negative numbers with at most two decimals.')


def iso_date(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return date.fromisoformat(str(value).strip()).isoformat()


def invoices(content, suffix):
    if suffix == '.xlsx':
        book = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        if len(book.sheetnames) != 1:
            raise ValueError('Use one invoice sheet per workbook for this prototype.')
        sheet = book.active
        rows = list(sheet.iter_rows(values_only=True))
        sheet_name = sheet.title
        book.close()
    else:
        rows = list(csv.reader(io.StringIO(content.decode('utf-8-sig'))))
        sheet_name = 'CSV'
    if not rows or len(rows) > 10001:
        raise ValueError('Provide a header and up to 10,000 invoices.')
    headers = [str(h or '').strip() for h in rows[0]]
    required = {'invoice_number', 'invoice_date', 'customer_name', 'total_amount', 'currency'}
    if not required.issubset(headers) or len(set(headers)) != len(headers):
        raise ValueError('Required unique columns: ' + ', '.join(sorted(required)))
    records = []
    for row_number, row in enumerate(rows[1:], 2):
        if all(v is None or str(v).strip() == '' for v in row):
            continue
        values = dict(zip(headers, row))
        try:
            if any(values.get(k) is None or not str(values[k]).strip() for k in required):
                raise ValueError('A required value is missing.')
            amount = money(values['total_amount'])
            if amount == 0:
                raise ValueError('Invoice total must be greater than zero.')
            if str(values['currency']).strip().upper() != 'SAR':
                raise ValueError('This prototype supports SAR only.')
            records.append(dict(type='invoice', record_date=iso_date(values['invoice_date']),
                                amount=str(amount), currency='SAR', direction=None,
                                reference=str(values['invoice_number']).strip(),
                                counterparty=str(values['customer_name']).strip(),
                                description=str(values.get('description') or ''),
                                source_location=f'{sheet_name}, row {row_number}'))
        except (ValueError, TypeError) as exc:
            raise ValueError(f'{sheet_name}, row {row_number}: {exc}') from exc
    if not records:
        raise ValueError('No invoice rows were found.')
    return {}, records


def bank_statement(content):
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        if len(pdf.pages) != 1:
            raise ValueError('Use the supplied one-page monthly statement layout.')
        page = pdf.pages[0]
        text = page.extract_text() or ''
        if 'Demo Bank - Monthly Statement' not in text or abs(page.width - 841.89) > 2:
            raise ValueError('Unsupported or scanned PDF. Use a text-based Demo Bank statement.')
        def find(pattern):
            match = re.search(pattern, text)
            if not match:
                raise ValueError('A required statement heading is missing or unreadable.')
            return match
        account = find(r'Account reference: (\S+)').group(1)
        holder = find(r'Account holder: ([^\n]+)').group(1).strip()
        period = find(r'Statement period: (\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})')
        start, end = iso_date(period.group(1)), iso_date(period.group(2))
        if end < start or find(r'Currency: (\S+)').group(1) != 'SAR':
            raise ValueError('Invalid statement period or unsupported currency.')
        summary = find(r'Opening balance Total incoming Total outgoing Closing balance\n([\d,]+\.\d{2}) ([\d,]+\.\d{2}) ([\d,]+\.\d{2}) ([\d,]+\.\d{2})')
        opening, total_in, total_out, closing = [money(v) for v in summary.groups()]
        words = page.extract_words()
        starts = sorted(w['top'] for w in words if 36 <= w['x0'] < 104 and re.fullmatch(r'\d{4}-\d{2}-\d{2}', w['text']))
        # Column boundaries belong only to the documented synthetic PDF layout.
        boundaries = [36,104,171,341,506,595,684,804]
        records, balance = [], opening
        incoming_sum = outgoing_sum = Decimal('0')
        for i, top in enumerate(starts):
            bottom = starts[i+1] - 2 if i+1 < len(starts) else top + 25
            cells = [' '.join((page.crop((boundaries[j],top-1,boundaries[j+1],bottom)).extract_text() or '').split()) for j in range(7)]
            day, tx, description, reference, debit, credit, new_balance = cells
            if not re.fullmatch(r'TX-\d+', tx):
                raise ValueError('A statement row could not be read reliably.')
            day = iso_date(day)
            if not start <= day <= end:
                raise ValueError('A transaction falls outside its statement period.')
            outgoing, incoming, row_balance = money(debit), money(credit), money(new_balance)
            if (outgoing > 0) == (incoming > 0):
                raise ValueError('Each transaction must have one incoming or outgoing amount.')
            balance += incoming - outgoing
            if balance != row_balance:
                raise ValueError('The transaction balances do not reconcile.')
            incoming_sum += incoming
            outgoing_sum += outgoing
            records.append(dict(type='bank_transaction', record_date=day,
                                amount=str(incoming or outgoing), currency='SAR',
                                direction='incoming' if incoming else 'outgoing',
                                reference='' if reference == '-' else reference,
                                counterparty='', description=description,
                                source_location=f'PDF page 1, {tx}'))
        if not records or balance != closing or incoming_sum != total_in or outgoing_sum != total_out:
            raise ValueError('The extracted rows do not reconcile with the statement totals.')
        return dict(account_reference=account, holder=holder, coverage_start=start, coverage_end=end,
                    opening=str(opening), closing=str(closing)), records

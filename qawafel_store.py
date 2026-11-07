"""Qawafel's five-table SQLite store and applicant workflow rules."""
import calendar
import hashlib
import json
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from parsers import invoices, bank_statement

ROOT = Path(__file__).resolve().parent

def now():
    return datetime.now(timezone.utc).isoformat()

def connect(path=None):
    path = Path(path or os.environ.get('QAWAFEL_DB', ROOT/'local_data/app.sqlite3'))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS application (
      id INTEGER PRIMARY KEY, business_name TEXT NOT NULL, applicant_id TEXT NOT NULL,
      period_start TEXT NOT NULL, period_end TEXT NOT NULL, required_accounts TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'draft', submitted_at TEXT);
    CREATE TABLE IF NOT EXISTS document (
      id INTEGER PRIMARY KEY, application_id INTEGER NOT NULL REFERENCES application(id),
      file_name TEXT NOT NULL, content BLOB NOT NULL, digest TEXT NOT NULL, type TEXT NOT NULL,
      processing_status TEXT NOT NULL, error TEXT, metadata TEXT NOT NULL,
      replaces_document_id INTEGER REFERENCES document(id), active INTEGER NOT NULL DEFAULT 1,
      uploaded_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS financial_record (
      id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES document(id),
      type TEXT NOT NULL, record_date TEXT NOT NULL, amount TEXT NOT NULL, currency TEXT NOT NULL,
      direction TEXT, reference TEXT, counterparty TEXT, description TEXT, source_location TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS data_issue (
      id INTEGER PRIMARY KEY, application_id INTEGER NOT NULL REFERENCES application(id),
      issue_key TEXT NOT NULL, document_id INTEGER REFERENCES document(id),
      record_id INTEGER REFERENCES financial_record(id), account_reference TEXT, gap_period TEXT,
      severity TEXT NOT NULL, status TEXT NOT NULL, message TEXT NOT NULL, next_action TEXT NOT NULL,
      applicant_explanation TEXT NOT NULL DEFAULT '', explained_by TEXT, explained_at TEXT,
      UNIQUE(application_id,issue_key));
    CREATE TABLE IF NOT EXISTS payment_suggestion (
      id INTEGER PRIMARY KEY, invoice_record_id INTEGER REFERENCES financial_record(id),
      payment_record_id INTEGER REFERENCES financial_record(id), suggested_amount TEXT);
    ''')
    return db

def rows(db, sql, args=()):
    return [dict(r) for r in db.execute(sql,args)]

def application(db, app_id):
    return dict(db.execute('SELECT * FROM application WHERE id=?',(app_id,)).fetchone())

def editable(db, app_id):
    if application(db,app_id)['status'] != 'draft':
        raise ValueError('This request was submitted and is read-only. Create a new request to try again.')

def delete_draft(db, app_id):
    """Remove one draft and its stored copies in a single transaction."""
    with db:
        claimed = db.execute("UPDATE application SET status='deleting' WHERE id=? AND status='draft'", (app_id,))
        if claimed.rowcount != 1:
            raise ValueError('Only an existing draft can be deleted.')
        document_ids = 'SELECT id FROM document WHERE application_id=?'
        record_ids = f'SELECT id FROM financial_record WHERE document_id IN ({document_ids})'
        db.execute(f'DELETE FROM payment_suggestion WHERE invoice_record_id IN ({record_ids}) OR payment_record_id IN ({record_ids})', (app_id, app_id))
        db.execute('DELETE FROM data_issue WHERE application_id=?', (app_id,))
        db.execute(f'DELETE FROM financial_record WHERE document_id IN ({document_ids})', (app_id,))
        db.execute('DELETE FROM document WHERE application_id=?', (app_id,))
        db.execute('DELETE FROM application WHERE id=?', (app_id,))

def create_application(db, name, year, accounts):
    accounts = list(dict.fromkeys(a.strip() for a in accounts if a.strip()))
    if not name.strip() or not accounts or not 2000 <= year <= 2100:
        raise ValueError('Enter a business name, reporting year and at least one account.')
    with db:
        cur=db.execute('INSERT INTO application (business_name,applicant_id,period_start,period_end,required_accounts) VALUES (?,?,?,?,?)',
                       (name.strip(),'demo-applicant',f'{year}-01-01',f'{year}-12-31',json.dumps(accounts)))
        app_id=cur.lastrowid
        validate(db,app_id)
    return app_id

def documents(db, app_id, active=True):
    return rows(db,'SELECT * FROM document WHERE application_id=?'+(' AND active=1' if active else '')+' ORDER BY id',(app_id,))

def records(db, app_id):
    return rows(db,'''SELECT r.*,d.file_name FROM financial_record r JOIN document d ON d.id=r.document_id
                     WHERE d.application_id=? AND d.active=1 ORDER BY r.record_date,r.id''',(app_id,))

def upload(db, app_id, filename, content, replaces=None):
    editable(db,app_id)
    suffix=Path(filename).suffix.lower()
    if suffix not in ('.xlsx','.csv','.pdf') or not content or len(content)>10*1024*1024:
        raise ValueError('Upload a non-empty XLSX, CSV or PDF file up to 10 MB.')
    digest=hashlib.sha256(content).hexdigest()
    if db.execute('SELECT 1 FROM document WHERE application_id=? AND digest=? AND active=1',(app_id,digest)).fetchone():
        raise ValueError(f'{filename}: this exact file is already included. No rows were added.')
    kind='bank_statement' if suffix=='.pdf' else 'invoices'
    if replaces:
        old=db.execute('SELECT * FROM document WHERE id=? AND application_id=? AND active=1',(replaces,app_id)).fetchone()
        if old is None or old['type']!=kind:
            raise ValueError('Choose an active file of the same type to replace.')
    metadata, parsed, error = {}, [], ''
    try:
        metadata,parsed=bank_statement(content) if suffix=='.pdf' else invoices(content,suffix)
    except Exception as exc:
        error=str(exc) if isinstance(exc,ValueError) else 'The file could not be read. Check the format, encryption and contents.'
    with db:
        cur=db.execute('''INSERT INTO document (application_id,file_name,content,digest,type,processing_status,error,metadata,replaces_document_id,uploaded_at)
                          VALUES (?,?,?,?,?,?,?,?,?,?)''',
                       (app_id,Path(filename.replace('\\','/')).name,content,digest,kind,'failed' if error else 'processed',error,json.dumps(metadata),replaces,now()))
        doc_id=cur.lastrowid
        if replaces:
            db.execute('UPDATE document SET active=0 WHERE id=?',(replaces,))
        for r in parsed:
            db.execute('''INSERT INTO financial_record (document_id,type,record_date,amount,currency,direction,reference,counterparty,description,source_location)
                          VALUES (?,?,?,?,?,?,?,?,?,?)''',(doc_id,*[r[k] for k in ('type','record_date','amount','currency','direction','reference','counterparty','description','source_location')]))
        validate(db,app_id)
    return doc_id

def exclude(db, app_id, doc_id):
    editable(db,app_id)
    with db:
        db.execute('UPDATE document SET active=0 WHERE id=? AND application_id=?',(doc_id,app_id))
        validate(db,app_id)

def issues(db, app_id, history=False):
    return rows(db,'SELECT * FROM data_issue WHERE application_id=?'+('' if history else " AND status='open'")+' ORDER BY severity,id',(app_id,))

def validate(db, app_id):
    a=application(db,app_id)
    docs=documents(db,app_id)
    recs=records(db,app_id)
    db.execute("UPDATE data_issue SET status='resolved' WHERE application_id=?",(app_id,))
    def issue(key,message,action,severity='blocking',doc=None,record=None,account=None,gap=None):
        db.execute('''INSERT INTO data_issue (application_id,issue_key,document_id,record_id,account_reference,gap_period,severity,status,message,next_action)
                      VALUES (?,?,?,?,?,?,?,'open',?,?) ON CONFLICT(application_id,issue_key) DO UPDATE SET
                      status='open',message=excluded.message,next_action=excluded.next_action,severity=excluded.severity''',
                   (app_id,key,doc,record,account,gap,severity,message,action))
    for d in docs:
        if d['processing_status']!='processed':
            issue(f"file:{d['id']}",f"{d['file_name']}: {d['error']}",'Replace this file with a readable supported file, or exclude it.',doc=d['id'])
    inv=[r for r in recs if r['type']=='invoice']
    if not inv:
        issue('no-invoices','No readable invoices are included.','Upload the invoice spreadsheet.')
    seen={}
    for r in inv:
        if r['reference'] in seen:
            issue(f"duplicate:{r['id']}",f"Duplicate invoice {r['reference']} in {r['file_name']} ({r['source_location']}).",'Correct the spreadsheet or exclude the extra file.',doc=r['document_id'],record=r['id'])
        seen[r['reference']]=r['id']
        if not a['period_start']<=r['record_date']<=a['period_end']:
            issue(f"date:{r['id']}",f"Invoice {r['reference']} is outside the reporting year.",'Replace the file with invoices for the requested period.',doc=r['document_id'],record=r['id'])
    year=int(a['period_start'][:4])
    for month in range(1,13):
        key=f'{year}-{month:02}'
        if inv and not any(r['record_date'].startswith(key) for r in inv):
            issue('invoice-month:'+key,f'No invoices were found for {key}.','Upload the missing invoices or explain why there were no sales.','warning',gap=key)
    accounts=json.loads(a['required_accounts'])
    good={acct:[] for acct in accounts}
    for d in docs:
        if d['type']!='bank_statement' or d['processing_status']!='processed':
            continue
        m=json.loads(d['metadata'])
        reasons=[]
        if m['account_reference'] not in accounts: reasons.append('unexpected account')
        if m['holder'].casefold()!=a['business_name'].casefold(): reasons.append('different business name')
        if m['coverage_start']<a['period_start'] or m['coverage_end']>a['period_end']: reasons.append('outside the reporting period')
        if reasons:
            issue(f"statement:{d['id']}",f"{d['file_name']}: {', '.join(reasons)}.",'Replace or exclude this statement.',doc=d['id'])
        else:
            good[m['account_reference']].append((d,m))
    coverage=[]
    for account, statements in good.items():
        ordered=sorted(statements,key=lambda pair:pair[1]['coverage_start'])
        for i,(d,m) in enumerate(ordered):
            for previous,pm in ordered[:i]:
                if m['coverage_start']<=pm['coverage_end']:
                    issue(f"overlap:{previous['id']}:{d['id']}",f"Overlapping statements: {previous['file_name']} and {d['file_name']}.",'Exclude the duplicate or replace the incorrect statement.',doc=d['id'],account=account)
            if i:
                _,pm=ordered[i-1]
                if date.fromisoformat(pm['coverage_end'])+timedelta(days=1)==date.fromisoformat(m['coverage_start']) and pm['closing']!=m['opening']:
                    issue(f"balance:{d['id']}",f"Opening balance of {d['file_name']} differs from the previous closing balance.",'Check and replace the incorrect statement.',doc=d['id'],account=account)
        for month in range(1,13):
            start=date(year,month,1); end=date(year,month,calendar.monthrange(year,month)[1])
            days={start+timedelta(days=i) for i in range((end-start).days+1)}
            covered=set()
            for _,m in statements:
                s=max(start,date.fromisoformat(m['coverage_start'])); e=min(end,date.fromisoformat(m['coverage_end']))
                if e>=s: covered.update(s+timedelta(days=i) for i in range((e-s).days+1))
            complete=days.issubset(covered)
            key=f'{year}-{month:02}'
            coverage.append({'Account':account,'Month':key,'Coverage':'Complete' if complete else 'Missing or incomplete'})
            if not complete:
                issue(f'coverage:{account}:{key}',f'Statement coverage is missing or incomplete for {account}, {key}.','Upload a statement covering the missing dates.',account=account,gap=key)
    return coverage

def save_explanation(db,app_id,issue_id,text):
    editable(db,app_id)
    with db:
        db.execute('UPDATE data_issue SET applicant_explanation=?,explained_by=?,explained_at=? WHERE id=? AND application_id=?',
                   (text.strip(),'demo-applicant',now(),issue_id,app_id))

def submit(db,app_id):
    editable(db,app_id)
    with db:
        validate(db,app_id)
        remaining=[i for i in issues(db,app_id) if i['severity']=='blocking' or not i['applicant_explanation'].strip()]
        if remaining:
            raise ValueError('Resolve blocking issues and explain all warnings before submitting.')
        db.execute("UPDATE application SET status='submitted',submitted_at=? WHERE id=?",(now(),app_id))

def summary(db,app_id):
    return {'application':application(db,app_id),
            'documents':[{k:v for k,v in d.items() if k not in ('content','digest')} for d in documents(db,app_id)],
            'records':records(db,app_id),'issues':issues(db,app_id,history=True),
            'notice':'Demonstration review package. Suggestions are not confirmed payments. No real bank delivery or financing decision.'}

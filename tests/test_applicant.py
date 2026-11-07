import csv
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

import qawafel_store as s
from parsers import bank_statement

ROOT=Path(__file__).resolve().parents[1]
(ROOT/'tmp').mkdir(exist_ok=True)

class ApplicantTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'tmp')
        self.db=s.connect(Path(self.tmp.name)/'test.sqlite3')
        self.app=s.create_application(self.db,'Demo Noor Wholesale',2025,['DEMO-ACCOUNT-001'])

    def tearDown(self):
        self.db.close(); self.tmp.cleanup()

    def load(self,skip=None):
        p=ROOT/'data/invoices/sample_invoices_2025.xlsx'
        s.upload(self.db,self.app,p.name,p.read_bytes())
        for p in sorted((ROOT/'data/bank_statements').glob('*.pdf')):
            if p.name!=skip: s.upload(self.db,self.app,p.name,p.read_bytes())

    def test_complete_sample_and_persistence(self):
        self.load()
        self.assertEqual(s.issues(self.db,self.app),[])
        self.assertEqual(len(s.records(self.db,self.app)),83)
        self.assertEqual(len(s.documents(self.db,self.app)),13)
        s.submit(self.db,self.app)
        self.assertEqual(s.application(self.db,self.app)['status'],'submitted')
        self.assertEqual(len(s.summary(self.db,self.app)['records']),83)
        with self.assertRaises(ValueError): s.exclude(self.db,self.app,1)
        with self.assertRaises(ValueError): s.submit(self.db,self.app)
        other=s.connect(Path(self.tmp.name)/'test.sqlite3')
        self.assertEqual(s.application(other,self.app)['status'],'submitted')
        other.close()

    def test_missing_month_explanation_and_recovery(self):
        self.load('statement_2025-04.pdf')
        issue=s.issues(self.db,self.app)[0]
        self.assertEqual(issue['gap_period'],'2025-04')
        s.save_explanation(self.db,self.app,issue['id'],'I will request the missing statement.')
        with self.assertRaises(ValueError): s.submit(self.db,self.app)
        p=ROOT/'data/bank_statements/statement_2025-04.pdf'
        s.upload(self.db,self.app,p.name,p.read_bytes())
        self.assertEqual(s.issues(self.db,self.app),[])
        original=next(i for i in s.issues(self.db,self.app,True) if i['id']==issue['id'])
        self.assertEqual(original['status'],'resolved')
        self.assertEqual(original['applicant_explanation'],'I will request the missing statement.')

    def test_draft_deletion_is_scoped_and_submitted_requests_survive(self):
        self.load()
        s.submit(self.db, self.app)
        draft = s.create_application(self.db, 'Wrong name', 2025, ['DEMO-ACCOUNT-001'])
        path = ROOT/'data/bank_statements/statement_2025-01.pdf'
        invalid = s.upload(self.db, draft, 'broken.pdf', b'broken')
        s.upload(self.db, draft, path.name, path.read_bytes(), replaces=invalid)
        s.delete_draft(self.db, draft)
        self.assertFalse(s.documents(self.db, draft, active=False))
        self.assertFalse(s.issues(self.db, draft, history=True))
        self.assertIsNone(self.db.execute('SELECT id FROM application WHERE id=?', (draft,)).fetchone())
        with self.assertRaises(ValueError): s.delete_draft(self.db, self.app)
        self.assertEqual(len(s.records(self.db, self.app)), 83)
        self.assertFalse(self.db.execute('PRAGMA foreign_key_check').fetchall())

    def test_exact_duplicate_keeps_counts(self):
        p=ROOT/'data/bank_statements/statement_2025-03.pdf'
        s.upload(self.db,self.app,p.name,p.read_bytes())
        count=len(s.records(self.db,self.app))
        with self.assertRaises(ValueError): s.upload(self.db,self.app,'renamed.pdf',p.read_bytes())
        self.assertEqual(len(s.records(self.db,self.app)),count)

    def test_corrupt_file_replacement_keeps_history(self):
        bad=s.upload(self.db,self.app,'bad.pdf',b'not a PDF')
        issue=next(i for i in s.issues(self.db,self.app) if i['document_id']==bad)
        s.save_explanation(self.db,self.app,issue['id'],'Replacing unreadable file.')
        p=ROOT/'data/bank_statements/statement_2025-01.pdf'
        new=s.upload(self.db,self.app,p.name,p.read_bytes(),replaces=bad)
        self.assertNotEqual(new,bad)
        self.assertEqual(len(s.documents(self.db,self.app)),1)
        self.assertEqual(len(s.documents(self.db,self.app,False)),2)
        old_issue=next(i for i in s.issues(self.db,self.app,True) if i['id']==issue['id'])
        self.assertEqual(old_issue['applicant_explanation'],'Replacing unreadable file.')
        self.assertEqual(old_issue['status'],'resolved')

    def test_outside_period_exclusion(self):
        self.load()
        p=ROOT/'data/extra_period/statement_2026-01.pdf'
        extra=s.upload(self.db,self.app,p.name,p.read_bytes())
        self.assertTrue(any('outside the reporting period' in i['message'] for i in s.issues(self.db,self.app)))
        with self.assertRaises(ValueError): s.submit(self.db,self.app)
        s.exclude(self.db,self.app,extra)
        self.assertEqual(s.issues(self.db,self.app),[])

    def test_no_sales_warning_requires_explanation(self):
        self.load()
        invoice=next(d for d in s.documents(self.db,self.app) if d['type']=='invoices')
        with (ROOT/'data/invoices/sample_invoices_2025.csv').open(encoding='utf-8',newline='') as source:
            original=list(csv.DictReader(source))
        content=io.StringIO(); writer=csv.DictWriter(content,fieldnames=list(original[0])); writer.writeheader()
        writer.writerows(r for r in original if not r['invoice_date'].startswith('2025-06'))
        s.upload(self.db,self.app,'no_june.csv',content.getvalue().encode(),replaces=invoice['id'])
        warning=s.issues(self.db,self.app)[0]
        self.assertEqual(warning['severity'],'warning')
        with self.assertRaises(ValueError): s.submit(self.db,self.app)
        s.save_explanation(self.db,self.app,warning['id'],'No sales in June.')
        s.submit(self.db,self.app)

    def test_duplicate_invoice_in_alternative_format(self):
        for filename in ['sample_invoices_2025.xlsx','sample_invoices_2025.csv']:
            p=ROOT/'data/invoices'/filename; s.upload(self.db,self.app,p.name,p.read_bytes())
        self.assertEqual(len([i for i in s.issues(self.db,self.app) if i['issue_key'].startswith('duplicate:')]),24)

    def test_unknown_account_does_not_fill_required_coverage(self):
        a=s.create_application(self.db,'Demo Noor Wholesale',2025,['OTHER-ACCOUNT'])
        p=ROOT/'data/bank_statements/statement_2025-01.pdf'
        s.upload(self.db,a,p.name,p.read_bytes())
        found=s.issues(self.db,a)
        self.assertTrue(any('unexpected account' in i['message'] for i in found))
        self.assertEqual(len([i for i in found if i['issue_key'].startswith('coverage:')]),12)

    def test_other_business_is_flagged(self):
        a=s.create_application(self.db,'Another business',2025,['DEMO-ACCOUNT-001'])
        p=ROOT/'data/bank_statements/statement_2025-01.pdf'
        s.upload(self.db,a,p.name,p.read_bytes())
        self.assertTrue(any('different business' in i['message'] for i in s.issues(self.db,a)))

    def test_pdf_reader_matches_independent_reference(self):
        with (ROOT/'tests/expected_transactions.csv').open(encoding='utf-8',newline='') as f:
            expected=list(csv.DictReader(f))
        for filename in sorted({r['statement_file'] for r in expected}):
            _, actual=bank_statement((ROOT/filename).read_bytes())
            wanted=[r for r in expected if r['statement_file']==filename]
            self.assertEqual(len(actual),len(wanted))
            for record, row in zip(actual,wanted):
                self.assertEqual(record['record_date'],row['transaction_date'])
                self.assertEqual(record['reference'],row['payment_reference'])
                self.assertEqual(record['description'],row['description'])
                self.assertTrue(record['source_location'].endswith(row['transaction_id']))

class StreamlitTests(unittest.TestCase):
    def test_delete_from_manage_draft(self):
        from streamlit.testing.v1 import AppTest
        from unittest.mock import patch
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as tmp:
            path = Path(tmp)/'ui.sqlite3'
            with patch.dict(os.environ, {'QAWAFEL_DB': str(path)}):
                at = AppTest.from_file(str(ROOT/'app.py'), default_timeout=45).run()
                next(b for b in at.button if b.label == 'Create request').click().run()
                self.assertTrue(at.button(key='delete_draft_1').disabled)
                at.checkbox(key='confirm_delete_1').check().run()
                at.button(key='delete_draft_1').click().run()
                self.assertFalse(at.exception)
                self.assertEqual(at.selectbox(key='chosen_app').options, ['Create a new request'])
                db = s.connect(path)
                try:
                    self.assertEqual(s.rows(db, 'SELECT id FROM application'), [])
                finally:
                    db.close()

    def test_create_load_submit_ui(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as tmp:
            old=os.environ.get('QAWAFEL_DB')
            os.environ['QAWAFEL_DB']=str(Path(tmp)/'ui.sqlite3')
            try:
                at=AppTest.from_file(str(ROOT/'app.py'),default_timeout=45).run()
                self.assertFalse(at.exception)
                next(b for b in at.button if b.label=='Create request').click().run()
                self.assertFalse(at.exception)
                next(b for b in at.button if b.label=='Load sample files').click().run()
                self.assertFalse(at.exception)
                button=next(b for b in at.button if b.label=='Submit application')
                self.assertFalse(button.disabled)
                button.click().run()
                self.assertFalse(at.exception)
                self.assertTrue(any('Submitted locally' in e.value for e in at.success))
                self.assertEqual([t.label for t in at.tabs],['Applicant','Bank Review'])
                invoice=next(x for x in at.selectbox if x.label=='Inspect an invoice')
                self.assertEqual(len(invoice.options),24)
                invoice.select_index(6).run()
                self.assertFalse(at.exception)
                self.assertTrue(any('Uncertain: same customer and amount' in x.value for x in at.markdown))
            finally:
                if old is None: os.environ.pop('QAWAFEL_DB',None)
                else: os.environ['QAWAFEL_DB']=old

if __name__=='__main__': unittest.main()

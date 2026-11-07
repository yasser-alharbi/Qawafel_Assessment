from collections import Counter
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
import qawafel_store as s
from bank_review import review, suggest

ROOT=Path(__file__).resolve().parents[1]
(ROOT/'tmp').mkdir(exist_ok=True)

class BankReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tmp')
        self.db=s.connect(Path(self.temp.name)/'bank.sqlite3')
        self.app=s.create_application(self.db,'Demo Noor Wholesale',2025,['DEMO-ACCOUNT-001'])
        for p in [ROOT/'data/invoices/sample_invoices_2025.xlsx']+sorted((ROOT/'data/bank_statements').glob('*.pdf')):
            s.upload(self.db,self.app,p.name,p.read_bytes())

    def tearDown(self):
        self.db.close(); self.temp.cleanup()

    def test_requires_submission(self):
        with self.assertRaises(ValueError): review(self.db,self.app)

    def test_all_matching_cases_and_no_double_counting(self):
        s.submit(self.db,self.app)
        records,links,excluded,overview=review(self.db,self.app)
        statuses={o['Invoice']:o['Review status'] for o in overview}
        self.assertEqual(Counter(statuses.values()),{'Full amount suggested':19,'Partial amount suggested':1,'Needs review: uncertain match':2,'No matching payment identified':2})
        idx={r['id']:r for r in records}
        def for_invoice(n):return [l for l in links if idx[l['invoice_record_id']]['reference']==f'DEMO-2025-{n:03}']
        self.assertEqual(len(for_invoice(3)),2)
        self.assertEqual(sum(Decimal(l['suggested_amount']) for l in for_invoice(3)),Decimal('9660'))
        self.assertEqual(Decimal(for_invoice(5)[0]['suggested_amount']),Decimal('4000'))
        self.assertEqual(for_invoice(9)[0]['payment_record_id'],for_invoice(13)[0]['payment_record_id'])
        self.assertEqual(sum(Decimal(l['suggested_amount']) for l in for_invoice(9)+for_invoice(13)),Decimal('19665'))
        self.assertIsNone(for_invoice(7)[0]['suggested_amount'])
        self.assertIsNone(for_invoice(11)[0]['suggested_amount'])
        self.assertEqual(for_invoice(14),[]); self.assertEqual(for_invoice(24),[])
        self.assertEqual(len(excluded),2)
        self.assertTrue(all(l['payment_record_id'] not in [r['id'] for r in excluded] for l in links))
        review(self.db,self.app)
        self.assertEqual(self.db.execute('SELECT count(*) FROM payment_suggestion').fetchone()[0],len(links))

    def test_overpayment_is_unallocated(self):
        records=s.records(self.db,self.app)
        payment=next(r for r in records if r['type']=='bank_transaction' and r['reference']=='DEMO-2025-001')
        payment['amount']='99999'
        links,_=suggest(records)
        link=next(l for l in links if l['payment_record_id']==payment['id'])
        self.assertIsNone(link['suggested_amount'])

    def test_reference_boundary_and_date(self):
        records=s.records(self.db,self.app)
        payment=next(r for r in records if r['type']=='bank_transaction' and r['reference']=='DEMO-2025-001')
        payment['reference']='DEMO-2025-0010'
        links,_=suggest(records)
        self.assertFalse(any(l['payment_record_id']==payment['id'] for l in links))
        payment['reference']='DEMO-2025-001'; payment['record_date']='2024-12-31'
        links,_=suggest(records)
        self.assertFalse(any(l['payment_record_id']==payment['id'] for l in links))

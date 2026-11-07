"""Checks the fixture files, not the future application's behaviour."""
from pathlib import Path
from decimal import Decimal
import csv
import unittest
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]

class DatasetTests(unittest.TestCase):
    def test_invoice_period_and_ids(self):
        with (ROOT/'data/invoices/sample_invoices_2025.csv').open(newline='',encoding='utf-8') as f:
            rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),24)
        self.assertEqual(len({r['invoice_number'] for r in rows}),24)
        self.assertEqual({r['invoice_date'][:7] for r in rows},{f'2025-{m:02}' for m in range(1,13)})

    def test_statements_and_balances(self):
        with (ROOT/'tests/expected_transactions.csv').open(newline='',encoding='utf-8') as f:
            rows=list(csv.DictReader(f))
        self.assertEqual(len(list((ROOT/'data/bank_statements').glob('*.pdf'))),12)
        self.assertEqual(len({r['transaction_id'] for r in rows}),len(rows))
        balance=Decimal('40000')
        for r in rows:
            incoming,outgoing=Decimal(r['incoming']),Decimal(r['outgoing'])
            self.assertTrue((incoming>0) != (outgoing>0))
            balance+=incoming-outgoing
            self.assertEqual(balance,Decimal(r['balance']))
        for filename in sorted({r['statement_file'] for r in rows}):
            pdf=PdfReader(ROOT/filename)
            self.assertEqual(len(pdf.pages),1,filename)
            text=pdf.pages[0].extract_text()
            self.assertIn('SYNTHETIC TEST DATA',text)
            self.assertIn('DEMO-ACCOUNT-001',text)
            for r in [r for r in rows if r['statement_file']==filename]:
                self.assertIn(r['transaction_id'],text)
                self.assertIn(r['transaction_date'],text)
                for key in ('incoming','outgoing','balance'):
                    self.assertIn(f"{Decimal(r[key]):,.2f}",text)
                if r['payment_reference']:
                    for reference in r['payment_reference'].split(' + '):
                        self.assertIn(reference,text)

    def test_special_cases(self):
        with (ROOT/'tests/expected_transactions.csv').open(newline='',encoding='utf-8') as f:
            rows=list(csv.DictReader(f))
        def receipts(ref):
            return [Decimal(r['incoming']) for r in rows if ref in r['payment_reference']]
        self.assertEqual(receipts('DEMO-2025-001'),[Decimal('8280')])
        self.assertEqual(receipts('DEMO-2025-003'),[Decimal('4830'),Decimal('4830')])
        self.assertEqual(receipts('DEMO-2025-005'),[Decimal('4000')])
        self.assertEqual(receipts('DEMO-2025-009'),[Decimal('19665')])
        self.assertEqual(receipts('DEMO-2025-013'),[Decimal('19665')])
        self.assertEqual(receipts('DEMO-2025-014'),[])
        self.assertEqual(receipts('DEMO-2025-007'),[])
        self.assertEqual(receipts('DEMO-2025-011'),[])
        self.assertEqual(len([r for r in rows if not r['payment_reference'] and Decimal(r['incoming'])==Decimal('8640')]),1)
        payment=next(r for r in rows if r['payment_reference']=='DEMO-2025-024')
        self.assertEqual(payment['transaction_date'],'2026-01-12')
        self.assertIn('extra_period',payment['statement_file'])

if __name__=='__main__':
    unittest.main()

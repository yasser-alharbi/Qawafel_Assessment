# Sample invoice data

- All companies, customers, invoices and amounts are fictional.
- Fictional seller: Demo Noor Wholesale, a dry-grocery wholesaler selling to small shops.
- Reporting period: 2025-01-01 to 2025-12-31.
- 24 invoices: two per month. This is a deliberately small test fixture, not a realistic full annual transaction volume.
- Four repeat customers, varied order dates and amounts, and 30-day payment terms.
- Each row is one invoice total, not an invoice line item. Descriptions summarise the goods ordered.
- Currency: SAR. total_amount is the final invoiced amount to compare with payments; no tax breakdown is modelled. Do not label it net revenue or profit.
- Two different invoices deliberately have the same amount (DEMO-2025-007 and DEMO-2025-011: SAR 8,640). Amount equality alone must not confirm a match. Other repeated amounts may also occur.
- No paid/unpaid status or payment evidence is included. Due dates do not establish whether an invoice has been paid.
- Some December invoices fall due in January 2026, after the reporting period.
- The Excel and CSV files contain the same 24 invoices. They are alternative formats, not additional data to combine.
- The Excel sheet is Invoices, with headers on row 1 and records on rows 2-25. Preserve the source row when importing.
- Baseline: 24 unique invoice numbers, 12 months represented, no missing required values. Invoice totals sum to SAR 213,355.
- This baseline contains no deliberately broken rows. Later tests can use copies with missing fields or duplicates.
- Twelve monthly text-based PDF bank statements are included in bank_statements/. They cover the same January-December 2025 reporting period for DEMO-ACCOUNT-001.
- extra_period/statement_2026-01.pdf is an optional boundary test: it contains the payment for invoice DEMO-2025-024, received after year-end. Exclude it from the base 2025 upload.
- The statement opening balance starts at SAR 40,000. All monthly balances reconcile and carry forward. Rent, supplier payments, fees, a loan and an own-account transfer are included as illustrative non-invoice transactions.
- Missing-month testing: omit the April PDF during upload, then upload it to resolve the gap. Duplicate testing: attempt to upload the March PDF twice.
- Test expectations are in ../tests/test_cases.json. The reference transactions CSV is for verifying extraction only; the application must read the actual PDFs.
- No real bank, IBAN, tax identifier or customer data is used. These PDFs are deliberately labelled synthetic test data.

## Field mapping to FinancialRecord

| Source column | Model field |
| --- | --- |
| invoice_number | reference |
| invoice_date | record_date |
| customer_name | counterparty |
| description | description |
| total_amount | amount |
| currency | currency |

Set type to invoice. Store document_id and source_location during import. due_date is extra source context, retained in the spreadsheet; it does not require changing the agreed model now.

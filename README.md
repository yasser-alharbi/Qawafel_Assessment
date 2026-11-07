<div align="center">

# Qawafel Assessment

**A small SME financing-review prototype: check documents, then inspect payment evidence.**

Python · Streamlit · SQLite

</div>

---

## 📖 Overview

Two working tabs follow the two user stories:

- **Applicant:** upload invoices and bank statements, check coverage, fix files, explain warnings and submit locally.
- **Bank Review:** inspect each invoice and its suggested payments, view applicant explanations, open the original sources and download a review package.

This is a fictional-data demo. It does not approve financing, send documents to a real bank or implement the REST API proposed in the assessment. Both tabs represent user roles without authentication.

**[الشرح والتشغيل بالعربية](RUN_AR.md)**

## 🚀 Run

Use Python 3.11 or newer. Open this folder in Antigravity.

**Windows:** double-click `start.bat`. It prepares dependencies in a sibling folder called `.qawafel_runtime`, then starts the app. The first run needs internet access. Open **http://localhost:8501** and leave the terminal running.

Or run these commands from the project folder:

```powershell
python -m venv ..\.qawafel_runtime
..\.qawafel_runtime\Scripts\python.exe -m pip install -r requirements.txt
..\.qawafel_runtime\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

If needed, replace `python` in the first command with `py -3`. On macOS/Linux use `python3 -m venv ../.qawafel_runtime`, then `../.qawafel_runtime/bin/python` for the other commands. Stop the server with `Ctrl+C`.

## ✨ Try Both Stories

1. Create a request with **Demo Noor Wholesale**, **2025**, and **DEMO-ACCOUNT-001**.
2. Expand **Try the supplied sample files** and click **Load sample files** with **All 12 months** selected.
3. Review the coverage and files, then click **Submit application**.
4. Open **Bank Review**, select an invoice and inspect its possible payments and source documents.
5. Download the review ZIP containing the summary, suggestions, issues, explanations and original sources.

To test a problem, create another request and select **Leave April out**. Adding an explanation does not clear the missing-statement blocker. Upload April and recheck to resolve it. Original files and explanations remain in history after replacements.

## 📊 Data and Matching

The dataset has 24 invoices (two per month), 12 monthly 2025 statement PDFs and a separate January 2026 boundary test. All data is fictional.

Excel and CSV contain the same invoices; upload one format, not both. PDFs are the real app inputs. Files under `tests/` are expected answers for checking the code, not inputs used by the app.

| Evidence | Prototype behaviour |
|---|---|
| Exact invoice number in a payment reference | Suggest the payment for that invoice. |
| Several referenced payments for one invoice | Show each payment; classify the suggested sum as partial or full. |
| One reference names multiple invoices and the amount equals their sum | Allocate each invoice's amount without counting the payment twice. |
| Missing reference, same customer and same amount | Show an uncertain candidate without allocating money. |
| Reference amounts exceed an invoice, or a combined amount does not reconcile | Keep the evidence visible but leave the allocation unassigned. |
| Outgoing money, known loan or own-account transfer | Exclude from customer-payment suggestions. |
| No suitable evidence | Display “No matching payment identified.” |

Matches use the same currency and payments on/after the invoice date. All links are suggestions, not confirmed settlement. Keyword exclusions and name matching are intentionally simple; unfamiliar references and descriptions may need human review. No confidence score or credit threshold is invented.

**Examples:** invoice 003 has two SAR 4,830 receipts; invoice 005 has a SAR 4,000 partial receipt; invoices 009 and 013 share SAR 19,665; invoices 007 and 011 have an uncertain SAR 8,640 receipt. Invoice 024's payment is in the separate January 2026 file, outside the base period.

The default sample produces **19 full-amount suggestions, 1 partial, 2 uncertain and 2 invoices with no payment identified**. These labels describe the available evidence, not creditworthiness.

## 📂 Files

```text
Qawafel_Assessment/
├── app.py                # Applicant UI and two-tab entry point
├── bank_review.py        # Matching rules, bank UI and review package
├── parsers.py            # Actual Excel/CSV and PDF extraction
├── qawafel_store.py      # Five SQLite tables and validation
├── data/                 # Fictional invoices and bank statements
├── tests/                # Workflow, matching, extraction and UI tests
├── scripts/              # Optional statement regeneration
├── .streamlit/           # Display settings
├── requirements.txt
├── requirements-data.txt # Optional testing/generation dependencies
├── start.bat
├── RUN_AR.md
└── README.md
```

The app creates a small database under `local_data/`. Library installations are much larger than the project, so the runtime lives beside the repo. Do not upload the runtime, local databases, temporary files or ZIP archives to GitHub. `.gitignore` excludes generated files within the repo.

## 🧪 Checks

```powershell
..\.qawafel_runtime\Scripts\python.exe -m pip install -r requirements-data.txt
..\.qawafel_runtime\Scripts\python.exe -m unittest discover -s tests -v
```

Tests cover extraction, coverage, duplicate prevention, replacements, retained explanations, submission, persistence, payment cases and the complete two-tab UI flow. To regenerate statement PDFs: `python scripts/generate_bank_statements.py` after installing the optional dependencies. This overwrites the generated PDFs and test references.

## 🌐 GitHub and Browser Access

Upload the extracted project files to a GitHub repository. GitHub Pages cannot run this Python application.

For a browser demo, deploy the repository through [Streamlit Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app): choose the repository and branch, set the entry point to `app.py` (or its path if nested), and use Python 3.12. `requirements.txt` supplies the dependencies.

This demo has shared local storage and no login. A hosted demo must use fictional data only; visitors may see each other's demo requests, and local storage may be reset on restart/redeployment. This repository does not provision hosting or real bank credentials.

## 📝 Limits

- Calendar-year reporting, SAR, up to 10 MB per file, one invoice worksheet.
- Only the supplied text-based, one-page Demo Bank PDF layout. Scans and other bank layouts are flagged.
- Invoice totals are not profit. Tiny sample volumes and illustrative expenses are not full company accounts.
- Amounts use Decimal and decimal text storage. Sources, replaced files and issue explanations are retained; each issue stores its latest explanation rather than a complete edit audit trail.
- No real bank integration, authentication or automated financing decision.

## 🤖 AI Tools Used

Codex assisted with requirements, technical design, fictional data, both prototype tabs, documentation and tests.

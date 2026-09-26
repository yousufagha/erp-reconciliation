# erp-reconciliation

Reads a pile of supplier paperwork (purchase orders, goods received notes and delivery
dockets, invoices, credit notes, statements, remittances, price schedules) in whatever
format it arrives, and reports the status of the paperwork and the goods:

- **goods owed**: ordered, not yet delivered (PO to GRN)
- **paperwork owed**: received, not yet invoiced (GRN to invoice)
- **money owed**: invoiced, not yet paid (invoice to payment)

Built as a plain Python library with a command line, so it can sit inside the host CRM's
codebase whatever its stack. The model reads; deterministic code does every sum, match and
verdict.

## Status

| Step | What | State |
|---|---|---|
| 0 | Repo, test corpus, scoring harness | done |
| 1 | Intake, dedupe, profile, exact formats (UBL, XLSX, CSV, DOCX, email) | done |
| 2 | Text-layer PDFs, classification, per-type schemas and checks | done |
| 3 | Splitting and joining documents | done |
| 4 | Chain assembly and the three pendency registers | done |
| 5 | Model reading for scans and photos (Gemini free tier for testing) | next |
| 6 | Status report (`pile status <folder>`) | first version |

## Test corpus

- `corpus/public/invoice2data`: real invoices published with expected answers by the
  invoice2data project (MIT). Header fields only.
- `corpus/synthetic/scenario_aug2026`: one invented fabricator's August 2026 paperwork, 32
  files holding 34 documents in 12 formats, with seeded problems (price variance, short
  delivery, missing receipt, duplicate copies, an invoice with no PO, a statement listing an
  invoice that never arrived). All businesses and numbers are invented. Regenerate with
  `python corpus/synthetic/generate.py`. The generator never imports `pile`.
- The client's real sample pack, when it arrives. That is the gate; everything else is rehearsal.

## Use

```bash
pip install -e ".[dev]"
pytest
pile eval corpus/synthetic/scenario_aug2026 corpus/public/invoice2data --reader trivial
pile read path/to/folder -o found.json
pile status corpus/synthetic/scenario_aug2026   # goods owed, paperwork owed, money owed, exceptions
```

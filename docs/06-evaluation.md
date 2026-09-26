# Evaluation

## Corpora

| Corpus | What | Answers | Caveat |
|---|---|---|---|
| `corpus/public/invoice2data` | 13 real invoices (10 PDFs, 3 PNG renders) from AWS, Coolblue, Flipkart, OYO, a French ISP and others; English, Dutch, German, French | header fields as published by invoice2data (MIT) | answers are theirs; not Australian; few line answers |
| `corpus/synthetic/scenario_aug2026` | invented fabricator "Ridgeline Steel Fabrications", August 2026: 8 POs, 7 receipts, 8 invoices, 1 credit note, 3 statements, 3 remittances, 1 price schedule, 1 safety data sheet; 32 files, 34 documents, 12 formats | every field, line, link, pendency figure and exception, computed from the scenario, not read back from the files | written by the same hand as the code, so it confirms assumptions; the generator never imports `pile` to limit that |
| client's sample pack | not yet received | ground truth spreadsheet requested | **the real gate** |

Seeded problems in the synthetic pack: a 5% price rise with no PO amendment, a short delivery
billed in full then credited, an invoice with no receipt, an invoice with no PO number (should
be found by score), an invoice with no PO at all, one invoice arriving twice (in a supplier pack and as an emailed
copy), another arriving as a PDF and as a phone photo, a two-page invoice, page 2 of an invoice
sent as its own file, a scanner batch holding two dockets, a supplier statement listing an
invoice that never arrived, a part payment, and a document that is none of the eight types.

## What the harness measures

`pile eval <corpus>`:

- **documents found, document type**: aligned to truth by file and page overlap
- **header fields, line fields**: every reading, before the gate (how well the readers read)
- **files split correctly**: files whose document boundaries are exactly right (zero corrections)
- **gate**: of the values accepted as fact, how many are right and how many wrong; how many left
  blank rather than guessed; how many flagged for a person, and how many of those were right
- **reconciliation** (synthetic): invoice-to-PO links, and recall and precision on each
  register and on exceptions

Held documents' provisional values are never scored as accepted.

## Current numbers (26 Sep 2026, no model; `results/2026-09-26-no-guess.txt`)

| | Synthetic | Public |
|---|---|---|
| Header fields read correctly | 95.1% (212/223) | 59.0% (36/61) |
| Line fields read correctly | 85.1% (229/269) | 12.8% (12/94) |
| Values accepted as fact | 202, **0 wrong** | 9, **0 wrong** (5 left blank) |
| Flagged for confirmation | 0 | 4, all right |
| Files split correctly | 3/3 | n/a |
| Invoice to PO links | 9/9 (one by score) | n/a |
| Money owed, paperwork owed | 100% recall and precision | n/a |
| Goods owed | 100% recall, 40% precision | n/a |

Every goods-owed and missing-receipt error traces to three delivery records that exist only as
a phone photo or a scanned batch, which need the model path. `tests/test_step4_resolve.py`
proves this: fed a perfect reading, resolution reproduces every seeded figure exactly.

The public set's low coverage is honest: documents whose own arithmetic fails, or whose values
cannot be established, are held rather than guessed.

## Adding the client's pack

1. Put the files in `corpus/client/<pack-name>/` (never commit client files to a public repo;
   check the NDA before committing them at all).
2. Add `context.json`: the buyer (name, ABN) and the supplier list (name, ABN, aliases).
3. Add `truth.json` in the same shape as the synthetic one. The minimum useful truth is the
   four-column spreadsheet requested from the client (document, supplier, total, PO or job),
   converted; full field truth for 20 to 30 documents is enough to calibrate confidence.
4. `pile eval corpus/client/<pack-name> --json results/<date>-client.json`.
5. Fit the confidence weights and gate bands on it (`confidence.py`), then re-run both corpora.

Targets agreed in the plan: 95% header fields, 90% line items, and an honest measured number
for site-photographed dockets.

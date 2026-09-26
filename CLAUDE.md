# CLAUDE.md

Read this first. It is the briefing for any Claude instance (or person) picking up this repo.
Then read `docs/00-index.md` for the full documentation in order.

## What this is

A document reconciliation module for a CRM vendor whose customers are Australian fabrication
and building-materials companies. It reads a pile of supplier paperwork in any format and
reports, in the client's words, "the status of the paperwork and the real goods":

- **goods owed**: ordered, not yet received (PO to GRN)
- **paperwork owed**: received, not yet invoiced (GRN to invoice)
- **money owed**: invoiced, not yet paid (invoice to payment)

plus the exceptions a person must look at (price variance, quantity variance, no matching PO,
duplicate suspected, missing receipt, on a supplier statement but never received).

It is a plain Python library with a CLI (`pile`), built to drop into the client's codebase
once their stack is known. It is **not** a web app, a general ledger or a payment system.

Owner: Yousuf Agha (the consultant). The client is a CRM vendor; details in
`docs/03-client-context.md`.

## The rules that shape every change

1. **The model reads; it never decides.** Models turn pages into values. Every match, sum,
   link, confidence score, verdict and figure is deterministic code. Enforced by
   `tests/test_trust_boundary.py`. The brief's own grammar says the same: it writes "the AI"
   for reading and explaining, "the system" for tolerance and posting.
2. **No guessing.** A value is accepted as fact only with evidence: printed next to a label,
   matched to the CRM's supplier list, or (for model reads) found on the page by an
   independent OCR reading. Anything else is left blank, flagged for a person, or held.
   `tests/test_step2_pdf_and_checks.py::test_no_wrong_value_is_accepted_as_fact` holds the
   line: currently 0 wrong values accepted on either corpus.
3. **Never state inference about the client's customers as fact.** An earlier inference
   ("most of their customers never raise a PO") reached a client-facing document, was wrong,
   and cost credibility. Phrase anything about their customers' practices as a question.
   See `docs/05-decisions.md` D-00.
4. **Measure, don't assert.** Every step has a gate in the harness. Figures from the synthetic
   corpus are labelled synthetic: they were written by the same hand as the code. The client's
   real sample pack is the real gate.
5. **Free Gemini tier is for test documents only.** Google's free-tier terms use submitted
   content to improve its products. Never send client paperwork to it.

## House style (Yousuf's preferences)

UK English. No em dashes. Concise and direct. One committed recommendation, not a menu.
State cost (free / paid / trial / licence) before recommending a tool. Cite primary sources
(vendor docs, papers) for any fact that decides a choice; label anything unverified.
No duration estimates. Install and verify one tool at a time.

## Commands

```bash
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -e ".[dev]"            # add ,gemini for the model path
pytest -q                             # 43 tests; 6 skip without Tesseract
pile status corpus/synthetic/scenario_aug2026        # the report a person reads
pile eval corpus/synthetic/scenario_aug2026 corpus/public/invoice2data   # scores vs truth
pile read <folder> -o found.json      # raw per-document readings
python corpus/synthetic/generate.py   # regenerate the synthetic pack and its truth
```

`GEMINI_API_KEY` enables the model path for images and scans (`docs/02-model-testing.md`).
Tesseract (`brew install tesseract`, then `uv pip install -e ".[ocr]"`) enables grounding;
without it every model read is held.

## Map

```
src/pile/
  intake.py      files in; email unpacked into attachments and content-bearing bodies
  profile.py     what each file is: UBL, xlsx, csv, docx, text, PDF text pages vs image pages, image
  layout.py      one grid shape (rows of cells, with positions for PDFs) for every readable format
  pdf_text.py    PDF text layer to grid by word position; splits multi-document PDFs
  readers/ubl.py Peppol PINT A-NZ / UBL e-invoices, read as structure
  classify.py    document type from the printed title (8 types)
  labels.py      printed vocabulary mapped to field names (no templates, no positions)
  extract.py     header fields by label, line tables by column headings, parties by evidence
  segment.py     split files into documents and join continuations across files
  validate.py    per-type arithmetic and ATO tax-invoice rules
  dates.py       ambiguous dd/mm vs mm/dd dates flagged unless the document settles them
  model_read.py  the only file that calls a model (Gemini); page image to schema, values as printed
  ocr.py         Tesseract: independent reading for grounding and a second opinion
  image_read.py  model path assembly, grounding, confidence, gate question 3, provisional OCR labels
  confidence.py  six-signal per-field confidence (uncalibrated)
  pipeline.py    intake -> dedupe -> profile -> read -> classify -> extract -> join -> gate
  resolve.py     chains, three pendency registers, exceptions, statement corroboration
  report.py      the status report
  harness.py     scoring against truth.json, independent normalisers
corpus/public/invoice2data     13 real invoices with published answers (MIT)
corpus/synthetic/              invented fabricator "Ridgeline", Aug 2026; generator never imports pile
results/                       dated harness outputs; compare runs here
docs/                          everything else; start at docs/00-index.md
```

## State (26 Sep 2026)

Steps 0 to 5 built; step 6 (report) has a first version. The model path has never been run
live (the build environment could not reach Google). Current numbers and known gaps are in
`docs/06-evaluation.md` and `docs/07-open-questions.md`. **The plan of record is
`docs/10-next-phase.md`.**

## Before you change something

- Run `pytest -q` and `pile eval ...` before and after; commit the new `results/` file if
  numbers moved.
- New document types, fields or labels go in `models.py` / `labels.py`, not as special cases.
- A new model call must be added to `MAY_CALL_A_MODEL` in the boundary test, deliberately.
- Every threshold in `confidence.py` and `resolve.py` is a placeholder until fitted on the
  client's documents. Do not tune them to the synthetic corpus.

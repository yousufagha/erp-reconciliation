# Decisions

Each entry: the decision, why, and what would change it. Newest last. Evidence with sources is
in `01-research-approach.md`.

## D-00 Do not state inference about the client's customers as fact (14 Sep 2026)

An unticked checkbox ("the CRM has no supplier POs") became, over four documents, "most of your
customers never raise a PO", including an invented "half the base" figure, and reached a
client-facing one-pager. The brief said the opposite. The client corrected it ("purchase order
always created"). **Rule:** anything about the client's customers' practices is a question until
real documents or a customer conversation settle it.

## D-01 The model reads and explains; it never decides (9 Sep, kept)

Extraction and narration may use a model. Matching, tolerance, arithmetic, confidence, gating,
posting are deterministic. The brief's own wording splits the same way ("the AI" extracts and
explains; "the system" applies tolerance and posts). Enforced by `tests/test_trust_boundary.py`.
It also answers the auditor's question: no language model approved a payment.

## D-02 A library with a CLI, not an app (26 Sep)

The deliverable is a module inside the client's codebase and their stack is unknown. A plain
library drops into anything; a FastAPI/React app (the 9 Sep build) would be rewritten.
**Changes if:** the client's stack is known and a service boundary is wanted.

## D-03 Evaluation first (26 Sep)

The corpus and harness were built before any reader, and every step has a gate. Synthetic
figures are labelled as such: the same hand wrote the documents and the code.

## D-04 Dedupe before reading (14 Sep design, D1)

Reading is the expensive step and the same invoice arrives several times. Byte hashes first;
same type, supplier and number later.

## D-05 Split only on strong evidence (14 Sep design, D2)

A wrong split is silent and permanent; a wrong join fails the arithmetic loudly. The page
stream segmentation literature agrees the useful measure is files needing zero corrections,
not page-level F1.

## D-06 A schema and a check per document type (14 Sep design, D3)

A docket has no money; a statement has no goods. One invoice-shaped schema forces every type
through invoice assumptions.

## D-07 Exact formats never touch a model (14 Sep design, D4)

UBL, spreadsheets and Word files carry their own structure; a model would turn certainty into
probability.

## D-08 Born-digital PDFs use the text layer, with positions (11 Sep)

The text is already in the file, exactly and for free. Columns are recovered from word
positions because text extraction collapses the gaps that define them (a bug found by building).

## D-09 Grounding comes from an independent reading (11 Sep, reconfirmed 26 Sep)

Claude's structured outputs cannot be combined with citations (API returns 400), citations are
page-level, and scanned PDFs are not citable. So the model cannot point at its source while
returning schema-valid values. Tesseract reads the same page independently and every value is
looked for on it.

## D-10 Confidence from document-side signals, not the model's own (11 Sep, reconfirmed 26 Sep)

Logprob confidence scored 0.705 AUROC in ExtractConf; model-intrinsic confidence 0.74 to 0.84 in
ConfBench; fused document-side signals 0.928. Six signals: readability, grounding, agreement,
arithmetic, field prior, corroboration. Self-consistency (5 calls) was 0.744 at 5x cost: not
built. **All weights uncalibrated** until fitted on the client's documents.

## D-11 Free Gemini for testing, not for client documents (26 Sep)

Yousuf asked to start free. The free tier's terms use content to improve Google's products and
say not to submit confidential information, so it is limited to synthetic and public test
documents. A paid or self-hosted model is proposed for client paperwork, on measured evidence.
Local Qwen3-VL via Ollama was the alternative considered; Yousuf preferred cloud.

## D-12 No guessing (26 Sep)

Yousuf: "make sure there is no guess and just real reads". Implemented as evidence tiers per
field (see architecture section 4). The "first line on the page is the supplier" fallback was
removed; letterhead names are flagged; ambiguous numeric dates are flagged unless the document
settles them; every number a model returns for a line must be on the page. Measured: 0 wrong
values accepted as fact on both corpora. The cost is coverage: more is flagged or held.

## D-13 Bigger models via a cascade, not everywhere (26 Sep, recommended, not built)

A bigger model helps on photos, handwriting and messy layouts, and signals its own errors
better. It does not help born-digital files (no model is used) or page splitting (Haiku matched
Sonnet in DocSplit). So: cheap model first, escalate only pages the checks fail.

## D-14 The buyer and the supplier list are configuration (26 Sep)

The CRM knows its own company and (probably) its suppliers. `context.json` supplies them.
Matching a name against a known list is evidence; inferring it from layout is not.

## D-15 Payment is read from documents (14 Sep, client's answer)

"the payment data comes from other documents like invoices, receipts". Remittances are the
buyer's record of payment; supplier statements corroborate it and reveal documents never
received.

## Rejected

- **OCR then markdown then LLM:** 58 to 64% on line items in the research; OCR on a tilted photo
  misattributes quantities (seen on our own corpus).
- **Template OCR:** the thing the brief says to replace.
- **Fine-tuned layout models (LayoutLM, Donut):** worse than general models in the research,
  more maintenance.
- **Optical compression (DeepSeek-OCR):** at a readable 150 dpi a page image only becomes
  cheaper than its text above about 11,600 characters a page (computed 11 Sep); the densest
  document seen, a 60-row supplier statement, has 4,231. Recompute if a customer's paper is denser.
- **A separate OCR vendor (Textract, Document AI):** per-page charges for what the text layer
  gives free and the model path does better.

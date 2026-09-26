# How to build it: research and approach (26 Sep 2026)

Context: the earlier code (130 tests) lived in temporary cloud workspaces and is gone. The
design survives in the other project docs. This note records what fresh research says about
the best way to rebuild, and the approach committed to before the git project starts.

## The problem, stated as two problems

The client's mission: "work through all kinds of files and file types, process their numbers and
create resolution among the chaos of all these files and tell us accurately the status of the
paperwork and the real goods."

1. **Reading the pile.** Arbitrary files in, typed and checked documents out.
2. **Resolving the pile.** Documents assembled into PO → GRN → invoice → payment chains, with
   pendency (goods owed, paperwork owed, money owed) at each junction.

Every tool found in research does a slice of this. None found assembles an unsorted pile into
chains and reports three-level pendency from documents alone (absence claim: unverified, based on
the tools reviewed below).

| Tool | What it does | What it does not do |
|---|---|---|
| EzzyBills for Simpro (AU trades) | Reads PO number off the bill, matches to Simpro PO; single-line POs matched within 10%; unknown or closed PO → bill stored, no further processing; price mismatch → email | No chain assembly without a PO number; no statements; no pendency view |
| Dext supplier statements | Extracts invoice numbers, dates, amounts from a statement image; flags missing, duplicate, mismatched vs invoices held | Statement ↔ invoice only; no PO or GRN |
| SAP GR/IR reconciliation | Clears matched GR and IR postings; surfaces "GR Amount Surplus" and "IR Amount Surplus" | Works on postings already in the ERP, not on documents |

SAP's two surplus measures are the same idea as the client's pendency: GR surplus is
**paperwork owed** (received, not invoiced); IR surplus is an **invoice with no receipt** (the
brief's "Missing receipt" bucket). Useful language when the client benchmarks against SAP.

## Findings that change or confirm the design

**1. Grounding must come from an independent parse. Confirmed again.**
Claude's structured outputs are still incompatible with citations (400 error if both are set),
citations on PDFs are page-level only, and scanned PDFs are not citable at all. So the model
cannot point at where a number came from while also returning schema-valid JSON. The design's
answer stands: the model reads into a schema; a separate parse of the page supplies word
positions; every claimed value is located as an exact token on that parse.

**2. Model self-confidence is not good enough to route on.**
ConfBench (Aug 2026, 75 invoices, 1,346 degraded variants, 70,000+ field checks): best
model-intrinsic confidence AUROC 0.84 (Opus 4.6); Haiku 4.5 0.74. At a 30% review budget the
best model catches only 2.43x the errors random review would. Against ExtractConf's fused
multi-signal 0.928 (from our earlier research), this confirms the six-signal confidence engine
is worth building and logprobs or verbalised confidence are not.

**3. Splitting is the hard part of a pile; ordering is not.**
DocSplit (Feb 2026, Amazon, 13 document categories): boundary clustering scores vary 0.56 to 0.90
across models and are "the primary differentiator"; page ordering is above 0.97 for all. Haiku 4.5
(0.9051 to 0.9391 packet score) is level with Sonnet 4.5 (0.9113 to 0.9377), so the cheap model is
enough for boundary tie-breaks. The page stream segmentation literature warns that page-level F1
hides the real cost: one baseline scored 0.83 F1 but only 7.4% of streams needed no correction
(author's summary of arXiv 2408.11981). **Measure packets processed with zero corrections, not
page F1.** This backs design decision D2 (split only on strong evidence).

**4. Australian rules give free validation checks.**
ATO: a tax invoice must show that it is intended to be a tax invoice, seller identity, seller
ABN, issue date, items with quantity and price, GST (or "Total price includes GST" when GST is
exactly one eleventh), and the extent each sale is taxable. At $1,000 or more it must also show
the buyer's identity or ABN. Each is a deterministic check that needs no model and catches a
misread or a non-compliant supplier document.

**5. E-invoices are real but not the pile.**
Peppol PINT A-NZ has been the only supported exchange format since 15 May 2025. B2G is mandatory
for federal agencies (30% of invoices by 1 Jul 2026); B2B remains voluntary, the proposed B2B
mandate was not enforced. So the structured handler should target PINT A-NZ UBL, and PDFs and
photos stay the main case.

**6. There is no public dataset of linked PO/GRN/invoice/payment sets.**
None found. Public data covers single documents: invoice2data test set (MIT, 14 real invoices
with expected header JSON), DocILE (6.7k annotated real business documents, 55 field classes,
line items), FATURA (10k synthetic multi-layout invoice images; licence to check before use),
SROIE and CORD receipts, DocSplit packets (CC BY-NC-SA 4.0). Chain assembly and pendency can
only be tested on a synthetic scenario pack until the client's samples arrive.

## The committed approach

**Build a standalone Python library with a command-line entry point, not a web app.**
The target is a module inside the client's codebase and their stack is still unknown. A library
with thin adapters drops into whatever they run; a FastAPI/React app would be rewritten. The
earlier engines (matching, tolerance, allocation, trust boundary) port in as pure functions.

**Evaluation first.** The first thing in the repo is the test corpus and the scoring harness, so
every later step is measured rather than asserted. Three corpus layers:

1. Public real documents with published answers (invoice2data now; DocILE if access is granted).
2. A synthetic scenario pack: one fabrication company's month, with suppliers, POs, GRNs and
   dockets (including photographed ones), invoices in every format, a credit note, statements,
   remittances, duplicates, a multi-invoice scan, a split invoice, and seeded defects (price
   variance, short delivery, missing receipt, unpaid balance). Known answers for every field,
   every chain and every pendency figure.
3. The client's real pack. This is the gate. Figures from layers 1 and 2 are labelled as such.

**Build order, each step gated by the harness:**

| Step | Builds | Gate |
|---|---|---|
| 0 | Repo, corpus, harness | Harness scores a trivial reader and reports 0% honestly |
| 1 | Intake, dedupe, profile; exact formats (UBL PINT A-NZ, XLSX/CSV, DOCX, email) | Exact formats read 100% on the synthetic pack |
| 2 | Born-digital PDF text layer with positions; classify; per-type schemas and validators (8 types, ATO checks) | Headers and lines scored per type on public and synthetic |
| 3 | Split and join (boundary evidence, bias against splitting) | Packets with zero corrections, not page F1 |
| 4 | Chain assembly and the three pendency registers; five exception buckets | Every seeded chain and pendency figure exact |
| 5 | Model read path (schema-constrained, Haiku first), grounding via independent parse, six-signal confidence, gate | Selective automation curve on scans and photos |
| 6 | Status report the client can read: paperwork status and goods status | Readable by someone who has not seen the code |

**Grounding layer for scans:** Tesseract word boxes (Apache 2.0, already installable) as the
independent parse. Docling (MIT, reads PDF, DOCX, XLSX, email, images with OCR and table structure)
is the upgrade path if scan grounding underperforms on the client's pack; not the default,
because it pulls in a large model stack the client's codebase may not want.

## Cost

Everything in the build is free and open source. The only paid item is the model API for the
image path: Claude Haiku 4.5 at $1 / $5 per million tokens ($0.50 / $2.50 batched), roughly
$0.0048 per page batched or double that interactive (from earlier measurement). Testing the
model path on a 200-page corpus is about $2. Without a key, steps 0 to 4 and the text path
still run fully; scans and photos are held for a person.

## Sources

- Claude structured outputs: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- Claude citations: https://platform.claude.com/docs/en/build-with-claude/citations
- Claude pricing: https://platform.claude.com/docs/en/about-claude/pricing
- ConfBench, arXiv 2608.01792: https://arxiv.org/html/2608.01792
- DocSplit, arXiv 2602.15958: https://arxiv.org/html/2602.15958v1
- LLMs for Page Stream Segmentation, arXiv 2408.11981: https://arxiv.org/abs/2408.11981
- Author's summary of PSS history: https://hunterheidenreich.com/posts/history-of-page-stream-segmentation/
- ATO tax invoices: https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/gst/tax-invoices
- AU e-invoicing status, Sep 2026: https://www.vatupdate.com/2026/09/22/331691/
- SAP GR/IR reconciliation: https://learning.sap.com/courses/explaining-payables-management-period-end-closing-activities/describing-gr-ir-reconciliation-for-accounts-payable-closing_b1a87580-bf30-4060-af74-9563bec75e72
- Dext supplier statements: https://dext.com/en/business/products/supplier-statements-reconciliation
- EzzyBills for Simpro: https://www.ezzybills.com/user-guide/bills-data-automation-to-simpro/
- DocILE, arXiv 2302.05658: https://arxiv.org/abs/2302.05658
- FATURA, arXiv 2311.11856: https://arxiv.org/abs/2311.11856
- Docling: https://github.com/docling-project/docling
- invoice2data test set: https://github.com/invoice-x/invoice2data/tree/master/tests/compare

Not read: arXiv 2609.22620 (lower-cost LLM page stream segmentation), fetch was rate-limited.
Unverified: FATURA licence terms; DocILE access conditions.

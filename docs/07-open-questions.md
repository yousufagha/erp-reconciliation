# Open questions and gaps

In priority order. Questions for the client are phrased as questions (see D-00).

## For the client

1. **Which system is the PO raised in?** "The PO is done by the company we provide our CRM to"
   says who, not where. Decides whether POs arrive as documents (read by `pile`) or as data
   (imported). The code supports both; the answer decides the adapter.
2. **Does a credit note for goods never delivered close the PO line, or is the shortfall still
   owed?** The code reports the line as goods owed and marks it `credited_by`; the business
   rule is theirs to set.
3. **Their stack, schema and module pattern.** Framework, database, whether a background worker
   exists, how tenancy works, what a job record and a document attachment record hold. Blocks
   integration design.
4. **The sample pack.** 30 to 50 supplier invoices (the worst, not the tidiest), 15 to 20
   dockets as photographed on site, 5 statements from 5 different suppliers, 3 to 4 credit
   notes, 2 to 3 price files, and ground truth for 20 to 30 invoices. Resist redaction of
   prices: a redacted invoice cannot exercise the price or statement checks.
5. **Pendency as a live register, a periodic report, or both?**
6. **Is their supplier list in the CRM?** The no-guess rule leans on it for supplier names.
7. **Data residency.** If documents must stay in Australia, the model path needs an Australian
   region or a self-hosted model (dots.ocr, PaddleOCR-VL, Qwen3-VL); US-only inference does not
   answer it.
8. **Who may approve a cost, and who handles escalations** (ops, purchasing, finance)?

## Technical, in order

1. **First live model run** (Gemini free tier, on the Mac): `docs/02-model-testing.md`. The SDK
   call is checked against the SDK source but has never run against the API.
2. **Calibrate** confidence weights and gate bands on the client's pack. Every threshold is a
   placeholder.
3. **Text-layer second pass.** Model reads have an independent second opinion; text-layer reads
   have one pass, so their per-field confidence is not computed yet.
4. **Line items on unfamiliar layouts** (public corpus 12.8%). Multi-row lines, merged headings
   and non-English headings. The model path is the expected answer; measure it before adding
   vocabulary.
5. **Escalation cascade** (D-13): cheap model first, a stronger model only for pages the checks
   fail. Needs a paid provider behind the same `Reader` interface.
6. **Rebuild what the 9 Sep build had:** tolerance scoping (global, vendor, item, vendor+item,
   org ceiling, expiry), rule learning with blast-radius preview, plain-language exception
   narration (model-written, template fallback), audit trail, semantic SKU matching
   (dimensional signatures such as `310UB46` = `UB 310x46`), UoM conversion.
7. **Job coding** (invoice to job), price schedule variance checks, landed cost, posting adapter.
8. **Screens:** exception queue with bucket rail, exception card, pendency registers, dashboard.
9. **Soft duplicates:** same supplier, amount within 0.5%, date within 10 days, different number.

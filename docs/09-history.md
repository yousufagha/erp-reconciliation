# History

How the project got here. Kept because several mistakes are worth not repeating.

| Date (2026) | What happened |
|---|---|
| 28 to 31 Aug | Client supplies `AI Vendor Reconciliation.docx` (see `client/brief.md`). |
| 9 Sep | First build: FastAPI, Postgres, React vertical slice of the three-way match. 44 tests. Trust boundary test introduced. Two bugs found by running it: a PO number quoted by a different supplier was force-linked; an unanchored regex read "Imports" as PO "rts". |
| 10 Sep | Correction from Yousuf: the client is a **CRM vendor** whose customers are fabricators, not a DTC brand. Feasibility plan and architecture diagrams. Recommendation: sub-ledger posting into Xero/QBO, not a general ledger. |
| 11 Sep | Document reading research (sources in `01-research-approach.md`) and build: text layer, router, six-signal confidence, validators, dispatcher and cascade. Five then seven reader bugs found by building (legibility threshold tuned for prose; descriptions overflowing into quantity; **grounding matched numbers inside product codes**; silence scored as disagreement; readability penalising short invoices; table detection on collapsed whitespace; **the cascade accepting an empty reading**). AI-first realignment: the brief mandates LLM extraction. 130 tests. |
| 11 to 14 Sep | **The PO mistake.** An unticked checkbox became "most of your customers never raise a PO" in a client-facing document. Retracted; standing rule D-00. |
| 14 Sep | Client's WhatsApp correction (PO always created; four-stage chain; pendency) and answers to five questions (see `03-client-context.md`). Requirement ledger: 76 sub-clauses. Design: "Reading the Pile". |
| 26 Sep | The earlier code is found to have lived only in temporary cloud workspaces: gone. Rebuilt from the project notes as this library, evaluation first, steps 0 to 5, plus the no-guess hardening. Pushed to GitHub. |

## Lessons

- **Save code somewhere durable as it is written.** The first build was lost with its workspace.
- **Inference is not a finding.** Label it, or ask.
- **A check that can pass vacuously will.** An empty reading has no weak fields; it must be
  rejected explicitly.
- **A false grounding is worse than none.** Match whole tokens only.
- **Figures from fixtures you wrote confirm what you assumed.** Label them; get real documents.

"""Per-field confidence from signals that look at the document, not at the model.

Model self-confidence is not good enough to route on: ConfBench (arXiv 2608.01792)
measured AUROC 0.74 to 0.84 for model-intrinsic confidence on invoices, against
0.928 for fused document-side signals in ExtractConf (arXiv 2606.24420). So the
signals here are:

  readability  .22  how legible the page is (OCR word confidence)
  grounding    .30  the value is on the page as an exact token
  agreement    .18  an independent second reading gives the same value
  arithmetic   .12  the document's own sums hold
  prior        .08  how reliable this kind of field usually is
  corroboration .10 another document agrees (neutral at reading time)

Two hard caps: a value that is not on the page is capped at 0.35; a value
another document contradicts is capped at 0.45.

EVERY THRESHOLD HERE IS UNCALIBRATED. The weights and bands are placeholders
until they are fitted on the client's documents with known answers.
"""
from __future__ import annotations

W = {"readability": 0.22, "grounding": 0.30, "agreement": 0.18, "arithmetic": 0.12, "prior": 0.08,
     "corroboration": 0.10}
AUTO, REVIEW = 0.92, 0.75
PRIORS = {"date": 0.9, "due_date": 0.9, "total": 0.9, "subtotal": 0.9, "gst": 0.9, "closing_balance": 0.9,
          "doc_number": 0.85, "po_reference": 0.85, "original_invoice": 0.85, "supplier_abn": 0.9,
          "supplier_name": 0.7, "buyer_name": 0.7, "payment_terms": 0.6}
MATERIAL = {"doc_number", "date", "total", "po_reference", "original_invoice", "closing_balance"}


def tri(x: bool | None) -> float:
    return 0.5 if x is None else (1.0 if x else 0.0)


def field_confidence(field: str, *, readability: float | None, grounded: bool | None, agrees: bool | None,
                     arithmetic_ok: bool | None, contradicted: bool = False) -> float:
    s = (W["readability"] * (0.5 if readability is None else readability)
         + W["grounding"] * tri(grounded)
         + W["agreement"] * tri(agrees)
         + W["arithmetic"] * tri(arithmetic_ok)
         + W["prior"] * PRIORS.get(field, 0.8)
         + W["corroboration"] * 0.5)
    if grounded is False:
        s = min(s, 0.35)
    if contradicted:
        s = min(s, 0.45)
    return round(s, 3)


def band(score: float) -> str:
    return "auto" if score >= AUTO else "review" if score >= REVIEW else "held"

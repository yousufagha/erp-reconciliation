"""Document type from the label the supplier printed.

Most suppliers print what the document is (TAX INVOICE, DELIVERY DOCKET,
STATEMENT OF ACCOUNT). A deterministic pass reads that label for free. Order
matters: a credit note usually also says "tax", a docket often says "not a tax
invoice", and an invoice mentions the purchase order, so the specific titles
are tested before the generic ones, and titles near the top outrank words in
the body. A model is asked only when this pass finds nothing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .layout import Grid
from .models import DocType

# (type, pattern, strength). Strength 3: a title. 2: a strong phrase. 1: weak.
PATTERNS: list[tuple[DocType, re.Pattern, int]] = [
    (DocType.CREDIT_NOTE, re.compile(r"\b(tax\s+)?(credit|adjustment)\s+note\b", re.I), 3),
    (DocType.REMITTANCE, re.compile(r"\b(remittance|payment)\s+advice\b", re.I), 3),
    (DocType.STATEMENT, re.compile(r"\bstatement\s+of\s+account\b|\baccount\s+statement\b|^\s*statement\b", re.I), 3),
    (DocType.GOODS_RECEIPT, re.compile(r"\b(delivery\s+(docket|note)|goods\s+received(\s+note)?|packing\s+slip"
                                       r"|consignment\s+note|proof\s+of\s+delivery)\b", re.I), 3),
    (DocType.PURCHASE_ORDER, re.compile(r"^\s*purchase\s+order\b", re.I), 3),
    (DocType.PRICE_SCHEDULE, re.compile(r"\b(price\s+(schedule|list)|pricing\s+schedule|rate\s+card)\b", re.I), 3),
    (DocType.SUPPLIER_INVOICE, re.compile(r"\b(tax\s+invoice|invoice|facture|factuur|rechnung|bill|receipt)\b", re.I), 2),
]
NEGATIONS = re.compile(r"\bnot\s+a\s+(tax\s+)?invoice\b|\bquote\s+the\s+invoice\b|\bcopy\s+of\s+invoice\b"
                       r"|\binvoice\s+(no|number|date|#)|\bpurchase\s+order\s+(no|number)", re.I)


@dataclass
class Classification:
    doc_type: DocType
    confidence: float
    evidence: str


def classify(grid: Grid, top_rows: int = 25) -> Classification:
    best: tuple[float, DocType, str] | None = None
    rows = [r for r in grid.rows if not r.is_blank]
    for i, row in enumerate(rows[:60]):
        for cell in row.texts:
            if not cell:
                continue
            probe = NEGATIONS.sub(" ", cell)
            for dt, pat, strength in PATTERNS:
                m = pat.search(probe)
                if not m:
                    continue
                if re.match(r"\s*(no|number|#|ref|date)?\s*[:#]\s*\S", probe[m.end():], re.I):
                    continue                                  # "Purchase Order: PO-4105" is a field, not a title
                short = len(cell) <= 40                       # a title stands alone
                position = 1.0 if i < top_rows else 0.4
                score = strength * position * (1.5 if short else 1.0) - i * 0.01
                if best is None or score > best[0]:
                    best = (score, dt, cell.strip()[:60])
    if best is None:
        return Classification(DocType.UNKNOWN, 0.0, "no printed document label")
    score, dt, ev = best
    conf = 0.95 if score >= 4 else 0.8 if score >= 2.5 else 0.55
    return Classification(dt, conf, ev)

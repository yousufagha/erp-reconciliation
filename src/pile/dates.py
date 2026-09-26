"""Dates that could be read two ways.

03/04/2026 is 3 April in Australia and 4 March in the United States. The reader
parses day-first, the Australian convention. That is a convention, not evidence,
so a date is accepted as read only when something on the document settles it:
  - it cannot be month-first (first number above 12), or
  - another date on the same document is unambiguous and shows the order, or
  - the document is Australian (a valid ABN appears on it), where day-first is the norm.
Otherwise the date is flagged for a person.
"""
from __future__ import annotations

import re

from .normalise import abn_valid, find_abns

NUMERIC = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})\b")
DATE_FIELDS = ("date", "due_date", "delivery_date", "effective_from", "effective_to")


def order_evidence(text: str) -> str | None:
    """'dayfirst' or 'monthfirst' if some numeric date in the text proves it."""
    for a, b, _ in NUMERIC.findall(text or ""):
        a, b = int(a), int(b)
        if a > 12 >= b:
            return "dayfirst"
        if b > 12 >= a:
            return "monthfirst"
    return None


def ambiguous_dates(doc, ctx) -> list[tuple[str, str]]:
    out = []
    # an ABN anywhere on it (supplier's or buyer's) makes it an Australian document
    australian = abn_valid(str(doc.value("supplier_abn") or "")) or bool(find_abns(doc.raw_text))
    proven = order_evidence(doc.raw_text)
    for k in DATE_FIELDS:
        fv = doc.fields.get(k)
        if fv is None or not fv.printed:
            continue
        m = NUMERIC.search(fv.printed)
        if not m:
            continue
        a, b = int(m[1]), int(m[2])
        if a == b or a > 12 or b > 12:
            continue
        if proven == "dayfirst" or australian:
            continue
        if proven == "monthfirst":
            y = int(m[3]) + (2000 if int(m[3]) < 100 else 0)
            fv.value = f"{y:04d}-{a:02d}-{b:02d}"
            continue
        out.append((k, f"{k} printed as {fv.printed!r} could be {b}/{a} or {a}/{b}; nothing on the document "
                       "settles the order"))
    return out

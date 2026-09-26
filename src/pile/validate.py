"""Each document type's own arithmetic, plus the ATO's tax invoice rules.

Checks never correct anything; they report. Two kinds, kept apart because they
mean different things downstream:
  arithmetic  the document disagrees with itself: we probably read it wrongly
              (or the supplier made an error). Blocks straight-through.
  compliance  the document reads fine but lacks something the ATO requires on a
              tax invoice. A supplier problem, not a reading problem.
ATO rules: https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/gst/tax-invoices
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .models import DocType, ReadDocument
from .normalise import abn_valid

CENT = 0.011           # rounding tolerance on a single amount
GST_RATE = 0.10


@dataclass
class Check:
    name: str
    kind: str          # arithmetic | compliance | presence
    passed: bool
    detail: str = ""

    def to_json(self) -> dict:
        return asdict(self)


def _close(a: float, b: float, tol: float = CENT) -> bool:
    return abs(a - b) <= tol


def _money_lines(doc: ReadDocument) -> list[Check]:
    out = []
    bad = []
    for i, l in enumerate(doc.lines, 1):
        q, p, a = l.get("quantity"), l.get("unit_price"), l.get("amount")
        if None in (q, p, a):
            continue
        # a tolerance of half a cent per unit covers suppliers who round the unit price
        if not _close(round(q * p, 2), a, max(CENT, abs(q) * 0.005 + CENT)):
            bad.append(f"line {i}: {q} x {p} = {round(q * p, 2)}, printed {a}")
    if any(None not in (l.get("quantity"), l.get("unit_price"), l.get("amount")) for l in doc.lines):
        out.append(Check("lines multiply out", "arithmetic", not bad, "; ".join(bad)))
    return out


def _totals(doc: ReadDocument, gst_expected: bool = True) -> list[Check]:
    out = []
    sub, gst, tot = doc.value("subtotal"), doc.value("gst"), doc.value("total")
    amounts = [l["amount"] for l in doc.lines if l.get("amount") is not None]
    if sub is not None and amounts:
        s = round(sum(amounts), 2)
        out.append(Check("lines sum to subtotal", "arithmetic", _close(s, sub), f"lines {s}, subtotal {sub}"))
    elif tot is not None and amounts and gst is None and sub is None:
        s = round(sum(amounts), 2)
        out.append(Check("lines sum to total", "arithmetic", _close(s, tot) or _close(s * 1.1, tot, 0.02),
                         f"lines {s}, total {tot}"))
    if sub is not None and gst is not None and tot is not None:
        out.append(Check("subtotal plus GST equals total", "arithmetic", _close(sub + gst, tot),
                         f"{sub} + {gst} = {round(sub + gst, 2)}, printed {tot}"))
    if gst_expected and sub is not None and gst is not None and gst != 0:
        out.append(Check("GST is 10% of subtotal", "arithmetic", _close(sub * GST_RATE, gst, 0.02 + 0.005 * len(doc.lines)),
                         f"10% of {sub} is {round(sub * GST_RATE, 2)}, printed {gst}"))
    if tot is None:
        out.append(Check("total present", "presence", False, "no total found"))
    return out


def _ato(doc: ReadDocument, printed_label: str) -> list[Check]:
    """ATO: what a tax invoice must show. Checked only for Australian documents."""
    out = []
    abn = doc.value("supplier_abn")
    out.append(Check("seller ABN shown and valid", "compliance", bool(abn) and abn_valid(abn),
                     f"ABN {abn!r}" if abn else "no ABN found"))
    out.append(Check("marked as a tax invoice", "compliance", "tax" in printed_label.lower() or doc.reader == "ubl",
                     f"printed title {printed_label!r}"))
    out.append(Check("date of issue shown", "compliance", doc.value("date") is not None))
    tot = doc.value("total")
    if tot is not None and tot >= 1000:
        out.append(Check("buyer identified (sales of $1,000 or more)", "compliance",
                         bool(doc.value("buyer_name")), "no buyer name or ABN found" if not doc.value("buyer_name") else ""))
    return out


def check(doc: ReadDocument, printed_label: str = "", australian: bool = True) -> list[Check]:
    t = doc.doc_type
    out: list[Check] = []
    if t in (DocType.SUPPLIER_INVOICE, DocType.CREDIT_NOTE):
        out += _money_lines(doc) + _totals(doc, gst_expected=australian)
        if australian and t == DocType.SUPPLIER_INVOICE:
            out += _ato(doc, printed_label)
        if t == DocType.CREDIT_NOTE:
            out.append(Check("names the invoice it credits", "presence", bool(doc.value("original_invoice"))))
    elif t == DocType.PURCHASE_ORDER:
        out += _money_lines(doc) + _totals(doc, gst_expected=australian)
    elif t == DocType.GOODS_RECEIPT:
        out.append(Check("quantities present", "presence",
                         bool(doc.lines) and all(l.get("quantity") is not None for l in doc.lines)))
        out.append(Check("quotes a purchase order", "presence", bool(doc.value("po_reference"))))
    elif t == DocType.STATEMENT:
        close = doc.value("closing_balance")
        entries = [l["amount"] for l in doc.lines if l.get("amount") is not None]
        if close is not None and entries:
            s = round((doc.value("opening_balance") or 0) + sum(entries), 2)
            out.append(Check("entries sum to closing balance", "arithmetic", _close(s, close),
                             f"opening + entries = {s}, closing {close}"))
        else:
            out.append(Check("closing balance and entries present", "presence", False))
    elif t == DocType.REMITTANCE:
        tot = doc.value("total")
        amounts = [l["amount"] for l in doc.lines if l.get("amount") is not None]
        if tot is not None and amounts:
            out.append(Check("payments sum to amount remitted", "arithmetic", _close(sum(amounts), tot),
                             f"lines {round(sum(amounts), 2)}, total {tot}"))
        else:
            out.append(Check("amount and allocations present", "presence", False))
    elif t == DocType.PRICE_SCHEDULE:
        f, to = doc.value("effective_from"), doc.value("effective_to")
        out.append(Check("effective dates in order", "presence", bool(f) and (not to or f <= to), f"{f} to {to}"))
        out.append(Check("prices present", "presence", bool(doc.lines) and all("unit_price" in l for l in doc.lines)))
    return out

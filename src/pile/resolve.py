"""Step 4: resolution among the chaos.

Takes every document read from the pile, in whatever order it arrived, and
assembles chains: purchase order -> goods received -> invoice (less credits)
-> payment. From the chains come the client's three pendencies:

  goods owed       ordered, not yet received          (PO -> GRN)
  paperwork owed   received, not yet invoiced         (GRN -> invoice)
  money owed       invoiced, not yet paid             (invoice -> payment)

plus the exceptions a person needs to look at, bucketed as the brief asks.
Everything here is deterministic. No model decides a link, a figure or a verdict.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from .labels import LEGAL_ENTITY
from .models import DocType, ReadDocument

PRICE_TOLERANCE = 0.02        # the brief's example: auto-approve under 2% price variance
QTY_EPS = 1e-6
LINK_AUTO, LINK_LOW = 0.85, 0.60
WEIGHTS = {"supplier": 0.35, "amount": 0.25, "date": 0.15, "lines": 0.25}


# ------------------------------------------------------------------ identities
def supplier_key(doc: ReadDocument) -> str:
    abn = re.sub(r"\D", "", str(doc.value("supplier_abn") or ""))
    name = str(doc.value("supplier_name") or "")
    return _name_key(name) or abn


def _name_key(name: str) -> str:
    n = LEGAL_ENTITY.sub(" ", name.casefold())
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    return " ".join(n.split())


def _num(s: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


def _sku(s: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


def _words(s: Any) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(s or "").casefold()))


def line_matches(line: dict, po_line: dict) -> float:
    """How sure we are that an invoice or docket line is this PO line (0..1)."""
    a, b = _sku(line.get("sku")), _sku(po_line.get("sku"))
    if a and b:
        return 1.0 if a == b else 0.0
    if b and b in _sku(line.get("description")):
        return 0.95                       # code printed inside the description
    wa, wb = _words(line.get("description")), _words(po_line.get("description"))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _d(s: str | None) -> date | None:
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


# ------------------------------------------------------------------ records
@dataclass
class POLine:
    po: str
    sku: str
    description: str
    ordered: float
    price: float
    received: float = 0.0
    invoiced: float = 0.0
    credited: float = 0.0
    receipts: list[str] = field(default_factory=list)
    invoices: list[str] = field(default_factory=list)
    credits: list[str] = field(default_factory=list)


@dataclass
class Exception_:
    bucket: str
    document: str
    headline: str
    suggested: str
    impact: float = 0.0
    po: str | None = None
    sku: str | None = None
    evidence: dict = field(default_factory=dict)
    resolved_by: str | None = None


@dataclass
class Resolution:
    po_lines: list[POLine]
    invoice_to_po: dict[str, str | None]
    link_scores: dict[str, float]
    goods_owed: list[dict]
    paperwork_owed: list[dict]
    invoiced_not_received: list[dict]
    money_owed: list[dict]
    exceptions: list[Exception_]
    unread: list[dict]
    corroboration: list[dict]

    def to_json(self) -> dict:
        return {
            "invoice_to_po": self.invoice_to_po, "link_scores": self.link_scores,
            "goods_owed": self.goods_owed, "paperwork_owed": self.paperwork_owed,
            "invoiced_not_received": self.invoiced_not_received, "money_owed": self.money_owed,
            "exceptions": [asdict(e) for e in self.exceptions], "unread": self.unread,
            "corroboration": self.corroboration,
        }


# ------------------------------------------------------------------ main
def resolve(docs: list[ReadDocument]) -> Resolution:
    unread = [{"source": d.sources[0].file, "status": d.status, "why": (d.notes or [""])[-1]}
              for d in docs if d.status not in ("read",) and d.status != "duplicate"]
    read = [d for d in docs if d.status == "read"]
    exceptions: list[Exception_] = []

    # one record per business document; copies noted, not double counted
    canonical: dict[tuple, ReadDocument] = {}
    copies: dict[tuple, list[str]] = defaultdict(list)
    for d in read:
        key = (d.doc_type, supplier_key(d), _num(d.value("doc_number")))
        if not key[2]:
            key = key + (d.sources[0].file,)
        if key in canonical:
            copies[key].append(d.sources[0].file)
        else:
            canonical[key] = d
    for key, extra in copies.items():
        d = canonical[key]
        exceptions.append(Exception_(
            "duplicate_suspected", str(d.value("doc_number")),
            f"{d.doc_type.value.replace('_', ' ').capitalize()} {d.value('doc_number')} arrived {len(extra) + 1} times "
            f"({', '.join([d.sources[0].file] + extra)}).",
            "Keep one; make sure it is entered and paid once.", impact=float(d.value("total") or 0),
            evidence={"copies": [d.sources[0].file] + extra}))
    docs_ = list(canonical.values())
    by_type = defaultdict(list)
    for d in docs_:
        by_type[d.doc_type].append(d)

    # purchase orders are the spine
    po_lines: dict[str, list[POLine]] = {}
    po_docs: dict[str, ReadDocument] = {}
    for po in by_type[DocType.PURCHASE_ORDER]:
        num = str(po.value("doc_number"))
        po_docs[_num(num)] = po
        po_lines[_num(num)] = [POLine(num, l.get("sku", ""), l.get("description", ""), l.get("quantity") or 0,
                                      l.get("unit_price") or 0) for l in po.lines]

    def best_po_line(po_key: str, line: dict) -> POLine | None:
        scored = [(line_matches(line, {"sku": pl.sku, "description": pl.description}), pl)
                  for pl in po_lines.get(po_key, [])]
        scored = [s for s in scored if s[0] >= 0.6]
        return max(scored, key=lambda s: s[0])[1] if scored else None

    def link(d: ReadDocument) -> tuple[str | None, float]:
        """Which PO a receipt or invoice belongs to, with a score a person can audit."""
        stated = _num(d.value("po_reference"))
        if stated in po_docs:
            same_supplier = _supplier_score(d, po_docs[stated]) >= 0.5
            if same_supplier:
                return stated, 1.0
            # a PO number quoted by a different supplier is not taken on trust (regression: 9 Sep build)
        best, best_s = None, 0.0
        for key, po in po_docs.items():
            s = _candidate_score(d, po, po_lines[key])
            if s > best_s:
                best, best_s = key, s
        return (best, best_s) if best_s >= LINK_LOW else (None, best_s)

    # receipts
    for r in by_type[DocType.GOODS_RECEIPT]:
        key, _ = link(r)
        if key is None:
            exceptions.append(Exception_("no_matching_po", str(r.value("doc_number")),
                                         f"Delivery {r.value('doc_number')} from {r.value('supplier_name')} matches no purchase order.",
                                         "Find the order this delivery belongs to."))
            continue
        for l in r.lines:
            pl = best_po_line(key, l)
            if pl:
                pl.received = round(pl.received + (l.get("quantity") or 0), 6)
                pl.receipts.append(str(r.value("doc_number")))

    # invoices and credit notes
    invoice_to_po: dict[str, str | None] = {}
    link_scores: dict[str, float] = {}
    invoices = {_num(i.value("doc_number")): i for i in by_type[DocType.SUPPLIER_INVOICE]}
    for inv in by_type[DocType.SUPPLIER_INVOICE]:
        num = str(inv.value("doc_number"))
        key, score = link(inv)
        invoice_to_po[num] = po_docs[key].value("doc_number") if key else None
        link_scores[num] = round(score, 3)
        if key is None:
            exceptions.append(Exception_(
                "no_matching_po", num,
                f"Invoice {num} from {inv.value('supplier_name')} for {_money(inv.value('total'))} quotes no purchase order "
                f"and none matches (best candidate scored {score:.2f}).",
                "Confirm who ordered this, raise or attach a PO, or dispute it.", impact=float(inv.value("total") or 0)))
            continue
        if not _num(inv.value("po_reference")):
            inv.notes.append(f"linked to {invoice_to_po[num]} by match score {score:.2f}; the invoice quotes no PO")
        for l in inv.lines:
            pl = best_po_line(key, l)
            if pl is None:
                continue
            pl.invoiced = round(pl.invoiced + (l.get("quantity") or 0), 6)
            pl.invoices.append(num)
            price = l.get("unit_price")
            if price is not None and pl.price and abs(price - pl.price) / pl.price > PRICE_TOLERANCE:
                pct = (price - pl.price) / pl.price * 100
                impact = round((price - pl.price) * (l.get("quantity") or 0), 2)
                exceptions.append(Exception_(
                    "price_variance", num,
                    f"{inv.value('supplier_name')} billed {pl.description or pl.sku} at {_money(price)} against "
                    f"{_money(pl.price)} on {pl.po} ({pct:+.1f}%), {l.get('quantity'):g} units, {_money(impact)}.",
                    "Approve if this is an agreed price change; otherwise dispute with the supplier.",
                    impact=impact, po=pl.po, sku=pl.sku, evidence={"po_price": pl.price, "billed_price": price}))
    for cn in by_type[DocType.CREDIT_NOTE]:
        orig = _num(cn.value("original_invoice"))
        target = invoices.get(orig)
        key = None
        if target is not None:
            po_num = invoice_to_po.get(str(target.value("doc_number")))
            key = _num(po_num) if po_num else None
        if key is None:
            key, _ = link(cn)
        num = str(cn.value("doc_number"))
        invoice_to_po[num] = po_docs[key].value("doc_number") if key else None
        if key:
            for l in cn.lines:
                pl = best_po_line(key, l)
                if pl:
                    pl.credited = round(pl.credited + (l.get("quantity") or 0), 6)
                    pl.credits.append(num)

    # quantity checks, per PO line, once everything is in
    for key, lines in po_lines.items():
        for pl in lines:
            net = pl.invoiced - pl.credited
            if pl.invoiced > QTY_EPS and pl.received <= QTY_EPS:
                for inv_num in dict.fromkeys(pl.invoices):
                    if not any(e.bucket == "missing_receipt" and e.document == inv_num for e in exceptions):
                        inv = invoices[_num(inv_num)]
                        exceptions.append(Exception_(
                            "missing_receipt", inv_num,
                            f"Invoice {inv_num} bills goods on {pl.po} but no delivery has been recorded against it.",
                            "Check whether the goods arrived; hold payment until a GRN or docket is on file.",
                            impact=float(inv.value("total") or 0), po=pl.po))
            elif pl.invoiced - pl.received > QTY_EPS:
                over = pl.invoiced - pl.received
                e = Exception_(
                    "quantity_variance", pl.invoices[-1],
                    f"Billed {pl.invoiced:g} of {pl.description or pl.sku} on {pl.po} but received {pl.received:g}: "
                    f"{over:g} billed and not delivered, {_money(over * pl.price)}.",
                    "Ask for a credit for the shortfall, or confirm the balance is still coming.",
                    impact=round(over * pl.price, 2), po=pl.po, sku=pl.sku)
                if net - pl.received <= QTY_EPS and pl.credits:
                    e.resolved_by = ", ".join(pl.credits)
                    e.headline += f" Credited by {e.resolved_by}."
                exceptions.append(e)

    # payments: remittances are our record; statements are the supplier's and corroborate it
    paid: dict[str, float] = defaultdict(float)
    for ra in by_type[DocType.REMITTANCE]:
        for l in ra.lines:
            paid[_num(l.get("reference"))] += l.get("amount") or 0
    credited_value: dict[str, float] = defaultdict(float)
    for cn in by_type[DocType.CREDIT_NOTE]:
        credited_value[_num(cn.value("original_invoice"))] += cn.value("total") or 0

    corroboration = []
    held_numbers = {_num(d.value("doc_number")) for d in docs_ if d.value("doc_number")}
    for st in by_type[DocType.STATEMENT]:
        listed = {_num(l.get("reference")): l for l in st.lines}
        supplier = supplier_key(st)
        missing = [ref for ref, l in listed.items() if ref not in held_numbers and (l.get("amount") or 0) > 0]
        for ref in missing:
            l = listed[ref]
            exceptions.append(Exception_(
                "missing_document", l.get("reference"),
                f"{st.value('supplier_name')}'s statement lists {l.get('reference')} for {_money(l.get('amount'))}, "
                f"which has not been received.",
                "Request a copy before paying the statement balance.", impact=float(l.get("amount") or 0)))
        ours = [i for i in docs_ if i.doc_type in (DocType.SUPPLIER_INVOICE, DocType.CREDIT_NOTE)
                and supplier_key(i) == supplier and (i.value("date") or "") <= (st.value("date") or "9999")]
        agreed = [str(i.value("doc_number")) for i in ours if _num(i.value("doc_number")) in listed]
        not_listed = [str(i.value("doc_number")) for i in ours if _num(i.value("doc_number")) not in listed]
        corroboration.append({"statement": st.sources[0].file, "supplier": st.value("supplier_name"),
                              "date": st.value("date"), "closing_balance": st.value("closing_balance"),
                              "invoices_agreed": agreed, "ours_not_on_statement": not_listed,
                              "on_statement_not_received": [listed[r].get("reference") for r in missing]})

    # the three registers
    goods_owed, paperwork_owed, invoiced_not_received = [], [], []
    for key, lines in po_lines.items():
        for pl in lines:
            net = round(pl.invoiced - pl.credited, 6)
            if pl.ordered - pl.received > QTY_EPS:
                e = {"po": pl.po, "sku": pl.sku, "description": pl.description, "ordered": pl.ordered,
                     "received": pl.received, "outstanding": round(pl.ordered - pl.received, 6),
                     "value": round((pl.ordered - pl.received) * pl.price, 2)}
                if pl.credits:
                    e["credited_by"] = sorted(set(pl.credits))
                goods_owed.append(e)
            if pl.received - net > QTY_EPS:
                paperwork_owed.append({"po": pl.po, "sku": pl.sku, "description": pl.description,
                                       "received": pl.received, "invoiced": net,
                                       "outstanding": round(pl.received - net, 6),
                                       "value": round((pl.received - net) * pl.price, 2),
                                       "receipts": sorted(set(pl.receipts))})
            if net - pl.received > QTY_EPS:
                invoiced_not_received.append({"po": pl.po, "sku": pl.sku, "received": pl.received, "invoiced": net,
                                              "excess": round(net - pl.received, 6)})
    money_owed = []
    for inv in by_type[DocType.SUPPLIER_INVOICE]:
        num = _num(inv.value("doc_number"))
        total = inv.value("total") or 0
        out = round(total - credited_value.get(num, 0) - paid.get(num, 0), 2)
        if out > 0.004:
            money_owed.append({"invoice": inv.value("doc_number"), "supplier": inv.value("supplier_name"),
                               "invoice_total": total, "credits": round(credited_value.get(num, 0), 2),
                               "paid": round(paid.get(num, 0), 2), "outstanding": out,
                               "po": invoice_to_po.get(str(inv.value("doc_number")))})
    if unread:
        for e in exceptions:
            if e.bucket in ("missing_receipt", "quantity_variance") and not e.resolved_by:
                e.headline += (f" {len(unread)} document(s) in the pile are unread; the delivery record may be"
                               f" among them.")
    return Resolution([pl for ls in po_lines.values() for pl in ls], invoice_to_po, link_scores,
                      goods_owed, paperwork_owed, invoiced_not_received, money_owed, exceptions, unread, corroboration)


# ------------------------------------------------------------------ scoring a candidate PO
def _supplier_score(d: ReadDocument, po: ReadDocument) -> float:
    a, b = supplier_key(d), supplier_key(po)
    if not a or not b:
        return 0.0
    if a == b or a in b or b in a:
        return 1.0
    wa, wb = set(a.split()), set(b.split())
    return len(wa & wb) / len(wa | wb)


def _candidate_score(d: ReadDocument, po: ReadDocument, lines: list[POLine]) -> float:
    """G5: vendor 0.35, amount 0.25, date 0.15, line overlap 0.25. Deterministic and auditable."""
    s = WEIGHTS["supplier"] * _supplier_score(d, po)
    sub, po_sub = d.value("subtotal"), po.value("subtotal")
    if sub and po_sub:
        s += WEIGHTS["amount"] * max(0.0, 1 - abs(sub - po_sub) / po_sub)
    elif d.doc_type == DocType.GOODS_RECEIPT:
        s += WEIGHTS["amount"] * 0.5            # dockets carry no money; neither help nor hurt
    dd, pd = _d(d.value("date")), _d(po.value("date"))
    if dd and pd:
        days = (dd - pd).days
        s += WEIGHTS["date"] * (1.0 if 0 <= days <= 45 else 0.3 if -3 <= days <= 90 else 0.0)
    if d.lines and lines:
        hit = sum(1 for l in d.lines if any(line_matches(l, {"sku": pl.sku, "description": pl.description}) >= 0.6
                                            for pl in lines))
        s += WEIGHTS["lines"] * hit / len(d.lines)
    return s


def _money(x) -> str:
    return "n/a" if x is None else f"${x:,.2f}"

"""The status report: what someone who has never seen the code can read."""
from __future__ import annotations

from .resolve import Resolution

BUCKET_NAMES = {
    "price_variance": "Price variance", "quantity_variance": "Quantity variance",
    "no_matching_po": "No matching PO", "duplicate_suspected": "Duplicate suspected",
    "missing_receipt": "Missing receipt", "missing_document": "On statement, never received",
}


def _m(x) -> str:
    return f"${x:,.2f}"


def render(res: Resolution) -> str:
    out = ["STATUS OF THE PAPERWORK AND THE GOODS", ""]
    if res.unread:
        out.append(f"Provisional: {len(res.unread)} document(s) could not be read and are not in these figures.")
        for u in res.unread:
            out.append(f"  - {u['source']}: {u['why']}")
        out.append("")
    go = res.goods_owed
    out.append(f"GOODS OWED (ordered, not yet received): {len(go)} line(s), {_m(sum(e['value'] for e in go))}")
    for e in go:
        extra = f"  [credited by {', '.join(e['credited_by'])}]" if e.get("credited_by") else ""
        out.append(f"  {e['po']:<9} {e['description'][:40]:<40} {e['outstanding']:>10g} of {e['ordered']:<8g} {_m(e['value']):>12}{extra}")
    po = res.paperwork_owed
    out += ["", f"PAPERWORK OWED (received, not yet invoiced): {len(po)} line(s), {_m(sum(e['value'] for e in po))}"]
    for e in po:
        out.append(f"  {e['po']:<9} {e['description'][:40]:<40} {e['outstanding']:>10g} received on {', '.join(e['receipts'])}  {_m(e['value']):>12}")
    mo = res.money_owed
    out += ["", f"MONEY OWED (invoiced, not yet paid): {len(mo)} invoice(s), {_m(sum(e['outstanding'] for e in mo))}"]
    for e in mo:
        parts = [f"total {_m(e['invoice_total'])}"]
        if e["credits"]:
            parts.append(f"credits {_m(e['credits'])}")
        if e["paid"]:
            parts.append(f"paid {_m(e['paid'])}")
        out.append(f"  {str(e['invoice']):<13} {str(e['supplier'])[:34]:<34} {_m(e['outstanding']):>12}  ({', '.join(parts)})")
    if res.invoiced_not_received:
        out += ["", "INVOICED BUT NOT RECEIVED"]
        for e in res.invoiced_not_received:
            out.append(f"  {e['po']:<9} {e['sku']:<18} invoiced {e['invoiced']:g}, received {e['received']:g}")
    out += ["", f"NEEDS A PERSON: {sum(1 for e in res.exceptions if not e.resolved_by)} open exception(s)"]
    for bucket, name in BUCKET_NAMES.items():
        items = [e for e in res.exceptions if e.bucket == bucket]
        if not items:
            continue
        out.append(f"  {name}")
        for e in items:
            tag = "  RESOLVED" if e.resolved_by else ""
            out.append(f"    - {e.headline}{tag}")
            if not e.resolved_by:
                out.append(f"      Suggested: {e.suggested}")
    if res.corroboration:
        out += ["", "SUPPLIER STATEMENTS"]
        for c in res.corroboration:
            out.append(f"  {c['supplier']} at {c['date']}: closing {_m(c['closing_balance'] or 0)}; "
                       f"{len(c['invoices_agreed'])} of our documents agree"
                       + (f"; ours not on their statement: {', '.join(c['ours_not_on_statement'])}" if c['ours_not_on_statement'] else "")
                       + (f"; theirs we never received: {', '.join(c['on_statement_not_received'])}" if c['on_statement_not_received'] else ""))
    return "\n".join(out)

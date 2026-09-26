"""UBL 2.1 e-invoices (Peppol PINT A-NZ and BIS). Structured data read as structure.

No model and no heuristics: the file says exactly what each value is.
"""
from __future__ import annotations

from lxml import etree

from ..models import DocType, FieldValue

NS = {"cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
      "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"}


def is_ubl(data: bytes) -> bool:
    head = data[:2000]
    return b"urn:oasis:names:specification:ubl:schema:xsd:" in head and (b"<Invoice" in head or b"<CreditNote" in head
                                                                          or b":Invoice" in head or b":CreditNote" in head)


def _t(node, path: str):
    r = node.xpath(path, namespaces=NS)
    if not r:
        return None
    v = r[0]
    return (v.text if hasattr(v, "text") else str(v)).strip() if v is not None else None


def _f(node, path: str):
    v = _t(node, path)
    return None if v is None else round(float(v), 2)


def read_ubl(data: bytes) -> tuple[DocType, dict[str, FieldValue], list[dict]]:
    root = etree.fromstring(data)
    credit = etree.QName(root).localname == "CreditNote"
    dt = DocType.CREDIT_NOTE if credit else DocType.SUPPLIER_INVOICE
    sup = "cac:AccountingSupplierParty/cac:Party"
    abn = _t(root, f"{sup}/cac:PartyLegalEntity/cbc:CompanyID") or _t(root, f"{sup}/cbc:EndpointID")
    f = {
        "doc_number": _t(root, "cbc:ID"),
        "date": _t(root, "cbc:IssueDate"),
        "due_date": _t(root, "cbc:DueDate"),
        "po_reference": _t(root, "cac:OrderReference/cbc:ID"),
        "supplier_name": _t(root, f"{sup}/cac:PartyLegalEntity/cbc:RegistrationName")
                         or _t(root, f"{sup}/cac:PartyName/cbc:Name"),
        "supplier_abn": (f"{abn[:2]} {abn[2:5]} {abn[5:8]} {abn[8:]}" if abn and len(abn) == 11 else abn),
        "buyer_name": _t(root, "cac:AccountingCustomerParty/cac:Party/cac:PartyLegalEntity/cbc:RegistrationName"),
        "payment_terms": _t(root, "cac:PaymentTerms/cbc:Note"),
        "subtotal": _f(root, "cac:LegalMonetaryTotal/cbc:TaxExclusiveAmount"),
        "gst": _f(root, "cac:TaxTotal/cbc:TaxAmount"),
        "total": _f(root, "cac:LegalMonetaryTotal/cbc:PayableAmount")
                 or _f(root, "cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount"),
        "original_invoice": _t(root, "cac:BillingReference/cac:InvoiceDocumentReference/cbc:ID"),
    }
    fields = {k: FieldValue(v, confidence=1.0, source="ubl", grounded=True) for k, v in f.items() if v not in (None, "")}
    lines = []
    tag = "cac:CreditNoteLine" if credit else "cac:InvoiceLine"
    qtag = "cbc:CreditedQuantity" if credit else "cbc:InvoicedQuantity"
    for ln in root.xpath(tag, namespaces=NS):
        lines.append({k: v for k, v in {
            "sku": _t(ln, "cac:Item/cac:SellersItemIdentification/cbc:ID"),
            "description": _t(ln, "cac:Item/cbc:Name"),
            "quantity": float(_t(ln, qtag)) if _t(ln, qtag) else None,
            "unit_price": _f(ln, "cac:Price/cbc:PriceAmount"),
            "amount": _f(ln, "cbc:LineExtensionAmount"),
        }.items() if v is not None})
    return dt, fields, lines

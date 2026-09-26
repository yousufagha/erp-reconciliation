"""What suppliers print, mapped to our field names.

This is vocabulary, not templates: no positions, no per-supplier configuration.
Each list is ordered most specific first.
"""
from __future__ import annotations

import re

from .models import DocType


def norm(s: str) -> str:
    s = s.casefold().replace("№", "no").replace("n°", "no ")
    s = re.sub(r"[^\w#%\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


HEADER_LABELS: dict[str, list[str]] = {
    "doc_number": [
        "tax invoice no", "tax invoice number", "invoice number", "invoice no", "invoice #", "invoice num",
        "inv no", "inv #", "credit note no", "credit note number", "adjustment note no", "tax credit note no",
        "docket no", "docket number", "delivery docket no", "delivery no", "delivery note no", "packing slip no",
        "grn no", "grn number", "goods received note", "remittance no", "remittance number", "payment ref",
        "payment reference", "po number", "po no", "purchase order no", "purchase order number", "order number",
        "schedule", "price list no", "our ref", "document no", "document number", "facture no", "factuurnummer",
        "rechnungsnr", "rechnungsnummer", "invoice", "number", "no", "#",
    ],
    "date": [
        "invoice date", "tax invoice date", "issue date", "date of issue", "docket date", "delivery date",
        "received date", "received", "order date", "payment date", "statement date", "credit note date",
        "date issued", "dated", "as at", "rechnungsdatum", "factuurdatum", "factuur datum", "date de facture",
        "date",
    ],
    "po_reference": [
        "customer po", "customer po no", "customer order no", "customer order", "your order no", "your order",
        "your po", "your ref", "your reference", "order no", "order ref", "purchase order", "po number",
        "po no", "po ref", "po", "order number",
    ],
    "due_date": ["due date", "payment due", "payment due date", "date limite de paiement", "due"],
    "payment_terms": ["payment terms", "terms"],
    "original_invoice": ["original invoice", "original invoice no", "against invoice", "credit for invoice",
                         "invoice credited", "relates to invoice"],
    "delivery_date": ["deliver by", "delivery required", "required by", "delivery date"],
    "effective_from": ["effective from", "valid from", "effective date"],
    "effective_to": ["effective to", "valid to", "valid until", "expires"],
    "subtotal": ["subtotal", "sub total", "total ex gst", "total excl gst", "total excluding gst",
                 "amount ex gst", "net total", "total before gst", "untaxed amount", "montant eur ht",
                 "montant ht", "total ht", "exclusief btw", "nettobetrag", "total ex tax"],
    "gst": ["gst 10%", "gst amount", "total gst", "gst", "tax amount", "total tax", "vat", "tax",
            "montant tva", "btw"],
    "total": ["total inc gst", "total incl gst", "total including gst", "total aud", "total credit aud",
              "amount due", "total due", "invoice total", "grand total", "order total", "total paid",
              "balance due", "amount payable", "total amount due", "total amount", "total for this invoice",
              "factuur totaal eur", "factuur totaal", "montant eur ttc", "total ttc", "rechnungsbetrag",
              "gesamtbetrag", "totaal", "total", "amount"],
    "opening_balance": ["opening balance", "balance brought forward", "balance b f", "previous balance"],
    "closing_balance": ["closing balance", "balance due", "amount due", "total due", "balance now due",
                        "total outstanding", "closing"],
    "supplier_name": ["supplier", "vendor", "payee", "service provider", "sold by", "from"],
    "buyer_name": ["bill to", "invoice to", "customer", "sold to", "deliver to", "ship to", "payer", "to"],
}

# fields whose label must not be taken as a generic "number" etc. for these types
TYPE_NUMBER_LABELS: dict[DocType, list[str]] = {
    DocType.SUPPLIER_INVOICE: ["tax invoice no", "tax invoice number", "invoice number", "invoice no", "invoice #",
                               "invoice num", "inv no", "inv #", "our ref", "document no", "document number",
                               "facture no", "factuurnummer", "rechnungsnr", "rechnungsnummer", "factuur", "invoice",
                               "number", "no", "#"],
    DocType.CREDIT_NOTE: ["credit note no", "credit note number", "adjustment note no", "tax credit note no",
                          "credit no", "document no", "number"],
    DocType.GOODS_RECEIPT: ["docket no", "docket number", "delivery docket no", "delivery no", "delivery note no",
                            "packing slip no", "grn no", "grn number", "goods received note", "document no", "number"],
    DocType.PURCHASE_ORDER: ["po number", "po no", "purchase order no", "purchase order number", "purchase order",
                             "order number", "order no", "number"],
    DocType.REMITTANCE: ["remittance no", "remittance number", "remittance advice no", "payment ref",
                         "payment reference", "reference", "number"],
    DocType.PRICE_SCHEDULE: ["schedule", "schedule no", "price list no", "reference"],
    DocType.STATEMENT: [],
    DocType.UNKNOWN: [],
}

COLUMN_LABELS: dict[str, list[str]] = {
    "sku": ["item code", "product code", "part no", "part number", "item no", "code", "sku", "item", "product",
            "article"],
    "description": ["item description", "product description", "description", "details", "particulars",
                    "title", "name", "omschrijving", "désignation", "designation", "document type", "type"],
    "quantity_received": ["qty received", "quantity received", "received", "qty supplied", "qty delivered",
                          "supplied", "delivered"],
    "quantity": ["quantity", "qty", "qté", "aantal", "units", "qty ordered", "ordered", "invoicedquantity"],
    "unit": ["unit", "uom", "unit of measure"],
    "unit_price": ["unit price", "price ex gst", "price each", "unit cost", "price", "rate", "prijs",
                   "prix unitaire"],
    "amount": ["line total", "line amount", "amount paid", "extended", "ext price", "net amount", "amount", "value",
               "total", "invoice amount", "bedrag"],
    "reference": ["document", "reference", "invoice no", "invoice", "doc no", "ref", "transaction"],
    "date": ["trans date", "transaction date", "invoice date", "date"],
    "debit": ["debit", "debits", "charges", "invoiced"],
    "credit": ["credit", "credits", "payments", "paid"],
    "balance": ["running balance", "balance"],
}

TOTAL_ROW = re.compile(r"^(sub ?total|total|gst|tax|vat|amount due|balance|closing|grand total|order total"
                       r"|total ex|total inc|montant)", re.I)

LEGAL_ENTITY = re.compile(r"\b(pty\.?\s*ltd|pty\.?\s*limited|limited|ltd|inc|incorporated|llc|b\.v\.?|bv|gmbh|"
                          r"ag|s\.?a\.?s?|plc|corp(oration)?|co\.|pvt\.?\s*ltd|private limited|spółka)\b\.?", re.I)


def match_label(text: str, labels: list[str]) -> tuple[str, str] | None:
    """If `text` starts with one of `labels` (whole words), return (label, remainder after it)."""
    t = norm(text)
    for lab in labels:
        if t == lab:
            return lab, ""
        if t.startswith(lab + " ") or t.startswith(lab + ":"):
            raw = text
            # remainder from the raw text after the label and any separator
            m = re.match(r"^\s*" + r"\W*\s*".join(re.escape(w) for w in lab.split()) + r"\s*[:#.\-]*\s*(.*)$",
                         raw, re.I)
            return lab, (m.group(1).strip() if m else t[len(lab):].strip(" :"))
    return None

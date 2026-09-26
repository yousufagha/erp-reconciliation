"""Core records shared by every stage.

A *file* is what arrives. A *document* is one business document (an invoice,
a docket, a statement). One file can hold many documents and one document can
span several files, so the two are kept apart from the first line.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class DocType(str, Enum):
    SUPPLIER_INVOICE = "supplier_invoice"
    CREDIT_NOTE = "credit_note"
    GOODS_RECEIPT = "goods_receipt"      # GRN or supplier delivery docket
    STATEMENT = "statement"
    PRICE_SCHEDULE = "price_schedule"
    PURCHASE_ORDER = "purchase_order"
    REMITTANCE = "remittance"
    UNKNOWN = "unknown"


# Header fields each type can carry. Anything else a reader returns is ignored.
HEADER_FIELDS: dict[DocType, tuple[str, ...]] = {
    DocType.SUPPLIER_INVOICE: (
        "supplier_name", "supplier_abn", "buyer_name", "doc_number", "date",
        "po_reference", "due_date", "payment_terms", "subtotal", "gst", "total",
    ),
    DocType.CREDIT_NOTE: (
        "supplier_name", "supplier_abn", "buyer_name", "doc_number", "date",
        "original_invoice", "po_reference", "subtotal", "gst", "total",
    ),
    DocType.GOODS_RECEIPT: (
        "supplier_name", "buyer_name", "doc_number", "date", "po_reference",
    ),
    DocType.STATEMENT: (
        "supplier_name", "supplier_abn", "buyer_name", "date",
        "opening_balance", "closing_balance",
    ),
    DocType.PRICE_SCHEDULE: (
        "supplier_name", "doc_number", "effective_from", "effective_to",
    ),
    DocType.PURCHASE_ORDER: (
        "supplier_name", "buyer_name", "doc_number", "date",
        "delivery_date", "subtotal", "gst", "total",
    ),
    DocType.REMITTANCE: (
        "supplier_name", "buyer_name", "doc_number", "date", "total",
    ),
    DocType.UNKNOWN: (),
}

LINE_FIELDS = ("sku", "description", "quantity", "unit", "unit_price", "amount", "reference", "date")

MONEY_FIELDS = {
    "subtotal", "gst", "total", "opening_balance", "closing_balance",
    "unit_price", "amount",
}
DATE_FIELDS = {"date", "due_date", "effective_from", "effective_to", "delivery_date"}


@dataclass
class SourceRef:
    """Where a document came from: one file, optionally a page range."""
    file: str
    pages: list[int] | None = None   # 1-based; None means the whole file


@dataclass
class FieldValue:
    value: Any
    confidence: float = 0.0
    source: str = ""                  # which reader produced it
    grounded: bool | None = None      # located on the page as an exact token
    blocked_on: str | None = None     # "corroboration" | "extraction_quality"


@dataclass
class ReadDocument:
    """A reader's answer for one business document."""
    sources: list[SourceRef]
    doc_type: DocType = DocType.UNKNOWN
    fields: dict[str, FieldValue] = field(default_factory=dict)
    lines: list[dict[str, Any]] = field(default_factory=list)
    reader: str = ""
    status: str = "read"              # read | held | failed
    notes: list[str] = field(default_factory=list)
    checks: list = field(default_factory=list)           # validate.Check
    printed_label: str = ""
    raw_text: str = ""                                   # kept for joining; not written out
    model_read: bool = False                             # values came from a model reading an image

    def value(self, name: str) -> Any:
        fv = self.fields.get(name)
        return None if fv is None else fv.value

    def to_json(self) -> dict[str, Any]:
        return {
            "sources": [asdict(s) for s in self.sources],
            "doc_type": self.doc_type.value,
            "fields": {k: v.value for k, v in self.fields.items()},
            "field_meta": {
                k: {"confidence": v.confidence, "source": v.source,
                    "grounded": v.grounded, "blocked_on": v.blocked_on}
                for k, v in self.fields.items()
            },
            "lines": self.lines,
            "reader": self.reader,
            "model_read": self.model_read,
            "status": self.status,
            "notes": self.notes,
            "checks": [c.to_json() for c in self.checks],
        }

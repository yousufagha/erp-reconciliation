"""Step 5: reading pages that have no text layer (scans, phone photos) with a model.

The model reads; it never decides. It returns what is printed, as printed, into
a fixed schema. Everything after that (parsing, arithmetic, grounding,
confidence, the gate, every link and figure) is the same deterministic code the
text-layer path uses.

Providers sit behind one small interface so the free test model can be swapped
for a paid one with a setting:
    PILE_MODEL_PROVIDER = gemini | none         (default: gemini if a key is set)
    PILE_MODEL          = model id              (default below)
    PILE_MODEL_MIN_INTERVAL = seconds between calls (default 5; free-tier limits are per minute)
    PILE_MODEL_TIMEOUT  = seconds before a call is abandoned and the page held (default 90)
    GEMINI_API_KEY      = your key from Google AI Studio

Gemini's free tier uses submitted content to improve Google's products. Use it
for synthetic and public test documents only, never for client paperwork.
"""
from __future__ import annotations

import base64
import io
import json
import os
from dataclasses import dataclass
from typing import Any, Protocol

from .models import DocType

DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"   # Google's docs, Sep 2026: recommended with 3.5 Flash-Lite

PROMPT = """You are reading ONE page of a business document received by an Australian steel
fabrication company. Return only what is printed on this page, copied exactly as printed
(keep commas, currency symbols and date formats). If something is not printed, return null.
Never calculate, infer or correct a value. If the page is not a business document, use
doc_type "unknown".

doc_type is the kind of document this page belongs to:
supplier_invoice, credit_note, goods_receipt (delivery docket, goods received note, packing
slip), statement, price_schedule, purchase_order, remittance, unknown.

continues_previous is true only if the page says it continues an earlier page (for example
"continued", or "Page 2 of 3"). page_number and page_count are as printed, else null.

For line items, copy each row of the main table. For statements use reference, date and
amount (charges positive, payments and credits negative, as the statement shows them).
Handwritten figures: copy them if legible and set handwritten true on that line."""

LINE_PROPS = {k: {"type": ["string", "null"]} for k in
              ("sku", "description", "quantity", "unit", "unit_price", "amount", "reference", "date")}
LINE_PROPS["handwritten"] = {"type": ["boolean", "null"]}
FIELD_NAMES = ("supplier_name", "supplier_abn", "buyer_name", "doc_number", "date", "po_reference",
               "due_date", "payment_terms", "original_invoice", "delivery_date", "effective_from",
               "effective_to", "subtotal", "gst", "total", "opening_balance", "closing_balance")
SCHEMA = {
    "type": "object",
    "properties": {
        "doc_type": {"type": "string", "enum": [t.value for t in DocType]},
        "printed_title": {"type": ["string", "null"]},
        "continues_previous": {"type": "boolean"},
        "page_number": {"type": ["string", "null"]},
        "page_count": {"type": ["string", "null"]},
        "fields": {"type": "object", "properties": {f: {"type": ["string", "null"]} for f in FIELD_NAMES}},
        "lines": {"type": "array", "items": {"type": "object", "properties": LINE_PROPS}},
    },
    "required": ["doc_type", "continues_previous", "fields", "lines"],
}


@dataclass
class PageReading:
    page: int
    doc_type: DocType
    printed_title: str
    continues_previous: bool
    page_of: tuple[int, int] | None
    fields: dict[str, str]
    lines: list[dict[str, Any]]
    model: str


class Reader(Protocol):
    name: str

    def read_page(self, image_jpeg: bytes) -> dict: ...


class GeminiReader:
    """Google Gemini via the google-genai SDK. Written against Google's published docs
    (structured output and image understanding pages, Sep 2026); first live run is yours."""

    def __init__(self, model: str | None = None, api_key: str | None = None):
        from google import genai            # pip install google-genai
        from google.genai import types
        self.model = model or os.environ.get("PILE_MODEL", DEFAULT_GEMINI_MODEL)
        self.name = f"gemini:{self.model}"
        # A call that cannot finish is reported, never waited on forever. Free-tier limits are
        # per minute, so calls are spaced and a refused call is retried a few times with backoff.
        self.min_interval = float(os.environ.get("PILE_MODEL_MIN_INTERVAL", "5"))
        timeout_ms = int(float(os.environ.get("PILE_MODEL_TIMEOUT", "90")) * 1000)
        self.client = genai.Client(
            api_key=api_key or os.environ.get("GEMINI_API_KEY"),
            http_options=types.HttpOptions(
                timeout=timeout_ms,
                retry_options=types.HttpRetryOptions(attempts=3, initial_delay=10, max_delay=60,
                                                     http_status_codes=[429, 500, 503])))
        self._last = 0.0

    def read_page(self, image_jpeg: bytes) -> dict:
        import time
        wait = self.min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        interaction = self.client.interactions.create(
            model=self.model,
            input=[{"type": "text", "text": PROMPT},
                   {"type": "image", "data": base64.b64encode(image_jpeg).decode("ascii"), "mime_type": "image/jpeg"}],
            response_format={"type": "text", "mime_type": "application/json", "schema": SCHEMA},
        )
        return json.loads(interaction.output_text)


OVERRIDE: Reader | None = None      # tests install a stand-in reader here


def available_reader() -> Reader | None:
    if OVERRIDE is not None:
        return OVERRIDE
    provider = os.environ.get("PILE_MODEL_PROVIDER", "gemini" if os.environ.get("GEMINI_API_KEY") else "none")
    if provider == "gemini" and os.environ.get("GEMINI_API_KEY"):
        return GeminiReader()
    return None


# ------------------------------------------------------------------ page images
def page_images(data: bytes, kind: str, pages: list[int] | None = None, dpi: int = 150) -> list[tuple[int, Any]]:
    """PIL images for the pages to read. Images are one page; PDFs are rendered."""
    from PIL import Image, ImageOps
    if kind == "image":
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
        return [(1, img)]
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(data)
    out = []
    try:
        for i in range(len(doc)):
            if pages and i + 1 not in pages:
                continue
            out.append((i + 1, doc[i].render(scale=dpi / 72).to_pil().convert("RGB")))
    finally:
        doc.close()
    return out


def jpeg(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def to_reading(page: int, raw: dict, model: str) -> PageReading:
    try:
        dt = DocType(raw.get("doc_type") or "unknown")
    except ValueError:
        dt = DocType.UNKNOWN
    pn, pc = raw.get("page_number"), raw.get("page_count")
    page_of = (int(pn), int(pc)) if str(pn or "").isdigit() and str(pc or "").isdigit() else None
    fields = {k: v for k, v in (raw.get("fields") or {}).items() if v not in (None, "")}
    lines = [{k: v for k, v in l.items() if v not in (None, "")} for l in raw.get("lines") or []]
    return PageReading(page, dt, raw.get("printed_title") or "", bool(raw.get("continues_previous")),
                       page_of, fields, [l for l in lines if l], model)

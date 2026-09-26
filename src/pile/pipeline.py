"""The pile, end to end: intake -> dedupe -> profile -> read -> classify -> extract.

Stages not built yet hold the document for a person and say why, rather than
guessing. A held document is counted, never silently dropped.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import layout
from .classify import classify
from .extract import Context, extract
from .intake import Item, intake
from .models import DocType, FieldValue, ReadDocument, SourceRef
from .profile import profile
from . import validate
from .segment import join_continuations
from .readers.ubl import read_ubl

GRID_BUILDERS = {"xlsx": layout.from_xlsx, "csv": layout.from_csv, "docx": layout.from_docx, "text": layout.from_text}


def load_context(folder: Path) -> Context:
    """The buyer is the CRM's own company, so it is configuration, not something to read."""
    p = folder / "context.json"
    if p.exists():
        data = json.loads(p.read_text())
        c = data.get("buyer", {})
        return Context(buyer_name=c.get("name"), buyer_abn=c.get("abn"), suppliers=data.get("suppliers", []))
    return Context()


def read_item(item: Item, ctx: Context) -> list[ReadDocument]:
    prof = profile(item)
    src = [SourceRef(item.ref)]
    if prof.kind == "ubl":
        dt, fields, lines = read_ubl(item.data)
        return [ReadDocument(src, dt, fields, lines, reader="ubl")]
    if prof.kind in GRID_BUILDERS:
        grid = GRID_BUILDERS[prof.kind](item.data, item.ref)
        return [from_grid(grid, src, ctx, reader=prof.kind)]
    if prof.kind == "image":
        from .image_read import read_images
        return read_images(item, "image", None, ctx)
    if prof.kind == "pdf":
        from .pdf_text import read_pdf           # step 2
        return read_pdf(item, prof, ctx)
    reason = prof.note or f"{prof.kind}: no reader yet"
    return [ReadDocument(src, DocType.UNKNOWN, reader="none", status="held", notes=[reason])]


def from_grid(grid, src, ctx, reader: str) -> ReadDocument:
    cls = classify(grid)
    fields, lines = extract(grid, cls.doc_type, ctx, source=reader)
    doc = ReadDocument(src, cls.doc_type, fields, lines, reader=reader, printed_label=cls.evidence, raw_text=grid.text,
                       notes=[f"type from printed label: {cls.evidence!r}"])
    if cls.doc_type == DocType.UNKNOWN:
        doc.status = "held"
        doc.notes.append("no document type printed; needs a model or a person")
    return doc


def gate(doc: ReadDocument, ctx: Context) -> None:
    """FIG 8, first two questions. Did the read yield anything? Does the arithmetic hold?

    The third question (would a better reader fix the weak fields?) needs the model
    path and the confidence engine, step 5.
    """
    if doc.status != "read":
        return
    australian = bool(ctx.buyer_abn) or bool(doc.value("supplier_abn"))
    doc.checks = validate.check(doc, doc.printed_label, australian=australian)
    if not doc.fields and not doc.lines:
        doc.status = "held"
        doc.notes.append("the read found nothing; an empty reading is never accepted")
        return
    failed = [c for c in doc.checks if not c.passed and c.kind in ("arithmetic", "presence")]
    if failed:
        doc.status = "held"
        doc.notes += [f"check failed: {c.name} ({c.detail})" if c.detail else f"check failed: {c.name}" for c in failed]
        return
    from .image_read import third_question
    third_question(doc)
    _no_guess(doc, ctx)


def _no_guess(doc: ReadDocument, ctx: Context) -> None:
    """Values that rest on inference rather than on what is printed are flagged, never passed as fact."""
    if doc.status not in ("read", "flagged"):
        return
    sup = doc.fields.get("supplier_name")
    if sup is not None and sup.evidence == "layout":
        sup.blocked_on = "corroboration"
        doc.status = "flagged"
        doc.notes.append(f"supplier {sup.value!r} inferred from the letterhead, not from a label or the supplier list;"
                         " confirm it")
    from .dates import ambiguous_dates
    for k, why in ambiguous_dates(doc, ctx):
        doc.fields[k].blocked_on = "extraction_quality"
        doc.status = "flagged"
        doc.notes.append(why)


def run(folder: Path) -> list[ReadDocument]:
    ctx = load_context(folder)
    items = intake(folder)
    seen: dict[str, str] = {}
    docs: list[ReadDocument] = []
    for it in items:
        # dedupe before reading: reading is the expensive step, hashing costs nothing
        if it.sha256 in seen:
            first = seen[it.sha256]
            docs.append(ReadDocument([SourceRef(it.ref)], reader="dedupe", status="duplicate",
                                     notes=[f"byte-identical to {first}"]))
            continue
        seen[it.sha256] = it.ref
        docs.extend(read_item(it, ctx))
    docs = join_continuations(docs)
    for d in docs:
        gate(d, ctx)
    _flag_same_document(docs)
    return docs


def _flag_same_document(docs: list[ReadDocument]) -> None:
    """Different bytes, same business document (re-sent, re-scanned, photographed)."""
    by_key: dict[tuple, ReadDocument] = {}
    for d in docs:
        num = d.value("doc_number")
        if not num or d.doc_type == DocType.UNKNOWN:
            continue
        key = (d.doc_type.value, str(d.value("supplier_name") or "").casefold()[:12], str(num).casefold())
        if key in by_key:
            d.notes.append(f"same document as {by_key[key].sources[0].file}")
            d.fields.setdefault("duplicate_of", FieldValue(by_key[key].sources[0].file, source="dedupe"))
        else:
            by_key[key] = d

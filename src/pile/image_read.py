"""Reading pages with no text layer: photos, scans, image-only PDFs.

With a model configured: the model reads each page into the schema; Tesseract
reads the same page independently; every value the model returns is looked for
on Tesseract's reading (grounding) and compared with a label-based extraction
of it (agreement); pages are grouped into documents with the same boundary
rules as text PDFs; then the gate decides.

Without a model: Tesseract's reading is used only to label the document
provisionally (what it is, its number, which PO it names) so the status report
can say what is waiting, and the document is held for a person. OCR alone is
not trusted to read line items: on a tilted phone photo it attaches quantities
to the wrong rows, and a delivery docket has no arithmetic to catch that.
"""
from __future__ import annotations

from .classify import classify
from .confidence import MATERIAL, band, field_confidence
from .extract import Context, extract, validate
from .layout import Grid
from .model_read import available_reader, jpeg, page_images, to_reading
from .models import HEADER_FIELDS, DocType, FieldValue, ReadDocument, SourceRef
from .normalise import parse_date, parse_money, parse_number
from . import ocr as ocr_mod
from .segment import PageFacts, _boundary


def read_images(item, kind: str, pages: list[int] | None, ctx: Context, total_pages: int = 1) -> list[ReadDocument]:
    imgs = page_images(item.data, kind, pages)
    ocr_pages = {p: _ocr_cached(item.sha256, p, img) for p, img in imgs}
    reader = available_reader()
    if reader is None:
        return _provisional(item, imgs, ocr_pages, ctx, total_pages)
    readings = []
    for p, img in imgs:
        try:
            readings.append(to_reading(p, reader.read_page(jpeg(img)), reader.name))
        except Exception as exc:   # an outage is reported, never passed off as a reading
            return [ReadDocument([SourceRef(item.ref, pages if total_pages > 1 else None)], DocType.UNKNOWN,
                                 reader=reader.name, status="held",
                                 notes=[f"model call failed ({type(exc).__name__}: {str(exc)[:120]}); held"])]
    groups = _group(readings)
    return [_assemble(item, g, ocr_pages, ctx, total_pages) for g in groups]


_OCR_CACHE: dict = {}


def _ocr_cached(sha: str, page: int, img):
    """OCR is the slow step; the same page is never OCR'd twice in one process."""
    key = (sha, page)
    if key not in _OCR_CACHE:
        _OCR_CACHE[key] = ocr_mod.ocr_page(img, page)
    return _OCR_CACHE[key]


def _group(readings):
    facts = [PageFacts(r.page, r.doc_type, 0.95 if r.doc_type != DocType.UNKNOWN else 0.0,
                       r.fields.get("doc_number"), r.page_of, r.continues_previous, False) for r in readings]
    groups, cur = [], [readings[0]]
    for i in range(1, len(readings)):
        cut, _ = _boundary(facts[i - 1], facts[i])
        if cut:
            groups.append(cur)
            cur = []
        cur.append(readings[i])
    groups.append(cur)
    return groups


def _typed(field: str, printed: str):
    return validate(field, printed)


def _typed_line(l: dict) -> dict:
    out = {}
    for k, v in l.items():
        if k == "quantity":
            n = parse_number(v)
            if n is not None:
                out[k] = n
        elif k in ("unit_price", "amount"):
            n = parse_money(v)
            if n is not None:
                out[k] = n
        elif k == "date":
            d = parse_date(v)
            if d:
                out[k] = d
        elif k != "handwritten":
            out[k] = v
    return out


def _assemble(item, group, ocr_pages, ctx, total_pages) -> ReadDocument:
    first = group[0]
    dt = first.doc_type
    page_nums = [r.page for r in group]
    ocrs = [ocr_pages[p] for p in page_nums if ocr_pages.get(p)]
    # second, independent reading: labels over Tesseract's words
    second: dict = {}
    if ocrs:
        g = Grid([row for o in ocrs for row in o.grid.rows])
        second = {k: v.value for k, v in extract(g, dt, ctx, source="ocr")[0].items()}
    readability = (sum(o.mean_conf for o in ocrs) / len(ocrs)) if ocrs else None
    wanted = HEADER_FIELDS.get(dt, ())
    printed: dict[str, str] = {}
    for r in group:
        for k, v in r.fields.items():
            printed.setdefault(k, v)
    fields: dict[str, FieldValue] = {}
    for k, raw in printed.items():
        if k not in wanted:
            continue
        val = _typed(k, raw)
        if val in (None, ""):
            continue
        g = ocr_mod.grounded(raw, ocrs, fuzzy=k.endswith("_name")) if ocrs else None
        agrees = None if second.get(k) is None else (str(second[k]).casefold() == str(val).casefold()
                                                     or (isinstance(val, float) and second[k] == val))
        fields[k] = FieldValue(val, source=first.model, grounded=g, evidence="model", printed=str(raw),
                               blocked_on="extraction_quality" if g is False else None,
                               confidence=field_confidence(k, readability=readability, grounded=g, agrees=agrees,
                                                           arithmetic_ok=None))
    lines = []
    ungrounded = []
    for r in group:
        for i, l in enumerate(r.lines, 1):
            tl = _typed_line(l)
            if not tl:
                continue
            # every number and code on a line must be on the page, not only the quantity
            for key in ("quantity", "unit_price", "amount", "sku", "reference"):
                if ocrs and l.get(key) not in (None, "") and not ocr_mod.grounded(str(l[key]), ocrs):
                    ungrounded.append(f"line {i} {key} {l[key]!r}")
            if l.get("handwritten"):
                tl["handwritten"] = True
            lines.append(tl)
    doc = ReadDocument([SourceRef(item.ref, page_nums if total_pages > 1 else None)], dt, fields, lines,
                       reader=first.model, printed_label=first.printed_title,
                       notes=[f"read by {first.model} from page image(s) {page_nums}"])
    doc.raw_text = "\n".join(o.grid.text for o in ocrs)
    doc.model_read = True
    if dt == DocType.UNKNOWN:
        doc.status = "held"
        doc.notes.append("the model found no document type")
    if ungrounded:
        doc.status = "held"
        doc.notes.append(f"not found on the page: {'; '.join(ungrounded)}; a person must check")
    return doc


def third_question(doc: ReadDocument) -> None:
    """FIG 8, question 3, for model-read documents: are the weak fields ones a better reader could fix?"""
    if doc.status != "read" or not doc.model_read:
        return
    arithmetic_ok = not any(c.kind == "arithmetic" and not c.passed for c in doc.checks)
    for k, fv in doc.fields.items():
        if k in ("subtotal", "gst", "total", "closing_balance") and any(c.kind == "arithmetic" for c in doc.checks):
            fv.confidence = round(fv.confidence + 0.12 * ((1.0 if arithmetic_ok else 0.0) - 0.5), 3)
    material = {k: fv for k, fv in doc.fields.items() if k in MATERIAL}
    if not material:
        return
    weakest_k, weakest = min(material.items(), key=lambda kv: kv[1].confidence)
    b = band(weakest.confidence)
    if b == "auto":
        return
    fixable = weakest.grounded is False or weakest.confidence < 0.6
    weakest.blocked_on = "extraction_quality" if fixable else "corroboration"
    if b == "held" and fixable:
        doc.status = "held"
        doc.notes.append(f"{weakest_k} scored {weakest.confidence:.2f} and was not found on the page; "
                         "re-read with a stronger model or check by hand")
    else:
        doc.status = "flagged"
        doc.notes.append(f"through, flagged: weakest material field {weakest_k} at {weakest.confidence:.2f} (uncalibrated)")


def _provisional(item, imgs, ocr_pages, ctx, total_pages) -> list[ReadDocument]:
    src_pages = [p for p, _ in imgs]
    if not any(ocr_pages.values()):
        return [ReadDocument([SourceRef(item.ref, src_pages if total_pages > 1 else None)], DocType.UNKNOWN,
                             reader="none", status="held",
                             notes=["no text layer, no model configured and no OCR installed; needs a person"])]
    # provisional grouping from OCR titles and numbers, same rules as everywhere else
    docs, cur, prev = [], [], None
    facts = []
    for p in src_pages:
        o = ocr_pages[p]
        cls = classify(o.grid)
        num = extract(o.grid, cls.doc_type, ctx, source="ocr")[0].get("doc_number")
        facts.append(PageFacts(p, cls.doc_type, cls.confidence, num.value if num else None, None, False, False))
    groups, cur = [], [facts[0]]
    for a, b in zip(facts, facts[1:]):
        if _boundary(a, b)[0]:
            groups.append(cur)
            cur = []
        cur.append(b)
    groups.append(cur)
    for g in groups:
        grid = Grid([row for f in g for row in ocr_pages[f.page].grid.rows])
        dt = g[0].doc_type
        fields, _ = extract(grid, dt, ctx, source="ocr")
        keep = {k: v for k, v in fields.items() if k in ("doc_number", "po_reference", "date", "supplier_name")}
        for v in keep.values():
            v.blocked_on = "extraction_quality"
        d = ReadDocument([SourceRef(item.ref, [f.page for f in g] if total_pages > 1 else None)], dt, keep, [],
                         reader="ocr (provisional)", status="held",
                         notes=["no model configured: labelled provisionally from OCR, not read; needs a model or a person"])
        d.raw_text = grid.text
        docs.append(d)
    return docs

"""Born-digital PDFs: the text layer, with positions kept.

A born-digital PDF already contains its text exactly, for free. Rendering it
to an image to "avoid OCR" would perform OCR unnecessarily. Words are grouped
into rows by vertical position and into cells by horizontal gaps, keeping each
cell's left and right edge so table columns can be recovered from geometry.
Whitespace in extracted text cannot be trusted for this: text extraction
collapses the very gaps that define a column.
"""
from __future__ import annotations

import io

from .layout import Grid, Row
from .models import DocType, ReadDocument, SourceRef

ROW_TOLERANCE = 3.0      # points: words whose vertical centres are this close share a row
CELL_GAP_FACTOR = 0.9    # a gap wider than this x font size starts a new cell


def pdf_grid(data: bytes, pages: list[int] | None = None, source: str = "") -> Grid:
    import pdfplumber
    rows: list[Row] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        n = len(pdf.pages)
        for pno, page in enumerate(pdf.pages, 1):
            if pages and pno not in pages:
                continue
            words = page.extract_words(keep_blank_chars=False, x_tolerance=1.5, y_tolerance=2,
                                       extra_attrs=["size"])
            words.sort(key=lambda w: ((w["top"] + w["bottom"]) / 2, w["x0"]))
            lines: list[list[dict]] = []
            for w in words:
                yc = (w["top"] + w["bottom"]) / 2
                if lines and abs(yc - lines[-1][0]["_yc"]) <= ROW_TOLERANCE:
                    w["_yc"] = lines[-1][0]["_yc"]
                    lines[-1].append(w)
                else:
                    w["_yc"] = yc
                    lines.append([w])
            for ln in lines:
                ln.sort(key=lambda w: w["x0"])
                cells, xs, x1s = [], [], []
                cur = [ln[0]]
                for prev, w in zip(ln, ln[1:]):
                    gap = w["x0"] - prev["x1"]
                    if gap > CELL_GAP_FACTOR * max(prev.get("size", 9), 6):
                        cells.append(cur)
                        cur = [w]
                    else:
                        cur.append(w)
                cells.append(cur)
                texts = [_join(c) for c in cells]
                xs = [c[0]["x0"] for c in cells]
                x1s = [c[-1]["x1"] for c in cells]
                rows.append(Row(texts, page=pno, y=ln[0]["_yc"], xs=xs, x1s=x1s))
    return Grid(rows, pages=n, source=source)


def _join(words: list[dict]) -> str:
    """Joins words, repairing drop-cap splits such as 'F actuurnummer'."""
    out = words[0]["text"]
    for prev, w in zip(words, words[1:]):
        dropcap = len(prev["text"]) == 1 and prev["text"].isupper() and w["text"][:1].islower() \
            and w["x0"] - prev["x1"] < 0.1 * max(prev.get("size", 9), 6)
        out += ("" if dropcap else " ") + w["text"]
    return out


def read_pdf(item, prof, ctx) -> list[ReadDocument]:
    from .image_read import read_images
    from .pipeline import from_grid
    if not prof.text_pages:
        return read_images(item, "pdf", prof.image_pages, ctx, prof.pages)
    from .segment import CONTINUED, split_pages
    grid = pdf_grid(item.data, prof.text_pages, item.ref)
    groups, why = split_pages(grid, prof.text_pages)
    docs = []
    for group in groups:
        sub = Grid([r for r in grid.rows if r.page in group], pages=len(group), source=item.ref)
        pages = group if prof.pages > 1 else None
        doc = from_grid(sub, [SourceRef(item.ref, pages)], ctx, reader="pdf_text")
        first_page = Grid(sub.page_rows(group[0]))
        if CONTINUED.search(first_page.text):
            doc.notes.append("continuation")
        docs.append(doc)
    if why:
        docs[0].notes += why
    if prof.image_pages:
        docs += read_images(item, "pdf", prof.image_pages, ctx, prof.pages)
    return docs

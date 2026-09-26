"""Stage 3: profile. What kind of file is this and which reader can attempt it.

Deterministic and free. Measures the file, never its meaning.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass

from .intake import Item
from .readers.ubl import is_ubl

TEXT_LAYER_MIN_CHARS = 40     # per page; below this a PDF page is treated as an image


@dataclass
class Profile:
    kind: str                  # ubl | xlsx | csv | docx | text | pdf | image | unsupported
    pages: int = 1
    text_pages: list[int] | None = None     # PDF pages that carry a usable text layer
    image_pages: list[int] | None = None    # PDF pages that are pictures only
    chars_per_page: float = 0.0
    numeric_ratio: float = 0.0
    note: str = ""

    @property
    def born_digital(self) -> bool:
        return self.kind != "image" and not self.image_pages


def profile(item: Item) -> Profile:
    d, ext = item.data, item.ext
    if d[:5] == b"%PDF-" or ext == ".pdf":
        return _pdf(d)
    if d[:4] == b"PK\x03\x04":
        if ext in (".xlsx", ".xlsm") or b"xl/" in d[:4000]:
            return Profile("xlsx")
        if ext == ".docx" or b"word/" in d[:4000]:
            return Profile("docx")
    if d[:3] == b"\xff\xd8\xff" or d[:8] == b"\x89PNG\r\n\x1a\n" or ext in (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic", ".webp"):
        return Profile("image", note="no text layer; needs a model or a person")
    if ext == ".xml" or d.lstrip()[:5] == b"<?xml":
        return Profile("ubl") if is_ubl(d) else Profile("unsupported", note="XML that is not UBL")
    if ext == ".csv":
        return Profile("csv")
    if ext in (".txt", ".text") or item.ref.endswith("#body"):
        return Profile("text")
    return Profile("unsupported", note=f"unrecognised file type {ext or 'without extension'}")


def _pdf(data: bytes) -> Profile:
    import pdfplumber
    text_pages, image_pages, chars, digits = [], [], 0, 0
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        n = len(pdf.pages)
        for i, page in enumerate(pdf.pages, 1):
            t = page.extract_text() or ""
            c = len(re.sub(r"\s", "", t))
            chars += c
            digits += sum(ch.isdigit() for ch in t)
            (text_pages if c >= TEXT_LAYER_MIN_CHARS else image_pages).append(i)
    return Profile("pdf", pages=n, text_pages=text_pages, image_pages=image_pages,
                   chars_per_page=chars / max(n, 1), numeric_ratio=digits / max(chars, 1))

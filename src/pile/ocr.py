"""An independent reading of a page image, for grounding and a second opinion.

Tesseract (Apache 2.0, free) gives words with positions and a per-word
confidence. It is not the main reader for images; the model is. It is here
because the model cannot point at where it found a number (structured output
and citations cannot be combined, and scans are not citable), so something
that reads the page independently must.

If Tesseract is not installed, grounding is reported as unknown, never as passed.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass

from .layout import Grid, Row


@dataclass
class OcrPage:
    page: int
    words: list[dict]          # text, conf (0-100), x0, x1, top, bottom
    grid: Grid
    mean_conf: float

    @property
    def tokens(self) -> list[str]:
        return [w["text"] for w in self.words]


def available() -> bool:
    if shutil.which("tesseract") is None:
        return False
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    return True


def ocr_page(img, page: int = 1) -> OcrPage | None:
    if not available():
        return None
    import pytesseract
    d = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, config="--psm 3")
    words = []
    for i, t in enumerate(d["text"]):
        t = (t or "").strip()
        conf = float(d["conf"][i])
        if not t or conf < 0:
            continue
        words.append({"text": t, "conf": conf, "x0": d["left"][i], "x1": d["left"][i] + d["width"][i],
                      "top": d["top"][i], "bottom": d["top"][i] + d["height"][i],
                      "line": (d["block_num"][i], d["par_num"][i], d["line_num"][i]), "h": d["height"][i]})
    return OcrPage(page, words, _grid(words, page), sum(w["conf"] for w in words) / max(len(words), 1) / 100)


def _grid(words: list[dict], page: int) -> Grid:
    """Rows by vertical position (not Tesseract's blocks, which split table columns apart)."""
    words = sorted(words, key=lambda w: ((w["top"] + w["bottom"]) / 2, w["x0"]))
    rows: list[list[dict]] = []
    for w in words:
        yc = (w["top"] + w["bottom"]) / 2
        tol = max(w["h"], 8) * 0.6
        if rows and abs(yc - rows[-1][0]["_yc"]) <= tol:
            rows[-1].append(w)
            w["_yc"] = rows[-1][0]["_yc"]
        else:
            w["_yc"] = yc
            rows.append([w])
    out = []
    for r in rows:
        r.sort(key=lambda w: w["x0"])
        cells, cur = [], [r[0]]
        for a, b in zip(r, r[1:]):
            if b["x0"] - a["x1"] > max(a["h"], 8) * 1.1:
                cells.append(cur)
                cur = [b]
            else:
                cur.append(b)
        cells.append(cur)
        out.append(Row([" ".join(w["text"] for w in c) for c in cells], page=page, y=r[0]["_yc"],
                       xs=[c[0]["x0"] for c in cells], x1s=[c[-1]["x1"] for c in cells]))
    return Grid(out, pages=1)


# ------------------------------------------------------------------ grounding
def _canon(s: str) -> str:
    s = s.strip().strip(".,;:()[]$€£").replace("$", "")
    if re.fullmatch(r"-?[\d,]*\.?\d+", s):
        return s.replace(",", "")
    return s.casefold()


def grounded(value: str, pages: list[OcrPage], fuzzy: bool = False) -> bool | None:
    """Is this printed value on the page as a whole token (or run of tokens)?

    A number found inside a longer code does not count: quantity 12 is not grounded by
    TMB-140x45-MGP12. A false grounding is worse than none.
    """
    if not pages:
        return None
    v = str(value).strip()
    if not v:
        return None
    parts = [_canon(p) for p in v.split() if _canon(p)]
    for pg in pages:
        toks = [_canon(t) for t in pg.tokens]
        n = len(parts)
        for i in range(len(toks) - n + 1):
            if toks[i:i + n] == parts:
                return True
        if fuzzy and n > 1:
            # names: OCR mangles letters in logos and headings; most of the words must still be there
            words = {t for t in toks if len(t) > 2}
            hits = sum(1 for p in parts if p in words)
            if hits / n >= 0.6:
                return True
        if n == 1:
            # tolerate the page splitting a number such as "1, 840.00" into two tokens
            joined = "".join(toks)
            if len(parts[0]) >= 4 and re.search(r"(?<![a-z0-9])" + re.escape(parts[0]) + r"(?![a-z0-9])", joined):
                return True
    return False

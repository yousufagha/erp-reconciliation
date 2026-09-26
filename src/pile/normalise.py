"""Parsing printed values into typed ones. Reader-side; the harness has its own."""
from __future__ import annotations

import re
from datetime import date, datetime

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_MONTHS.update({"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
                "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
                "décembre": 12, "decembre": 12, "januari": 1, "februari": 2, "maart": 3, "mei": 5,
                "juni": 6, "juli": 7, "augustus": 8, "oktober": 10})

MONEY_RE = re.compile(r"\(?-?\s?(?:[$€£₹]|rs\.?|aud|usd|eur)?\s?-?\d{1,3}(?:[,\s.]\d{3})*(?:[.,]\d{1,2})?\)?(?:\s?cr)?", re.I)


def parse_money(v) -> float | None:
    """'1,234.56' '$1 234,56' '(609.84)' '609.84 CR' -> float. None if not a number."""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    s = str(v).strip()
    if not s or not re.search(r"\d", s):
        return None
    neg = (s.startswith("(") and s.endswith(")")) or bool(re.search(r"\bcr\b", s, re.I)) or s.lstrip("$€£ ").startswith("-")
    s = re.sub(r"(?i)\b(aud|usd|eur|rs|inr|cr)\b\.?", "", s)
    s = re.sub(r"[^\d.,\s]", "", s).strip().replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", "") if re.search(r",\d{3}$", s) else s.replace(",", ".")
    elif s.count(".") > 1:
        head, _, tail = s.rpartition(".")
        s = head.replace(".", "") + "." + tail
    try:
        x = float(s)
    except ValueError:
        return None
    return round(-x if neg else x, 2)


def parse_number(v) -> float | None:
    """Quantities: like money but keeps three decimals (tonnes)."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    if v is None:
        return None
    s = re.sub(r"[^\d.,\-]", "", str(v))
    if not re.search(r"\d", s):
        return None
    if "," in s and "." in s:
        s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", "") if re.search(r",\d{3}$", s) else s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_date(v, dayfirst: bool = True) -> str | None:
    """Returns ISO date. Day-first (Australian) unless the numbers only work month-first."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip()
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", s)
    if m:
        return _iso(int(m[1]), int(m[2]), int(m[3]))
    m = re.search(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})\b", s)
    if m:
        a, b, y = int(m[1]), int(m[2]), int(m[3])
        y = y + 2000 if y < 100 else y
        if dayfirst and b <= 12:
            return _iso(y, b, a) or _iso(y, a, b)
        return _iso(y, a, b) or _iso(y, b, a)
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th|er)?\s+([A-Za-zéû]{3,9})\.?,?\s+(\d{4})\b", s)
    if m and m[2].lower()[:3] in _MONTHS or (m and m[2].lower() in _MONTHS):
        mon = _MONTHS.get(m[2].lower()) or _MONTHS.get(m[2].lower()[:3])
        return _iso(int(m[3]), mon, int(m[1]))
    m = re.search(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b", s)
    if m and m[1].lower()[:3] in _MONTHS:
        return _iso(int(m[3]), _MONTHS[m[1].lower()[:3]], int(m[2]))
    return None


def _iso(y: int, m: int, d: int) -> str | None:
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def abn_valid(abn: str) -> bool:
    """ATO ABN checksum."""
    d = [int(c) for c in re.sub(r"\D", "", abn or "")]
    if len(d) != 11:
        return False
    d[0] -= 1
    return sum(w * x for w, x in zip([10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19], d)) % 89 == 0


ABN_RE = re.compile(r"\b(\d{2}\s?\d{3}\s?\d{3}\s?\d{3})\b")


def find_abns(text: str) -> list[str]:
    out = []
    for m in ABN_RE.finditer(text):
        n = re.sub(r"\D", "", m[1])
        if abn_valid(n):
            out.append(f"{n[:2]} {n[2:5]} {n[5:8]} {n[8:]}")
    return out

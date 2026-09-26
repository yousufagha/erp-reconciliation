"""Scores a reader's output against a corpus's ground truth.

The harness is deliberately independent of the readers: it has its own small
normalisers and never imports parsing code, so a reader bug cannot be hidden by
the same bug in the scorer.

Truth format (corpus/<set>/truth.json):
    {"documents": [{"id", "files": [..], "pages": {file: [..]} | null,
                    "doc_type", "format", "fields": {..}, "lines": [..]}]}
Prediction format: a list of ReadDocument.to_json() dicts.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

MONEY = {"subtotal", "gst", "total", "opening_balance", "closing_balance",
         "unit_price", "amount"}
NUMBER = {"quantity"}
DATES = {"date", "due_date", "effective_from", "effective_to", "delivery_date"}
LEGAL_SUFFIXES = re.compile(r"\b(pty|ltd|limited|inc|llc|b\.?v|gmbh|co|corp|the)\b\.?", re.I)


# ---------------------------------------------------------------- normalisers
def _money(v: Any) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    s = str(v).strip()
    neg = s.startswith("(") and s.endswith(")") or s.endswith("CR") or s.startswith("-")
    s = re.sub(r"[^\d.,]", "", s)
    if "," in s and "." in s:
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", "") if re.search(r",\d{3}$", s) else s.replace(",", ".")
    try:
        x = round(float(s), 2)
    except ValueError:
        return None
    return -x if neg else x


def _date(v: Any) -> str | None:
    if v is None or v == "":
        return None
    if isinstance(v, (date, datetime)):
        return v.strftime("%Y-%m-%d")
    s = str(v).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %b %Y", "%d %B %Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s


def _text(v: Any) -> str:
    s = "" if v is None else str(v)
    s = s.casefold()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _name(v: Any) -> str:
    return re.sub(r"\s+", " ", LEGAL_SUFFIXES.sub(" ", _text(v))).strip()


def values_match(fieldname: str, truth: Any, pred: Any) -> bool:
    if pred is None or pred == "":
        return False
    if fieldname in MONEY:
        t, p = _money(truth), _money(pred)
        return t is not None and p is not None and abs(t - p) < 0.005
    if fieldname in NUMBER:
        t, p = _money(truth), _money(pred)
        return t is not None and p is not None and abs(t - p) < 1e-6
    if fieldname in DATES:
        return _date(truth) == _date(pred)
    if fieldname.endswith("_name"):
        t, p = _name(truth), _name(pred)
        return bool(t) and (t == p or (len(p) >= 4 and (t in p or p in t)))
    if fieldname.endswith("_abn"):
        return re.sub(r"\D", "", str(truth)) == re.sub(r"\D", "", str(pred))
    if fieldname == "description":
        t, p = set(_text(truth).split()), set(_text(pred).split())
        return bool(t) and len(t & p) / len(t | p) >= 0.8
    return _text(truth) == _text(pred)


# ---------------------------------------------------------------- alignment
def _pages_of(doc: dict, key: str) -> set[tuple[str, int]]:
    """Set of (file, page) a document covers; page 0 means 'whole file'."""
    out: set[tuple[str, int]] = set()
    if key == "truth":
        pages = doc.get("pages") or {}
        for f in doc["files"]:
            for p in pages.get(f) or [0]:
                out.add((f, p))
    else:
        for s in doc["sources"]:
            for p in s.get("pages") or [0]:
                out.add((s["file"], p))
    return out


def _overlap(a: set, b: set) -> int:
    """Pages two documents share. Page 0 means 'whole file' and overlaps any page of it."""
    n = 0
    for f, p in a:
        for g, q in b:
            if f == g and (p == q or p == 0 or q == 0):
                n += 1
    return n


def align(truth_docs: list[dict], preds: list[dict]) -> list[tuple[dict, dict | None]]:
    pairs: list[tuple[dict, dict | None]] = []
    used: set[int] = set()
    for t in truth_docs:
        tp = _pages_of(t, "truth")
        best, best_score = None, 0.0
        for i, p in enumerate(preds):
            if i in used:
                continue
            ov = _overlap(tp, _pages_of(p, "pred"))
            if ov == 0:
                continue
            score = float(ov)
            num = (t.get("fields") or {}).get("doc_number")
            if num and _text(num) == _text((p.get("fields") or {}).get("doc_number")):
                score += 100
            if score > best_score:
                best, best_score = i, score
        if best is not None:
            used.add(best)
            pairs.append((t, preds[best]))
        else:
            pairs.append((t, None))
    return pairs


def align_lines(truth_lines: list[dict], pred_lines: list[dict]) -> list[tuple[dict, dict | None]]:
    remaining = list(range(len(pred_lines)))
    out = []
    for t in truth_lines:
        best, best_s = None, 0.0
        for i in remaining:
            p = pred_lines[i]
            s = 0.0
            for f in ("amount", "unit_price", "quantity"):
                if f in t and values_match(f, t[f], p.get(f)):
                    s += 1
            for f in ("sku", "reference"):
                if t.get(f) and values_match(f, t[f], p.get(f)):
                    s += 1.5
            td, pd = set(_text(t.get("description")).split()), set(_text(p.get("description")).split())
            if td and pd:
                s += len(td & pd) / len(td | pd)
            if s > best_s:
                best, best_s = i, s
        if best is not None and best_s >= 0.5:
            remaining.remove(best)
            out.append((t, pred_lines[best]))
        else:
            out.append((t, None))
    return out


# ---------------------------------------------------------------- scoring
@dataclass
class Tally:
    right: int = 0
    total: int = 0

    def add(self, ok: bool) -> None:
        self.total += 1
        self.right += int(ok)

    @property
    def pct(self) -> float | None:
        return None if self.total == 0 else 100.0 * self.right / self.total


@dataclass
class Score:
    documents: Tally = field(default_factory=Tally)       # truth doc found at all
    doc_type: Tally = field(default_factory=Tally)
    headers: Tally = field(default_factory=Tally)
    lines: Tally = field(default_factory=Tally)
    packets: Tally = field(default_factory=Tally)         # files split with zero corrections
    held: int = 0
    by_field: dict[str, Tally] = field(default_factory=lambda: defaultdict(Tally))
    by_type: dict[str, Tally] = field(default_factory=lambda: defaultdict(Tally))
    by_format: dict[str, Tally] = field(default_factory=lambda: defaultdict(Tally))
    misses: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        def t(x: Tally) -> dict:
            return {"right": x.right, "total": x.total, "pct": None if x.pct is None else round(x.pct, 1)}
        return {
            "documents": t(self.documents), "doc_type": t(self.doc_type),
            "headers": t(self.headers), "lines": t(self.lines),
            "packets_zero_corrections": t(self.packets), "held": self.held,
            "by_field": {k: t(v) for k, v in sorted(self.by_field.items())},
            "by_type": {k: t(v) for k, v in sorted(self.by_type.items())},
            "by_format": {k: t(v) for k, v in sorted(self.by_format.items())},
            "misses": self.misses[:200],
        }


def _packets(truth_docs: list[dict], preds: list[dict]) -> Tally:
    """A file scores only if the predicted document boundaries inside it are exactly right."""
    tally = Tally()
    truth_groups: dict[str, set[frozenset]] = defaultdict(set)
    for t in truth_docs:
        for f in t["files"]:
            pages = (t.get("pages") or {}).get(f)
            truth_groups[f].add(frozenset(pages or [0]))
    pred_groups: dict[str, set[frozenset]] = defaultdict(set)
    for p in preds:
        for s in p["sources"]:
            pred_groups[s["file"]].add(frozenset(s.get("pages") or [0]))
    for f, groups in truth_groups.items():
        if len(groups) == 1 and len(next(iter(groups))) <= 1:
            continue  # single-page single-document files say nothing about splitting
        pg = pred_groups.get(f, set())
        tally.add(pg == groups or (groups == {frozenset([0])} and pg == {frozenset([0])}))
    return tally


def score(truth: dict, preds: list[dict]) -> Score:
    sc = Score()
    truth_docs = truth["documents"]
    sc.held = sum(1 for p in preds if p.get("status") == "held")
    sc.packets = _packets(truth_docs, preds)
    for t, p in align(truth_docs, preds):
        tid = t.get("id") or "/".join(t["files"])
        fmt = t.get("format", "unknown")
        sc.documents.add(p is not None)
        if p is None:
            sc.misses.append(f"{tid}: not found")
        type_ok = p is not None and p.get("doc_type") == t["doc_type"]
        sc.doc_type.add(type_ok)
        if p is not None and not type_ok:
            sc.misses.append(f"{tid}: doc_type {p.get('doc_type')} != {t['doc_type']}")
        pf = (p or {}).get("fields") or {}
        for name, tv in (t.get("fields") or {}).items():
            if tv is None:
                continue
            ok = values_match(name, tv, pf.get(name))
            sc.headers.add(ok)
            sc.by_field[name].add(ok)
            sc.by_type[t["doc_type"]].add(ok)
            sc.by_format[fmt].add(ok)
            if not ok and p is not None:
                sc.misses.append(f"{tid}: {name} = {pf.get(name)!r}, expected {tv!r}")
        for tl, pl in align_lines(t.get("lines") or [], (p or {}).get("lines") or []):
            for name, tv in tl.items():
                if tv is None or name not in ("sku", "description", "quantity", "unit_price", "amount", "reference"):
                    continue
                ok = pl is not None and values_match(name, tv, pl.get(name))
                sc.lines.add(ok)
                sc.by_field["line." + name].add(ok)
                sc.by_type[t["doc_type"]].add(ok)
                sc.by_format[fmt].add(ok)
    return sc


def format_report(name: str, sc: Score) -> str:
    def row(label: str, t: Tally) -> str:
        pct = "  n/a" if t.pct is None else f"{t.pct:5.1f}%"
        return f"  {label:<28}{pct}  ({t.right}/{t.total})"
    out = [f"== {name} ==",
           row("documents found", sc.documents),
           row("document type", sc.doc_type),
           row("header fields", sc.headers),
           row("line fields", sc.lines),
           row("files split correctly", sc.packets),
           f"  {'held for a person':<28}{sc.held}",
           "  by type:"]
    out += [row("  " + k, v) for k, v in sorted(sc.by_type.items())]
    out.append("  by format:")
    out += [row("  " + k, v) for k, v in sorted(sc.by_format.items())]
    return "\n".join(out)


def load_truth(corpus_dir: Path) -> dict:
    return json.loads((corpus_dir / "truth.json").read_text())

"""Fields and lines from a grid, by printed labels. No templates, no positions.

Two passes that fail differently:
  header pass  label -> value (same cell, cell to the right, or cell below)
  table pass   a row of column labels -> the rows under it, until a totals row
Every candidate value must parse as its field's type or it is discarded, which
is what stops generic labels like "No" or "Total" from grabbing sentences.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .labels import (COLUMN_LABELS, HEADER_LABELS, LEGAL_ENTITY, TOTAL_ROW, TYPE_NUMBER_LABELS,
                     match_label, norm)
from .layout import Grid, Row, cell_text
from .models import DATE_FIELDS, HEADER_FIELDS, DocType, FieldValue
from .normalise import find_abns, parse_date, parse_money, parse_number

MONEY = {"subtotal", "gst", "total", "opening_balance", "closing_balance"}
REFS = {"doc_number", "po_reference", "original_invoice"}
TOTAL_FIELDS = {"subtotal", "gst", "total", "closing_balance"}


@dataclass
class Context:
    buyer_name: str | None = None
    buyer_abn: str | None = None


# ------------------------------------------------------------------ validators
def _ref(v: Any) -> str | None:
    s = cell_text(v).strip().lstrip("#:").strip()
    for tok in re.split(r"\s+", s):
        tok = tok.strip(".,;:()")
        tok = tok.lstrip("#")
        if re.search(r"\d", tok) and 2 <= len(tok) <= 32 and not re.fullmatch(r"\d{1,2}[/.]\d{1,2}[/.]\d{2,4}", tok):
            return tok
    return None


def _name(v: Any) -> str | None:
    s = cell_text(v).strip(" :-")
    if 2 <= len(s) <= 80 and re.search(r"[A-Za-z]{2}", s) and len(s.split()) <= 10:
        return s
    return None


def validate(field: str, v: Any) -> Any:
    if v is None or cell_text(v) == "":
        return None
    if field in MONEY:
        return parse_money(v) if re.search(r"\d", cell_text(v)) and not re.search(r"[A-Za-z]{4,}", cell_text(v)) else None
    if field in DATE_FIELDS:
        return parse_date(v)
    if field in REFS:
        return _ref(v)
    if field == "payment_terms":
        s = cell_text(v)
        return s if 2 <= len(s) <= 60 else None
    if field.endswith("_name"):
        return _name(v)
    return cell_text(v)


# ------------------------------------------------------------------ header pass
def _labels_for(field: str, doc_type: DocType) -> list[str]:
    if field == "doc_number":
        return TYPE_NUMBER_LABELS.get(doc_type) or HEADER_LABELS["doc_number"]
    if field == "po_reference" and doc_type == DocType.PURCHASE_ORDER:
        return []
    return HEADER_LABELS.get(field, [])


def header_candidates(grid: Grid, doc_type: DocType, fields: tuple[str, ...]):
    """Yields (field, value, rank, row_index) for every label hit that validates."""
    rows = grid.rows
    for ri, row in enumerate(rows):
        texts = row.texts
        for ci, cell in enumerate(texts):
            if not cell:
                continue
            for field in fields:
                labs = _labels_for(field, doc_type)
                hit = match_label(cell, labs) if labs else None
                if not hit:
                    continue
                lab, rest = hit
                rank = labs.index(lab)
                options = []
                if rest:
                    options.append(rest)
                else:
                    right = [t for t in texts[ci + 1:] if t]
                    if right:
                        options.append(row.cells[texts.index(right[0], ci + 1)])
                    below = _below(rows, ri, ci, row)
                    if below is not None:
                        options.append(below)
                for opt in options:
                    val = validate(field, opt)
                    if val not in (None, ""):
                        yield field, val, rank, ri
                        break


def _below(rows: list[Row], ri: int, ci: int, row: Row):
    """Value printed under a label (label row above value row)."""
    for nxt in rows[ri + 1: ri + 3]:
        if nxt.is_blank or nxt.page != row.page:
            continue
        if row.xs and nxt.xs:
            x = row.xs[ci]
            best = min(range(len(nxt.xs)), key=lambda k: abs(nxt.xs[k] - x))
            if abs(nxt.xs[best] - x) < 40:
                return nxt.cells[best]
            return None
        return nxt.cells[ci] if ci < len(nxt.cells) else None
    return None


# ------------------------------------------------------------------ table pass
def _column_field(text: str) -> tuple[str, int] | None:
    t = norm(text)
    if not t or len(t) > 30:
        return None
    best = None
    for field, labs in COLUMN_LABELS.items():
        for i, lab in enumerate(labs):
            if t == lab or (t.startswith(lab + " ") and len(t) <= len(lab) + 8):
                score = (0 if t == lab else 1, i)
                if best is None or score < best[1]:
                    best = (field, score)
                break
    return (best[0], best[1][1]) if best else None


NUMERIC_COLS = {"quantity", "quantity_received", "unit_price", "amount", "debit", "credit"}


def find_tables(grid: Grid) -> list[tuple[int, dict[int, str]]]:
    tables = []
    for ri, row in enumerate(grid.rows):
        mapped: dict[int, tuple[str, int]] = {}
        for ci, cell in enumerate(row.texts):
            f = _column_field(cell)
            if f:
                mapped[ci] = f
        fields = {f for f, _ in mapped.values()}
        if len(mapped) >= 2 and fields & NUMERIC_COLS and len(mapped) >= 0.6 * len([t for t in row.texts if t]):
            # one column per field: keep the most specific label
            chosen: dict[str, tuple[int, int]] = {}
            for ci, (f, rank) in mapped.items():
                if f not in chosen or rank < chosen[f][1]:
                    chosen[f] = (ci, rank)
            tables.append((ri, {ci: f for f, (ci, _) in chosen.items()}))
    return tables


def _cell_for(row: Row, header: Row, ci: int):
    """Cell in `row` under header column `ci` (by index for grids, by position for PDFs)."""
    if header.xs and row.xs:
        hx0 = header.xs[ci]
        hx1 = header.xs[ci + 1] if ci + 1 < len(header.xs) else 10_000
        hxprev = header.xs[ci - 1] if ci > 0 else -10_000
        for k, x in enumerate(row.xs):
            # a cell belongs to the column whose span its left edge falls in, with some slack for
            # right-aligned numbers that start left of their header
            if hx0 - 25 <= x < hx1 - 5 and x > hxprev + 5:
                return row.cells[k]
        return None
    return row.cells[ci] if ci < len(row.cells) else None


def read_table(grid: Grid, ri: int, cols: dict[int, str]) -> tuple[list[dict], int]:
    header = grid.rows[ri]
    lines: list[dict] = []
    end = ri
    for rj in range(ri + 1, len(grid.rows)):
        row = grid.rows[rj]
        if row.is_blank:
            if lines:
                end = rj
                break
            continue
        first = next((t for t in row.texts if t), "")
        if TOTAL_ROW.match(norm(first)) and not any(re.search(r"[A-Z]{2,}-?\d", t) for t in row.texts[:2]):
            end = rj
            break
        if any(_column_field(t) for t in row.texts if t) and sum(1 for t in row.texts if _column_field(t)) >= 2:
            end = rj
            break
        vals = {f: _cell_for(row, header, ci) for ci, f in cols.items()}
        line: dict[str, Any] = {}
        for f, v in vals.items():
            if v is None or cell_text(v) == "":
                continue
            if f in ("quantity", "quantity_received"):
                n = parse_number(v)
                if n is not None:
                    line[f] = n
            elif f in ("unit_price", "amount", "debit", "credit", "balance"):
                n = parse_money(v) if not re.search(r"[A-Za-z]{3,}", cell_text(v)) else None
                if n is not None:
                    line[f] = n
            elif f == "date":
                d = parse_date(v)
                if d:
                    line[f] = d
            else:
                line[f] = cell_text(v)
        if "quantity_received" in line:
            line["quantity"] = line.pop("quantity_received")
        if "debit" in line or "credit" in line:
            line["amount"] = round(line.pop("debit", 0.0) - line.pop("credit", 0.0), 2)
        line.pop("balance", None)
        has_number = any(k in line for k in ("quantity", "unit_price", "amount"))
        if not has_number:
            # a wrapped description continues the previous line
            text = " ".join(t for t in row.texts if t)
            if lines and text and not re.search(r"\d{3,}", text) and len(text) < 80 and "reference" not in line:
                lines[-1]["description"] = (lines[-1].get("description", "") + " " + text).strip()
            continue
        lines.append(line)
        end = rj
    return lines, end


# ------------------------------------------------------------------ parties
def _looks_like_company(s: str) -> bool:
    return bool(LEGAL_ENTITY.search(s)) and len(s) <= 80 and len(s.split()) <= 10


def _same_party(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    na, nb = norm(LEGAL_ENTITY.sub("", a)), norm(LEGAL_ENTITY.sub("", b))
    return bool(na) and (na == nb or na in nb or nb in na)


def infer_parties(grid: Grid, doc_type: DocType, ctx: Context, found: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    text = grid.text
    buyer_present = bool(ctx.buyer_name) and norm(LEGAL_ENTITY.sub("", ctx.buyer_name)) in norm(text)
    if buyer_present:
        out["buyer_name"] = ctx.buyer_name
    elif found.get("buyer_name"):
        out["buyer_name"] = found["buyer_name"]

    labelled = found.get("supplier_name")
    if labelled and _same_party(labelled, ctx.buyer_name):
        labelled = None
    supplier = None
    if doc_type in (DocType.PURCHASE_ORDER, DocType.REMITTANCE) or labelled:
        supplier = labelled
    if not supplier:
        for row in [r for r in grid.rows if not r.is_blank][:14]:
            for t in row.texts:
                t2 = re.sub(r"^(from|supplier|sold by|payee)\s*[:\-]\s*", "", t, flags=re.I).strip()
                cand = t2.split("  ")[0].split(" | ")[0].strip()
                cand = re.split(r"\s+(?:ABN|A\.B\.N\.|ACN)\b", cand)[0].strip(" ,")
                if _looks_like_company(cand) and not _same_party(cand, ctx.buyer_name):
                    supplier = cand
                    break
            if supplier:
                break
    if not supplier:
        first = next((t for r in grid.rows for t in r.texts if t and not _is_label(t)), None)
        if first and not _same_party(first, ctx.buyer_name) and _name(first):
            supplier = _name(first)
    if supplier:
        out["supplier_name"] = supplier
    abns = [a for a in find_abns(text) if re.sub(r"\D", "", a) != re.sub(r"\D", "", ctx.buyer_abn or "")]
    if abns:
        out["supplier_abn"] = abns[0]
    return out


def _is_label(t: str) -> bool:
    return any(match_label(t, labs) for labs in HEADER_LABELS.values())


# ------------------------------------------------------------------ main entry
def extract(grid: Grid, doc_type: DocType, ctx: Context | None = None, source: str = "labels"
            ) -> tuple[dict[str, FieldValue], list[dict]]:
    ctx = ctx or Context()
    wanted = HEADER_FIELDS.get(doc_type, ())
    search = tuple(f for f in wanted if f not in ("supplier_abn",)) + ("supplier_name", "buyer_name")
    search = tuple(dict.fromkeys(search))

    tables = find_tables(grid)
    lines: list[dict] = []
    table_end = -1
    table_start = len(grid.rows)
    for ri, cols in tables:
        if ri <= table_end:
            continue
        got, end = read_table(grid, ri, cols)
        if got:
            lines.extend(got)
            table_start = min(table_start, ri)
            table_end = max(table_end, end)

    best: dict[str, tuple[int, int, Any]] = {}
    for field, val, rank, ri in header_candidates(grid, doc_type, search):
        if field in TOTAL_FIELDS and table_end >= 0 and ri < table_end:
            continue                        # totals live after the lines
        if field not in TOTAL_FIELDS and table_end >= 0 and table_start < ri < table_end:
            continue                        # nothing but lines inside the table
        key = (rank, ri if field not in TOTAL_FIELDS else -ri if field == "closing_balance" else ri)
        if field not in best or key < best[field][:2]:
            best[field] = (key[0], key[1], val)
    found = {f: v for f, (_, _, v) in best.items()}
    parties = infer_parties(grid, doc_type, ctx, found)
    found.pop("supplier_name", None)
    found.pop("buyer_name", None)
    found.update(parties)

    if doc_type == DocType.STATEMENT and "closing_balance" not in found and lines:
        pass  # left for validation to flag; a statement without a stated closing balance is suspicious

    fields = {f: FieldValue(v, source=source) for f, v in found.items() if f in wanted}
    return fields, _shape_lines(lines, doc_type)


def _shape_lines(lines: list[dict], doc_type: DocType) -> list[dict]:
    keep = {
        DocType.GOODS_RECEIPT: ("sku", "description", "quantity", "unit"),
        DocType.STATEMENT: ("date", "reference", "description", "amount"),
        DocType.REMITTANCE: ("reference", "amount"),
        DocType.PRICE_SCHEDULE: ("sku", "description", "unit", "unit_price"),
    }.get(doc_type, ("sku", "description", "quantity", "unit", "unit_price", "amount"))
    out = []
    for l in lines:
        if doc_type == DocType.STATEMENT and not l.get("reference"):
            continue                        # opening-balance and carried-forward rows
        if doc_type == DocType.REMITTANCE and not l.get("reference"):
            if l.get("sku"):
                l["reference"] = l.pop("sku")
            else:
                continue
        out.append({k: l[k] for k in keep if k in l})
    return out

"""Fields and lines from a grid, by printed labels. No templates, no positions.

Two passes that fail differently:
  header pass  label -> value (same cell, cell to the right, or cell below)
  table pass   a row of column labels -> the rows under it, until a totals row
Every candidate value must parse as its field's type or it is discarded, which
is what stops generic labels like "No" or "Total" from grabbing sentences.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
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
    suppliers: list[dict] = field(default_factory=list)   # the CRM's supplier list: name, abn, aliases


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
    for field, val, rank, ri, _raw in header_candidates_raw(grid, doc_type, fields):
        yield field, val, rank, ri


def header_candidates_raw(grid: Grid, doc_type: DocType, fields: tuple[str, ...]):
    """As header_candidates, plus the text exactly as printed."""
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
                options = [rest] if rest else []
                right = [t for t in texts[ci + 1:] if t]
                if right:
                    options.append(row.cells[texts.index(right[0], ci + 1)])
                if not rest:
                    below = _below(rows, ri, ci, row)
                    if below is not None:
                        options.append(below)
                for opt in options:
                    val = validate(field, opt)
                    if val not in (None, ""):
                        yield field, val, rank, ri, cell_text(opt)
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


def _column_of(row: Row, header: Row, k: int) -> int | None:
    """Header column a PDF cell sits under: the region its centre falls in.

    Regions run from halfway between neighbouring headers, so left-aligned text and
    right-aligned numbers both land under the header they belong to.
    """
    hx0, hx1 = header.xs, header.x1s or header.xs
    centre = (row.xs[k] + (row.x1s or row.xs)[k]) / 2
    for i in range(len(hx0)):
        lo = -1e9 if i == 0 else (hx1[i - 1] + hx0[i]) / 2
        hi = 1e9 if i == len(hx0) - 1 else (hx1[i] + hx0[i + 1]) / 2
        if lo <= centre < hi:
            return i
    return None


def _cell_for(row: Row, header: Row, ci: int):
    """Cell in `row` under header column `ci` (by index for grids, by position for PDFs)."""
    if header.xs and row.xs:
        hits = [row.cells[k] for k in range(len(row.cells)) if _column_of(row, header, k) == ci]
        return " ".join(str(h) for h in hits) if hits else None
    return row.cells[ci] if ci < len(row.cells) else None


def read_table(grid: Grid, ri: int, cols: dict[int, str]) -> tuple[list[dict], int]:
    header = grid.rows[ri]
    lines: list[dict] = []
    end = ri
    lines_page = header.page
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
        if sum(1 for t in row.texts if t and _column_field(t)) >= 2:
            end = rj - 1                    # the next table's heading row belongs to the next table
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
            # a wrapped description continues the previous line: same page, only the description column
            text = " ".join(t for t in row.texts if t)
            desc_col = next((ci for ci, f in cols.items() if f == "description"), None)
            only_desc = desc_col is not None and (
                all(_column_of(row, header, k) == desc_col for k in range(len(row.cells)))
                if header.xs and row.xs else len([t for t in row.texts if t]) == 1)
            if lines and only_desc and row.page == lines_page and len(text) < 80:
                lines[-1]["description"] = (lines[-1].get("description", "") + " " + text).strip()
            continue
        lines.append(line)
        lines_page = row.page
        end = rj
    return lines, end


# ------------------------------------------------------------------ parties
BUYER_BLOCK = re.compile(r"^\s*(bill(ed)?\s+to|ship\s+to|sold\s+to|invoice\s+to|deliver\s+to|attn|customer\b|"
                         r"billing\s+address|factuuradres|rechnungsadresse|adresse\s+de\s+facturation)", re.I)


def _looks_like_company(s: str) -> bool:
    return bool(LEGAL_ENTITY.search(s)) and len(s) <= 80 and len(s.split()) <= 10


def _same_party(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    na, nb = norm(LEGAL_ENTITY.sub("", a)), norm(LEGAL_ENTITY.sub("", b))
    return bool(na) and (na == nb or na in nb or nb in na)


def infer_parties(grid: Grid, doc_type: DocType, ctx: Context, found: dict[str, Any]
                  ) -> tuple[dict[str, Any], dict[str, str]]:
    """Who issued the document and who it is addressed to, with the evidence for each.

    Evidence, strongest first. A name is never taken from "the first line on the page":
      master  the supplier's ABN or name on the page matches the CRM's supplier list
      label   printed next to a label such as "Supplier:" or "Payee:"
      layout  a company-looking line in the letterhead, outside the addressee block.
              Accepted, but marked so the gate flags it for a person to confirm.
    """
    out: dict[str, Any] = {}
    ev: dict[str, str] = {}
    text = grid.text
    buyer_present = bool(ctx.buyer_name) and norm(LEGAL_ENTITY.sub("", ctx.buyer_name)) in norm(text)
    if buyer_present:
        out["buyer_name"], ev["buyer_name"] = ctx.buyer_name, "master"
    elif found.get("buyer_name"):
        out["buyer_name"], ev["buyer_name"] = found["buyer_name"], "label"

    buyer_abn = re.sub(r"\D", "", ctx.buyer_abn or "")
    abns = [a for a in find_abns(text) if re.sub(r"\D", "", a) != buyer_abn]
    if abns:
        out["supplier_abn"], ev["supplier_abn"] = abns[0], "label"

    # 1. the CRM's supplier list
    for sup in ctx.suppliers:
        sabn = re.sub(r"\D", "", sup.get("abn") or "")
        names = [sup["name"]] + list(sup.get("aliases", []))
        if (sabn and any(re.sub(r"\D", "", a) == sabn for a in abns)) or any(
                norm(LEGAL_ENTITY.sub("", n)) and norm(LEGAL_ENTITY.sub("", n)) in norm(text) for n in names):
            out["supplier_name"], ev["supplier_name"] = sup["name"], "master"
            return out, ev
    # 2. a labelled name
    labelled = found.get("supplier_name")
    if labelled and not _same_party(labelled, ctx.buyer_name):
        out["supplier_name"], ev["supplier_name"] = labelled, "label"
        return out, ev
    if doc_type in (DocType.PURCHASE_ORDER, DocType.REMITTANCE):
        return out, ev          # the issuer is the buyer; the supplier must be labelled
    # 3. letterhead: a company-looking line outside the addressee block
    nonblank = [r for r in grid.rows if not r.is_blank]
    buyer_block: set[int] = set()
    for i, row in enumerate(nonblank[:30]):
        if any(BUYER_BLOCK.match(t) for t in row.texts):
            buyer_block.update(range(i, i + 4))
    for i, row in enumerate(nonblank[:14]):
        if i in buyer_block:
            continue
        for t in row.texts:
            cand = re.split(r"\s+(?:ABN|A\.B\.N\.|ACN)\b", t.split("  ")[0].split(" | ")[0].strip())[0].strip(" ,")
            if _looks_like_company(cand) and not _same_party(cand, ctx.buyer_name) \
                    and not cand.lower().startswith(("attn", "c/o")):
                out["supplier_name"], ev["supplier_name"] = cand, "layout"
                return out, ev
    return out, ev


TITLE_WORDS = re.compile(r"\b(invoice|receipt|statement|docket|credit note|purchase order|remittance|factuur|"
                         r"facture|rechnung)\b", re.I)


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
    printed: dict[str, str] = {}
    for field, val, rank, ri, raw in header_candidates_raw(grid, doc_type, search):
        if field in TOTAL_FIELDS - {"closing_balance"} and table_end >= 0 and ri < table_end:
            continue                        # invoice totals live after the lines
        if field not in TOTAL_FIELDS and table_end >= 0 and table_start <= ri < table_end:
            continue                        # column headings and lines are not header fields
        key = (rank, ri if field not in TOTAL_FIELDS else -ri if field == "closing_balance" else ri)
        if field not in best or key < best[field][:2]:
            best[field] = (key[0], key[1], val)
            printed[field] = raw
    found = {f: v for f, (_, _, v) in best.items()}
    parties, party_evidence = infer_parties(grid, doc_type, ctx, found)
    found.pop("supplier_name", None)
    found.pop("buyer_name", None)
    found.update(parties)

    if doc_type == DocType.STATEMENT and "closing_balance" not in found and lines:
        pass  # left for validation to flag; a statement without a stated closing balance is suspicious

    fields = {f: FieldValue(v, source=source, evidence=party_evidence.get(f, "label"), printed=printed.get(f))
              for f, v in found.items() if f in wanted}
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

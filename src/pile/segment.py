"""Step 3: a file is not a document.

Split: one PDF holding several documents (a supplier's pack, a scanner batch).
Join:  one document spread over several files (page 2 sent separately).

The asymmetry sets the policy. A wrong split is silent and permanent: two
half-invoices that each look plausible. A wrong join is loud: the arithmetic
check fails because two invoices' lines do not sum to either total. So split
only on strong evidence and, when in doubt, keep pages together.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .classify import classify
from .extract import header_candidates
from .layout import Grid
from .models import DocType, ReadDocument

PAGE_OF = re.compile(r"\bpage\s*(\d+)\s*(?:of|/)\s*(\d+)\b", re.I)
CONTINUED = re.compile(r"\(continued\)|\bcontinued\s+from\b|\bcontinuation\b|\bcont(?:inued|'d)\b(?!\s+overleaf)", re.I)
CONTINUES = re.compile(r"\bcontinued\s+overleaf\b|\bcontinued\s+on\s+next\s+page\b|\bover\s*leaf\b", re.I)


@dataclass
class PageFacts:
    page: int
    doc_type: DocType
    title_strength: float
    number: str | None
    page_of: tuple[int, int] | None
    continued: bool          # says it continues something earlier
    continues: bool          # says it carries on over the page


def page_facts(grid: Grid, page: int) -> PageFacts:
    g = Grid(grid.page_rows(page))
    cls = classify(g)
    num = None
    for field, val, rank, _ in header_candidates(g, cls.doc_type, ("doc_number",)):
        num = val
        break
    text = g.text
    m = PAGE_OF.search(text)
    return PageFacts(page, cls.doc_type, cls.confidence, num,
                     (int(m[1]), int(m[2])) if m else None,
                     bool(CONTINUED.search(text)), bool(CONTINUES.search(text)))


def split_pages(grid: Grid, pages: list[int]) -> tuple[list[list[int]], list[str]]:
    """Groups a PDF's pages into documents. Returns groups and the evidence for each cut."""
    if len(pages) <= 1:
        return [pages], []
    facts = [page_facts(grid, p) for p in pages]
    groups, cur, why = [], [facts[0].page], []
    for prev, nxt in zip(facts, facts[1:]):
        cut, reason = _boundary(prev, nxt)
        if cut:
            groups.append(cur)
            cur = [nxt.page]
            why.append(f"new document at page {nxt.page}: {reason}")
        else:
            cur.append(nxt.page)
    groups.append(cur)
    return groups, why


def _boundary(prev: PageFacts, nxt: PageFacts) -> tuple[bool, str]:
    # evidence against a cut, strongest first
    if nxt.continued:
        return False, "next page says it continues"
    if prev.continues:
        return False, "page says it continues overleaf"
    if prev.page_of and prev.page_of[0] < prev.page_of[1] and not (nxt.page_of and nxt.page_of[0] == 1):
        return False, f"page {prev.page_of[0]} of {prev.page_of[1]}"
    # evidence for a cut
    if nxt.page_of and nxt.page_of[0] == 1:
        return True, "page numbering restarts"
    titled = nxt.doc_type != DocType.UNKNOWN and nxt.title_strength >= 0.8
    if titled and nxt.number and prev.number and nxt.number != prev.number:
        return True, f"document number changes {prev.number} -> {nxt.number}"
    if titled and nxt.doc_type != prev.doc_type and prev.doc_type != DocType.UNKNOWN:
        return True, f"document type changes {prev.doc_type.value} -> {nxt.doc_type.value}"
    return False, "no strong evidence of a new document"


# ------------------------------------------------------------------ join across files
def join_continuations(docs: list[ReadDocument]) -> list[ReadDocument]:
    """Attaches a continuation page that arrived as its own file to the document it continues."""
    out = list(docs)
    for d in docs:
        if "continuation" not in d.notes:
            continue
        num = d.value("doc_number")
        candidates = [p for p in out if p is not d and "continuation" not in p.notes
                      and p.doc_type == d.doc_type and p.value("doc_number")]
        # the continuation names its parent: by its own number, or by the parent's number in its text
        parent = next((p for p in candidates if num and p.value("doc_number") == num), None) or next(
            (p for p in candidates if re.search(r"(?<![\w-])" + re.escape(str(p.value("doc_number"))) + r"(?![\w-])",
                                                d.raw_text)), None)
        if parent is None:
            d.notes.append("continues a document that has not arrived")
            continue
        parent.sources += d.sources
        parent.lines += [l for l in d.lines if l not in parent.lines]
        for k, v in d.fields.items():
            parent.fields.setdefault(k, v)
        parent.notes.append(f"joined continuation {d.sources[0].file}")
        out.remove(d)
    return out

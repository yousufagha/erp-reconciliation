"""Step 2: text-layer PDFs, per-type checks, and the first two questions of the gate."""
from pathlib import Path

import pytest

from pile import harness
from pile.extract import Context
from pile.models import DocType, FieldValue, ReadDocument, SourceRef
from pile.pdf_text import pdf_grid
from pile.pipeline import gate, run
from pile.validate import check

ROOT = Path(__file__).resolve().parent.parent
SYN = ROOT / "corpus" / "synthetic" / "scenario_aug2026"
PUB = ROOT / "corpus" / "public" / "invoice2data"


@pytest.fixture(scope="module")
def syn_docs():
    return {d.sources[0].file: d for d in run(SYN)}


def test_columns_recovered_from_positions_not_whitespace():
    g = pdf_grid((SYN / "HS-88214.pdf").read_bytes())
    row = next(r for r in g.rows if r.texts and r.texts[0] == "STL-UB-310-46")
    assert row.texts == ["STL-UB-310-46", "UB 310x46 Grade 300PLUS 9.0m", "4.990", "t", "1,840.00", "9,181.60"]


def test_single_document_text_pdfs_read_and_balance(syn_docs):
    """Every one-document born-digital PDF reads with its own arithmetic intact."""
    truth = harness.load_truth(SYN)
    singles = [t for t in truth["documents"] if t["format"] == "pdf_text" and t["doc_type"] != "unknown"]
    for t in singles:
        d = syn_docs[t["files"][0]]
        assert d.status == "read", (t["id"], d.notes)
        assert d.doc_type.value == t["doc_type"], t["id"]


def test_two_page_invoice_reads_lines_from_both_pages(syn_docs):
    d = syn_docs["HS-88302.pdf"]
    assert len(d.lines) == 2 and d.status == "read"


def test_arithmetic_failure_holds_the_document():
    d = ReadDocument([SourceRef("x.pdf")], DocType.SUPPLIER_INVOICE,
                     {"subtotal": FieldValue(100.0), "gst": FieldValue(10.0), "total": FieldValue(111.0),
                      "supplier_abn": FieldValue("51 824 753 556")},
                     [{"quantity": 2, "unit_price": 50.0, "amount": 100.0}], printed_label="TAX INVOICE")
    gate(d, Context(buyer_abn="51 824 753 556"))
    assert d.status == "held"
    assert any("subtotal plus GST" in n for n in d.notes)


def test_empty_reading_is_never_accepted():
    d = ReadDocument([SourceRef("x.pdf")], DocType.SUPPLIER_INVOICE, printed_label="TAX INVOICE")
    gate(d, Context())
    assert d.status == "held"


def test_ato_rules_are_compliance_not_reading_failures():
    d = ReadDocument([SourceRef("x.pdf")], DocType.SUPPLIER_INVOICE,
                     {"subtotal": FieldValue(1000.0), "gst": FieldValue(100.0), "total": FieldValue(1100.0),
                      "date": FieldValue("2026-08-01")},
                     [{"quantity": 1, "unit_price": 1000.0, "amount": 1000.0}], printed_label="INVOICE")
    failed = {c.name: c.kind for c in check(d, d.printed_label) if not c.passed}
    assert failed == {"seller ABN shown and valid": "compliance", "marked as a tax invoice": "compliance",
                      "buyer identified (sales of $1,000 or more)": "compliance"}
    gate(d, Context())
    assert d.status == "read"


def test_statement_balances(syn_docs):
    for f in ("Harbourline_statement_Aug26.pdf", "Boltmaster_statement_2026-08.xlsx", "SGWS_statement_20260831.csv"):
        d = syn_docs[f]
        assert d.doc_type == DocType.STATEMENT and d.status == "read", (f, d.notes)
        assert any(c.name == "entries sum to closing balance" and c.passed for c in d.checks)


def test_public_invoices_floor():
    """Real invoices from other countries and languages. A floor, not a target: the
    deterministic reader must not regress; the model path is expected to lift it."""
    sc = harness.score(harness.load_truth(PUB), [d.to_json() for d in run(PUB)], gated=False)
    assert sc.by_format["pdf_text"].pct >= 30


def test_no_wrong_value_is_accepted_as_fact():
    """The no-guess rule, measured: across both corpora, every header value the gate accepts
    as fact is right. Values it cannot establish are left blank or flagged, never guessed."""
    for corpus in (SYN, PUB):
        gq = harness.gate_quality(harness.load_truth(corpus), [d.to_json() for d in run(corpus)])
        assert gq["accepted"]["wrong"] == 0, gq["accepted"]["wrong_values"]


def test_ambiguous_dates_are_flagged_not_assumed():
    from pile.dates import ambiguous_dates, order_evidence
    from pile.extract import Context
    d = ReadDocument([SourceRef("x.pdf")], DocType.SUPPLIER_INVOICE,
                     {"date": FieldValue("2026-04-03", printed="03/04/2026")}, raw_text="Invoice date 03/04/2026")
    assert [k for k, _ in ambiguous_dates(d, Context())] == ["date"]
    d.raw_text += "  Due 17/04/2026"                       # another date proves day-first
    assert ambiguous_dates(d, Context()) == []
    assert order_evidence("04/17/2026") == "monthfirst"


def test_supplier_name_never_comes_from_the_first_line(tmp_path):
    """Without a label, the supplier list or a company-looking letterhead, the name stays blank."""
    from pile.extract import Context, extract
    from pile.layout import Grid, Row
    g = Grid([Row(["Global Wholesaler"]), Row(["TAX INVOICE"]), Row(["Invoice No", "A-1"])])
    fields, _ = extract(g, DocType.SUPPLIER_INVOICE, Context())
    assert "supplier_name" not in fields

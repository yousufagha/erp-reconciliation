"""Step 4: chains and the three pendencies.

The gate is tested in two halves so a reading error cannot hide a resolution error:
  1. fed a perfect reading (the truth itself), resolution must reproduce every seeded figure;
  2. fed the real pipeline, every discrepancy must trace to a document the pipeline could not read.
"""
from pathlib import Path

import pytest

from pile import harness
from pile.models import DocType, FieldValue, ReadDocument, SourceRef
from pile.pipeline import run
from pile.resolve import line_matches, resolve

SYN = Path(__file__).resolve().parent.parent / "corpus" / "synthetic" / "scenario_aug2026"
TRUTH = harness.load_truth(SYN)
REGISTERS = ("goods_owed", "paperwork_owed", "invoiced_not_received", "money_owed", "exceptions")


def perfect_docs():
    return [ReadDocument([SourceRef(f) for f in t["files"]], DocType(t["doc_type"]),
                         {k: FieldValue(v) for k, v in t["fields"].items() if v is not None},
                         [dict(l) for l in t["lines"]], status="read" if t["doc_type"] != "unknown" else "held")
            for t in TRUTH["documents"]]


def test_gate_perfect_reading_reproduces_every_seeded_figure():
    sc = harness.score_reconciliation(TRUTH["reconciliation"], resolve(perfect_docs()).to_json())
    assert sc["invoice_to_po"]["right"] == sc["invoice_to_po"]["truth"], sc["invoice_to_po"]["wrong"]
    for reg in REGISTERS:
        assert sc[reg]["recall"] == 100 and sc[reg]["precision"] == 100, (reg, sc[reg])


def test_real_pipeline_errors_all_trace_to_unread_documents():
    docs = run(SYN)
    res = resolve(docs)
    sc = harness.score_reconciliation(TRUTH["reconciliation"], res.to_json())
    for reg in REGISTERS[:-1]:
        assert sc[reg]["recall"] == 100, (reg, sc[reg]["wrong"])
    unread_truth = [t for t in TRUTH["documents"] if any(f in {u["source"] for u in res.unread} for f in t["files"])]
    unread_pos = {t["fields"].get("po_reference") for t in unread_truth if t["doc_type"] == "goods_receipt"}
    for e in sc["goods_owed"]["unexpected"] + sc["invoiced_not_received"]["unexpected"]:
        assert e[0] in unread_pos, e       # only POs whose delivery record is in an unread file
    assert {tuple(e) for e in sc["exceptions"]["unexpected"]} <= {
        ("missing_receipt", t["fields"]["doc_number"]) for t in TRUTH["documents"]
        if t["doc_type"] == "supplier_invoice" and t["fields"].get("po_reference") in unread_pos} | {
        ("missing_receipt", "SG-77120")}     # quotes no PO; its docket is in the scanner batch
    # a duplicate can only be seen if both copies are read; the missed one has a copy in a photo
    unread_numbers = {t["fields"].get("doc_number") for t in unread_truth}
    for miss in sc["exceptions"]["wrong"]:
        assert miss["key"][0] == "duplicate_suspected" and miss["key"][1] in unread_numbers, miss


def test_invoice_without_po_number_is_linked_by_score_not_trust():
    res = resolve(run(SYN))
    assert res.invoice_to_po["SG-77120"] == "PO-4107"
    assert res.link_scores["SG-77120"] >= 0.85
    assert res.invoice_to_po["CC-10497"] is None


def test_po_number_quoted_by_another_supplier_is_not_trusted():
    po = ReadDocument([SourceRef("po.pdf")], DocType.PURCHASE_ORDER,
                      {"doc_number": FieldValue("PO-1"), "supplier_name": FieldValue("Alpha Steel Pty Ltd"),
                       "subtotal": FieldValue(100.0), "date": FieldValue("2026-08-01")},
                      [{"sku": "A1", "description": "Widget", "quantity": 10, "unit_price": 10.0, "amount": 100.0}])
    inv = ReadDocument([SourceRef("inv.pdf")], DocType.SUPPLIER_INVOICE,
                       {"doc_number": FieldValue("Z-9"), "supplier_name": FieldValue("Zeta Plumbing Pty Ltd"),
                        "po_reference": FieldValue("PO-1"), "subtotal": FieldValue(900.0), "total": FieldValue(990.0),
                        "date": FieldValue("2026-08-05")},
                      [{"sku": "Q7", "description": "Valve", "quantity": 1, "unit_price": 900.0, "amount": 900.0}])
    res = resolve([po, inv])
    assert res.invoice_to_po["Z-9"] is None
    assert any(e.bucket == "no_matching_po" and e.document == "Z-9" for e in res.exceptions)


def test_line_matching():
    assert line_matches({"sku": "STL-UB-310-46"}, {"sku": "stl ub 310 46"}) == 1.0
    assert line_matches({"description": "Mixed gas [SG-MIX-G]"}, {"sku": "SG-MIX-G"}) == 0.95
    assert line_matches({"sku": "A"}, {"sku": "B"}) == 0.0

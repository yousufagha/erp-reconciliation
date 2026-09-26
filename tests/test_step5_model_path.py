"""Step 5: the model path, tested with a stand-in model so it runs without a key.

The stand-in returns what a model would: printed values, as printed. The tests check
what this code does with them: grounding against an independent OCR reading, holding
anything not found on the page, and feeding resolution. The live Gemini run is a
separate evaluation on the Mac (see docs/02-model-testing.md).
"""
from pathlib import Path

import pytest

from pile import model_read, ocr
from pile.pipeline import run
from pile.resolve import resolve

SYN = Path(__file__).resolve().parent.parent / "corpus" / "synthetic" / "scenario_aug2026"
pytestmark = pytest.mark.skipif(not ocr.available(), reason="Tesseract not installed")

DOCKET = {"doc_type": "goods_receipt", "printed_title": "DELIVERY DOCKET", "continues_previous": False,
          "fields": {"supplier_name": "Harbourline Steel Supply Pty Ltd", "doc_number": "DD-55120",
                     "date": "07/08/2026", "po_reference": "PO-4101"},
          "lines": [{"sku": "STL-UB-310-46", "description": "UB 310x46 Grade 300PLUS 9.0m", "quantity": "4.990"},
                    {"sku": "STL-RHS-100-5G", "description": "RHS 100x100x5.0 Galvanised", "quantity": "0.860"},
                    {"sku": "STL-PL-12-300", "description": "Plate 12mm Grade 300PLUS", "quantity": "1.240"}]}


class StandIn:
    name = "stand-in"

    def __init__(self, docket):
        self.docket = docket

    def read_page(self, image_jpeg):
        return self.docket


@pytest.fixture
def model(request):
    model_read.OVERRIDE = StandIn(request.param)
    yield
    model_read.OVERRIDE = None


def _docket(docs):
    return next(d for d in docs if d.sources[0].file == "IMG_20260807_143055.jpg")


@pytest.mark.parametrize("model", [DOCKET], indirect=True)
def test_a_correct_reading_is_grounded_and_closes_the_chain(model):
    docs = run(SYN)
    d = _docket(docs)
    assert d.status in ("read", "flagged"), d.notes
    assert d.fields["doc_number"].grounded is True and d.fields["po_reference"].grounded is True
    res = resolve(docs)
    assert not [g for g in res.goods_owed if g["po"] == "PO-4101"]          # the docket closed PO-4101
    assert not [e for e in res.exceptions if e.bucket == "missing_receipt" and e.document == "HS-88214"]


FABRICATED = {**DOCKET, "lines": [dict(DOCKET["lines"][0], quantity="5.990")] + DOCKET["lines"][1:]}


@pytest.mark.parametrize("model", [FABRICATED], indirect=True)
def test_a_quantity_not_on_the_page_holds_the_document(model):
    d = _docket(run(SYN))
    assert d.status == "held"
    assert any("5.990" in n for n in d.notes)


WRONG_NUMBER = {**DOCKET, "fields": dict(DOCKET["fields"], doc_number="DD-55126")}


@pytest.mark.parametrize("model", [WRONG_NUMBER], indirect=True)
def test_an_ungrounded_document_number_is_capped_and_blocks(model):
    d = _docket(run(SYN))
    assert d.fields["doc_number"].grounded is False
    assert d.fields["doc_number"].confidence <= 0.35
    assert d.status == "held" and d.fields["doc_number"].blocked_on == "extraction_quality"


class Down:
    name = "down"

    def read_page(self, image_jpeg):
        raise TimeoutError("model unavailable")


def test_an_outage_is_reported_never_passed_off_as_a_reading():
    model_read.OVERRIDE = Down()
    try:
        d = _docket(run(SYN))
    finally:
        model_read.OVERRIDE = None
    assert d.status == "held" and "model call failed" in d.notes[-1]


def test_without_a_model_images_are_held_but_labelled():
    d = _docket(run(SYN))
    assert d.status == "held"
    assert d.value("po_reference") == "PO-4101"            # provisional, from OCR, for the report only
    res = resolve(run(SYN))
    e = next(e for e in res.exceptions if e.bucket == "missing_receipt" and e.document == "HS-88214")
    assert "DD-55120" in e.headline

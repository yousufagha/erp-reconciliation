"""Step 1: intake, dedupe, profile, and the formats that carry their own structure."""
from pathlib import Path

import pytest

from pile import harness, layout
from pile.classify import classify
from pile.intake import intake
from pile.models import DocType
from pile.normalise import abn_valid, find_abns, parse_date, parse_money
from pile.pipeline import run
from pile.profile import profile

ROOT = Path(__file__).resolve().parent.parent
SYN = ROOT / "corpus" / "synthetic" / "scenario_aug2026"
EXACT = {"csv", "docx", "eml_body", "ubl_xml", "xlsx"}


@pytest.fixture(scope="module")
def synthetic_score():
    return harness.score(harness.load_truth(SYN), [d.to_json() for d in run(SYN)])


def test_gate_exact_formats_read_completely(synthetic_score):
    for fmt in EXACT:
        t = synthetic_score.by_format[fmt]
        assert t.total > 0 and t.right == t.total, f"{fmt}: {t.right}/{t.total}"


def test_email_is_a_container_not_a_document():
    refs = {it.ref for it in intake(SYN)}
    assert "remittance_RA-9001.eml#RA-9001.pdf" in refs
    assert "remittance_RA-9003.eml#body" in refs          # remittance typed into the email
    assert "remittance_RA-9001.eml#body" not in refs      # a covering note is not a document


def test_config_and_truth_are_not_documents():
    refs = {it.ref for it in intake(SYN)}
    assert "truth.json" not in refs and "context.json" not in refs


def test_profile_tells_scans_from_born_digital():
    items = {it.ref: it for it in intake(SYN)}
    assert profile(items["scan_frontdesk_0826.pdf"]).image_pages == [1, 2]
    assert profile(items["HS-88214.pdf"]).text_pages == [1]
    assert profile(items["IMG_20260807_143055.jpg"]).kind == "image"
    assert profile(items["BF-INV-30602.xml"]).kind == "ubl"


def test_byte_identical_copies_are_read_once(tmp_path):
    data = (SYN / "GRN-7006.xlsx").read_bytes()
    (tmp_path / "a.xlsx").write_bytes(data)
    (tmp_path / "b.xlsx").write_bytes(data)
    docs = run(tmp_path)
    assert [d.status for d in docs].count("duplicate") == 1


def test_classification_prefers_titles_over_mentions():
    def g(*lines):
        return layout.Grid([layout.Row([l]) for l in lines])
    assert classify(g("Acme Pty Ltd", "TAX INVOICE", "Purchase Order: PO-1")).doc_type == DocType.SUPPLIER_INVOICE
    assert classify(g("TAX CREDIT NOTE", "Original invoice: INV-9")).doc_type == DocType.CREDIT_NOTE
    assert classify(g("DELIVERY DOCKET", "This is not a tax invoice.")).doc_type == DocType.GOODS_RECEIPT
    assert classify(g("PURCHASE ORDER", "Please quote the invoice number")).doc_type == DocType.PURCHASE_ORDER
    assert classify(g("Safety data sheet", "Zinc dust 60-80%")).doc_type == DocType.UNKNOWN


def test_parsers():
    assert parse_money("$1,234.56") == 1234.56
    assert parse_money("(609.84)") == -609.84
    assert parse_money("609.84 CR") == -609.84
    assert parse_money("1.234,56") == 1234.56
    assert parse_date("07/08/2026") == "2026-08-07"      # day first
    assert parse_date("03/20/2023") == "2023-03-20"      # only works month first
    assert parse_date("9 Aug 2026") == "2026-08-09"
    assert parse_date("02 Juillet 2015") == "2015-07-02"
    assert abn_valid("51 824 753 556")                    # ATO's published example ABN
    assert not abn_valid("51 824 753 557")
    assert find_abns("ABN 51 824 753 556, ph 03 9555 1234") == ["51 824 753 556"]

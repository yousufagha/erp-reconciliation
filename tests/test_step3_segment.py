"""Step 3: splitting files into documents and joining documents spread over files."""
from pathlib import Path

from pile.models import DocType
from pile.pipeline import run
from pile.segment import PageFacts, _boundary

SYN = Path(__file__).resolve().parent.parent / "corpus" / "synthetic" / "scenario_aug2026"


def pf(page, dt=DocType.SUPPLIER_INVOICE, strength=0.95, number="INV-1", page_of=None, continued=False, continues=False):
    return PageFacts(page, dt, strength, number, page_of, continued, continues)


def test_pack_is_split_where_the_document_number_changes():
    docs = [d for d in run(SYN) if d.sources[0].file == "Boltmaster_documents_Aug.pdf"]
    assert [(d.sources[0].pages, d.doc_type.value, d.value("doc_number")) for d in docs] == [
        ([1], "goods_receipt", "BF-20931"), ([2], "supplier_invoice", "BF-INV-30551"), ([3], "goods_receipt", "BF-21007")]


def test_page_one_of_two_is_never_split():
    docs = [d for d in run(SYN) if d.sources[0].file == "HS-88302.pdf"]
    assert len(docs) == 1 and docs[0].sources[0].pages == [1, 2]


def test_page_two_sent_as_its_own_file_is_joined():
    d = next(d for d in run(SYN) if d.value("doc_number") == "BF-INV-30688")
    assert [s.file for s in d.sources] == ["BF-INV-30688.pdf", "BF-INV-30688_page2.pdf"]
    assert d.value("total") == 1727.0 and d.status == "read"


def test_weak_evidence_keeps_pages_together():
    # the same title repeated with the same number: one document printed over two pages
    assert _boundary(pf(1), pf(2))[0] is False
    # an untitled page following an invoice: keep it with the invoice
    assert _boundary(pf(1), pf(2, DocType.UNKNOWN, 0.0, None))[0] is False
    # explicit continuation markers win over everything
    assert _boundary(pf(1, continues=True), pf(2, number="INV-2"))[0] is False


def test_strong_evidence_splits():
    assert _boundary(pf(1, number="INV-1"), pf(2, number="INV-2"))[0] is True
    assert _boundary(pf(1, page_of=(1, 1)), pf(2, page_of=(1, 1), number="INV-1"))[0] is True
    assert _boundary(pf(1), pf(2, DocType.GOODS_RECEIPT, 0.95, None))[0] is True

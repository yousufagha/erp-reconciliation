"""The harness is the gate for every later step, so it is tested first."""
import json
from pathlib import Path

import pytest

from pile import harness
from pile.cli import main

ROOT = Path(__file__).resolve().parent.parent
SYN = ROOT / "corpus" / "synthetic" / "scenario_aug2026"
PUB = ROOT / "corpus" / "public" / "invoice2data"


def perfect(truth):
    """A prediction that copies the truth exactly."""
    preds = []
    for t in truth["documents"]:
        srcs = [{"file": f, "pages": (t.get("pages") or {}).get(f)} for f in t["files"]]
        preds.append({"sources": srcs, "doc_type": t["doc_type"], "fields": dict(t["fields"]),
                      "lines": [dict(l) for l in t["lines"]], "status": "read"})
    return preds


@pytest.mark.parametrize("corpus", [SYN, PUB])
def test_perfect_prediction_scores_100(corpus):
    truth = harness.load_truth(corpus)
    sc = harness.score(truth, perfect(truth))
    assert sc.documents.pct == 100 and sc.doc_type.pct == 100
    assert sc.headers.pct == 100
    if sc.lines.total:
        assert sc.lines.pct == 100
    if sc.packets.total:
        assert sc.packets.pct == 100


@pytest.mark.parametrize("corpus", [SYN, PUB])
def test_trivial_reader_scores_zero(corpus, capsys):
    """Step 0 gate: a reader that reads nothing must score nothing."""
    out = ROOT / "tmp_score.json"
    main(["eval", str(corpus), "--reader", "trivial", "--json", str(out)])
    res = json.loads(out.read_text())[str(corpus)]
    out.unlink()
    assert res["headers"]["right"] == 0
    assert res["lines"]["right"] == 0
    # 'unknown' documents are typed correctly by accident; nothing else is
    assert res["doc_type"]["right"] <= sum(1 for d in harness.load_truth(corpus)["documents"] if d["doc_type"] == "unknown")


def test_one_wrong_value_costs_exactly_one_field():
    truth = harness.load_truth(SYN)
    preds = perfect(truth)
    preds[0]["fields"]["total"] = 1.23
    sc = harness.score(truth, preds)
    assert sc.headers.total - sc.headers.right == 1


def test_value_rules():
    m = harness.values_match
    assert m("total", 15331.20, "15,331.20")
    assert m("total", 15331.20, "$15,331.2")
    assert not m("total", 15331.20, "15,331.21")
    assert m("total", -609.84, "(609.84)")
    assert m("date", "2026-08-07", "07/08/2026")          # AU day-first
    assert m("date", "2026-08-09", "9 Aug 2026")
    assert m("supplier_name", "Harbourline Steel Supply Pty Ltd", "HARBOURLINE STEEL SUPPLY PTY. LTD.")
    assert m("supplier_abn", "30 641 119 820", "30641119820")
    assert not m("doc_number", "HS-88214", "HS-88215")
    assert not m("total", 10.0, None)


def test_split_files_must_match_exactly():
    truth = {"documents": [
        {"files": ["pack.pdf"], "pages": {"pack.pdf": [1]}, "doc_type": "goods_receipt", "fields": {}},
        {"files": ["pack.pdf"], "pages": {"pack.pdf": [2, 3]}, "doc_type": "supplier_invoice", "fields": {}},
    ]}
    right = [{"sources": [{"file": "pack.pdf", "pages": [1]}], "doc_type": "goods_receipt", "fields": {}},
             {"sources": [{"file": "pack.pdf", "pages": [2, 3]}], "doc_type": "supplier_invoice", "fields": {}}]
    oversplit = [{"sources": [{"file": "pack.pdf", "pages": [1]}], "doc_type": "goods_receipt", "fields": {}},
                 {"sources": [{"file": "pack.pdf", "pages": [2]}], "doc_type": "supplier_invoice", "fields": {}},
                 {"sources": [{"file": "pack.pdf", "pages": [3]}], "doc_type": "supplier_invoice", "fields": {}}]
    assert harness.score(truth, right).packets.pct == 100
    assert harness.score(truth, oversplit).packets.pct == 0

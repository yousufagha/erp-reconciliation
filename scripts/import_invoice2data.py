"""Builds corpus/public/invoice2data from a clone of github.com/invoice-x/invoice2data.

Real invoices from real companies, published as that project's test set with
expected output (MIT licence). Their answers cover header fields only, and not
every field for every invoice; the harness scores only what the truth states.

Usage: python scripts/import_invoice2data.py <path-to-invoice2data-clone>
"""
import json
import shutil
import sys
from pathlib import Path

SKIP = {"Orlen", "SammyMaystoneLinesTest"}  # text-only input; synthetic lines fixture

FIELD_MAP = {"issuer": "supplier_name", "invoice_number": "doc_number", "date": "date",
             "amount": "total", "amount_untaxed": "subtotal"}


def main(clone: Path) -> None:
    src = clone / "tests" / "compare"
    out = Path(__file__).resolve().parent.parent / "corpus" / "public" / "invoice2data"
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy(clone / "LICENSE.md", out / "LICENSE-invoice2data.md")
    docs = []
    for js in sorted(src.glob("*.json")):
        stem = js.stem
        if stem in SKIP:
            continue
        expected = json.loads(js.read_text())[0]
        fields = {ours: expected[theirs] for theirs, ours in FIELD_MAP.items() if theirs in expected}
        lines = []
        for ln in expected.get("lines", []):
            if "name" not in ln:
                continue  # note-only rows
            lines.append({k2: ln[k1] for k1, k2 in (("name", "description"), ("qty", "quantity"),
                          ("price_unit", "unit_price"), ("price_subtotal", "amount")) if k1 in ln})
        for ext, fmt in ((".pdf", "pdf_text"), (".png", "image")):
            f = src / f"{stem}{ext}"
            if not f.exists():
                continue
            shutil.copy(f, out / f.name)
            docs.append({"id": f"{stem}{ext}", "files": [f.name], "pages": None,
                         "doc_type": "supplier_invoice", "format": fmt,
                         "fields": fields, "lines": lines})
    (out / "truth.json").write_text(json.dumps({
        "source": "https://github.com/invoice-x/invoice2data/tree/master/tests/compare",
        "licence": "MIT",
        "note": "Header answers as published by invoice2data. PNGs are page renders of the same PDFs.",
        "documents": docs}, indent=2))
    print(f"{len(docs)} documents -> {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))

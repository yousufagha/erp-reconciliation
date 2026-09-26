"""Command line.

    pile read <folder> [-o out.json] [--reader NAME]   read a pile, write what was found
    pile eval <corpus_dir> [--reader NAME]             read a corpus and score it against truth.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import harness
from .readers import READERS


def _read(folder: Path, reader: str) -> list[dict]:
    return [d.to_json() for d in READERS[reader](folder)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pile")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("read")
    r.add_argument("folder", type=Path)
    r.add_argument("-o", "--out", type=Path)
    r.add_argument("--reader", default="pipeline", choices=sorted(READERS))
    e = sub.add_parser("eval")
    e.add_argument("corpus", type=Path, nargs="+")
    e.add_argument("--reader", default="pipeline", choices=sorted(READERS))
    e.add_argument("--json", type=Path, help="write the full score here")
    e.add_argument("--misses", action="store_true", help="print every wrong field")
    a = ap.parse_args(argv)

    if a.cmd == "read":
        docs = _read(a.folder, a.reader)
        text = json.dumps(docs, indent=2, default=str)
        (a.out.write_text(text) if a.out else sys.stdout.write(text + "\n"))
        return 0

    results = {}
    for corpus in a.corpus:
        preds = _read(corpus, a.reader)
        sc = harness.score(harness.load_truth(corpus), preds)
        results[str(corpus)] = sc.to_json()
        print(harness.format_report(f"{corpus} [{a.reader}]", sc))
        if a.misses:
            print("  misses:\n    " + "\n    ".join(sc.misses))
    if a.json:
        a.json.write_text(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

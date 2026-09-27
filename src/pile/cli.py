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
    s = sub.add_parser("status", help="read a pile and report the status of the paperwork and the goods")
    s.add_argument("folder", type=Path)
    s.add_argument("--json", type=Path)
    a = ap.parse_args(argv)

    if a.cmd == "status":
        from .pipeline import run
        from .report import render
        from .resolve import resolve
        res = resolve(run(a.folder))
        print(render(res))
        if a.json:
            a.json.write_text(json.dumps(res.to_json(), indent=2, default=str))
        return 0

    if a.cmd == "read":
        docs = _read(a.folder, a.reader)
        text = json.dumps(docs, indent=2, default=str)
        (a.out.write_text(text) if a.out else sys.stdout.write(text + "\n"))
        return 0

    results = {}
    for corpus in a.corpus:
        truth = harness.load_truth(corpus)
        if a.reader == "pipeline":
            from .pipeline import run
            from .resolve import resolve
            docs = run(corpus)
            preds = [d.to_json() for d in docs]
        else:
            preds = _read(corpus, a.reader)
        sc = harness.score(truth, preds, gated=False)
        gq = harness.gate_quality(truth, preds)
        results[str(corpus)] = sc.to_json() | {"gate": gq}
        print(harness.format_report(f"{corpus} [{a.reader}]", sc))
        ac, fl = gq["accepted"], gq["flagged"]
        print(f"  gate: accepted {ac['values']} of {gq['total_fields']} header values as fact: {ac['right']} right, "
              f"{ac['wrong']} wrong, {ac['left_blank']} left blank rather than guessed")
        print(f"        flagged {fl['values']} more for a person to confirm: {fl['right']} right, {fl['wrong']} wrong")
        for w in ac["wrong_values"]:
            print(f"        ACCEPTED BUT WRONG: {w}")
        failed = [f"{p['sources'][0]['file']}: {n}" for p in preds for n in p.get("notes", []) if "model call failed" in n]
        if failed:
            print(f"  model calls failed: {len(failed)}")
            for f in failed[:10]:
                print(f"    {f[:220]}")
        results[str(corpus)]["model_call_failures"] = failed
        if "reconciliation" in truth and a.reader == "pipeline":
            rsc = harness.score_reconciliation(truth["reconciliation"], resolve(docs).to_json())
            results[str(corpus)]["reconciliation"] = rsc
            print(harness.format_reconciliation(rsc))
        if a.misses:
            print("  misses:\n    " + "\n    ".join(sc.misses))
    if a.json:
        a.json.write_text(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

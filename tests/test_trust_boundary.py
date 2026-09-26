"""The one architectural rule: the model reads and the model explains; it never decides.

Deciding code (matching, arithmetic, confidence, the gate, pendency) must not be able to
reach a model client. This walks each module's imports and fails the build if one can.
A new model call anywhere needs a deliberate entry in MAY_CALL_A_MODEL.
"""
import ast
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "src" / "pile"
MAY_CALL_A_MODEL = {"model_read.py"}                    # the only file allowed to import a model client
DECIDING = {"resolve.py", "validate.py", "confidence.py", "segment.py", "extract.py", "classify.py",
            "harness.py", "dates.py", "report.py", "normalise.py"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            mod = ("." * node.level) + (node.module or "")
            out.add(mod)
            out |= {f"{mod}.{a.name}" for a in node.names}
    return out


def test_only_model_read_imports_a_model_client():
    for f in PKG.rglob("*.py"):
        rel = str(f.relative_to(PKG))
        hits = {i for i in _imports(f) if i.split(".")[0] in {"google", "anthropic", "openai"}}
        if rel not in MAY_CALL_A_MODEL:
            assert not hits, f"{rel} imports a model client: {hits}"


def test_deciding_code_cannot_reach_the_model_reader():
    for rel in DECIDING:
        imps = _imports(PKG / rel)
        bad = {i for i in imps if "model_read" in i or "image_read" in i}
        assert not bad, f"{rel} can reach the model path: {bad}"

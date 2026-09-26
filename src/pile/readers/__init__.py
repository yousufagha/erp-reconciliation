"""Reader registry. Each reader takes a folder and returns ReadDocuments."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..intake import intake
from ..models import DocType, ReadDocument, SourceRef


def trivial(folder: Path) -> list[ReadDocument]:
    """Reads nothing. One held document per item. The harness must score this at zero."""
    return [ReadDocument(sources=[SourceRef(it.ref)], doc_type=DocType.UNKNOWN, reader="trivial", status="held")
            for it in intake(folder)]


def pipeline(folder: Path) -> list[ReadDocument]:
    from ..pipeline import run
    return run(folder)


READERS: dict[str, Callable[[Path], list[ReadDocument]]] = {"trivial": trivial, "pipeline": pipeline}

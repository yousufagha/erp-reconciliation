"""Step 2: PDF text layer. Not built yet; PDFs are held."""
from __future__ import annotations

from .models import DocType, ReadDocument, SourceRef


def read_pdf(item, prof, ctx):
    return [ReadDocument([SourceRef(item.ref)], DocType.UNKNOWN, reader="none", status="held",
                         notes=["PDF reader is step 2"])]

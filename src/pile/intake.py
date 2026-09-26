"""Stage 1: intake. Raw files land and their provenance is recorded.

Email is unpacked here, because an email is a container, not a document: each
attachment becomes its own item addressed as "<file>.eml#<attachment name>", and
a body that carries content (a remittance typed into the email) becomes
"<file>.eml#body".
"""
from __future__ import annotations

import email
import hashlib
from dataclasses import dataclass, field
from email import policy
from pathlib import Path

IGNORED = {".json", ".md", ".py", ".DS_Store"}
BODY_MIN_CHARS = 120   # an email body shorter than this is a covering note, not content


@dataclass
class Item:
    ref: str                 # address used everywhere downstream
    name: str                # file name as it arrived (attachment name for attachments)
    data: bytes
    sha256: str
    origin: dict = field(default_factory=dict)   # sender, subject, date, container

    @property
    def ext(self) -> str:
        return Path(self.name).suffix.lower()


def _item(ref: str, name: str, data: bytes, origin: dict) -> Item:
    return Item(ref, name, data, hashlib.sha256(data).hexdigest(), origin)


def _unpack_eml(ref: str, data: bytes) -> list[Item]:
    msg = email.message_from_bytes(data, policy=policy.default)
    origin = {"container": ref, "from": str(msg.get("From", "")), "subject": str(msg.get("Subject", "")),
              "date": str(msg.get("Date", ""))}
    items: list[Item] = []
    attachments = list(msg.iter_attachments())
    for part in attachments:
        name = part.get_filename() or "attachment.bin"
        items.append(_item(f"{ref}#{name}", name, part.get_payload(decode=True) or b"", origin))
    body = msg.get_body(preferencelist=("plain", "html"))
    text = body.get_content() if body is not None else ""
    if len(text.strip()) >= BODY_MIN_CHARS or not attachments:
        items.append(_item(f"{ref}#body", "body.txt", text.encode(), origin))
    return items


def intake(folder: Path) -> list[Item]:
    items: list[Item] = []
    for p in sorted(folder.rglob("*")):
        if not p.is_file() or p.name.startswith(".") or p.suffix in IGNORED or p.name == "truth.json":
            continue
        ref = str(p.relative_to(folder))
        data = p.read_bytes()
        if p.suffix.lower() == ".eml":
            items.extend(_unpack_eml(ref, data))
        else:
            items.append(_item(ref, p.name, data, {"path": ref}))
    return items

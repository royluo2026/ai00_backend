"""Knowledge-owned opaque identifiers; no Base sequence dependency."""
from __future__ import annotations

import uuid


_PREFIXES = {
    "space": "kns",
    "document": "knd",
    "revision": "knr",
    "proposal": "knp",
    "outbox": "kno",
    "entry": "kne",
}


def new_knowledge_id(kind: str) -> str:
    try:
        prefix = _PREFIXES[kind]
    except KeyError as exc:
        raise ValueError("unknown Knowledge identifier kind") from exc
    return f"{prefix}_{uuid.uuid4().hex}"


__all__ = ["new_knowledge_id"]

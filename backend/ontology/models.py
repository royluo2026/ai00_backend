from __future__ import annotations

from dataclasses import dataclass


OBJECT_KINDS = frozenset({"concept", "property", "relation", "mapping", "constraint"})


@dataclass(frozen=True)
class OntologyRelease:
    release_gid: str
    content_sha256: str
    object_count: int
    parent_release_gid: str | None
    ois_object_key: str
    source: str
    source_gid: str | None = None

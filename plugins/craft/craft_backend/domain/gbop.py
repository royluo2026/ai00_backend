from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class GbopRelease:
    ref: str
    bop_commit_ref: str
    pbom_commit_ref: str
    knowledge_refs: tuple[str, ...]
    ontology_release_ref: str
    status: str = "published"

__all__ = ["GbopRelease"]

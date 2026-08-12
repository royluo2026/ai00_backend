from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class RuleRelease:
    ref: str
    rules: tuple[str, ...]
    knowledge_refs: tuple[str, ...]
    ontology_release_ref: str

@dataclass(frozen=True)
class RuleWaiver:
    ref: str
    release_ref: str
    violation: str
    reason: str
    revoked: bool = False

__all__ = ["RuleRelease", "RuleWaiver"]

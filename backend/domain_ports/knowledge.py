"""Public cross-domain Knowledge port; implementations remain Knowledge-owned."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence


@dataclass(frozen=True)
class KnowledgeDocumentRef:
    object_ref: str
    revision_ref: str
    title: str


@dataclass(frozen=True)
class KnowledgeContextRef:
    document_ref: str
    revision_ref: str
    summary: str
    retrieval_method: str


@dataclass(frozen=True)
class KnowledgeProposalRef:
    object_ref: str
    status: str


class KnowledgeQueryPort(Protocol):
    def search(self, query: str, *, limit: int, tenant_id: str, actor_id: str) -> Sequence[KnowledgeDocumentRef]: ...
    def retrieve_context(self, query: str, *, limit: int, tenant_id: str, actor_id: str) -> Sequence[KnowledgeContextRef]: ...


class KnowledgeCommandPort(Protocol):
    def propose(self, payload: Mapping[str, object], *, tenant_id: str, actor_id: str, idempotency_key: str) -> KnowledgeProposalRef: ...


class KnowledgeOperationsPort(Protocol):
    """Bounded operational view; callers never receive Knowledge database rows."""

    owner: str

    def health(self, context: object) -> Mapping[str, object]: ...


__all__ = [
    "KnowledgeCommandPort", "KnowledgeContextRef", "KnowledgeDocumentRef",
    "KnowledgeOperationsPort", "KnowledgeProposalRef", "KnowledgeQueryPort",
]

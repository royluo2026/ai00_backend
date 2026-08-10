"""Public references and ports owned by the Ontology domain."""
from __future__ import annotations

from typing import Literal, Protocol, Sequence

from pydantic import Field

from backend.capability_v2.contracts import FrozenModel, IDENTITY_PATTERN
from backend.capability_v2.revision.models import CommitRef


class OntologyVersionRef(FrozenModel):
    release_gid: str = Field(pattern=IDENTITY_PATTERN)
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    revision_ref: CommitRef | None = None


class ConceptRef(FrozenModel):
    concept_id: str = Field(pattern=IDENTITY_PATTERN)
    kind: Literal["concept", "property", "relation", "mapping", "constraint"] = "concept"
    ontology_version: OntologyVersionRef


class ImpactReference(FrozenModel):
    provider: Literal["agent", "craft", "digital_model", "plugins"]
    consumer_type: str = Field(min_length=1, max_length=64)
    consumer_id: str = Field(pattern=IDENTITY_PATTERN)
    ontology_object_id: str = Field(pattern=IDENTITY_PATTERN)
    status: Literal["resolved", "unresolved"] = "unresolved"


class ImpactReport(FrozenModel):
    activation_allowed: bool
    breaking_object_ids: tuple[str, ...] = ()
    unresolved: tuple[ImpactReference, ...] = ()
    missing_providers: tuple[str, ...] = ()


class OntologyImpactProvider(Protocol):
    name: str
    def references(self, ontology_object_ids: Sequence[str]) -> tuple[ImpactReference, ...]: ...


class OntologyDomainPort(Protocol):
    def resolve_concept(self, term: str, version: OntologyVersionRef | None = None) -> ConceptRef: ...
    def get_concept(self, ref: ConceptRef) -> dict: ...
    def analyze_impact(self, changes: Sequence[object]) -> ImpactReport: ...


__all__ = [
    "ConceptRef", "ImpactReference", "ImpactReport", "OntologyDomainPort",
    "OntologyImpactProvider", "OntologyVersionRef",
]

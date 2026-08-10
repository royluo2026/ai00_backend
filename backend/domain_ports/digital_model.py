"""Public references and application port owned by Digital Model."""
from __future__ import annotations

from typing import Mapping, Protocol, Sequence

from pydantic import Field

from backend.capability_v2.contracts import ArtifactRef, FrozenModel, IDENTITY_PATTERN
from backend.capability_v2.revision.models import CommitRef


class ModelRef(FrozenModel):
    model_id: str = Field(pattern=IDENTITY_PATTERN)
    object_ref: str = Field(pattern=r"^model:[A-Za-z0-9_.:@/-]+$")


class ModelVersionRef(FrozenModel):
    model_id: str = Field(pattern=IDENTITY_PATTERN)
    version_id: str = Field(pattern=IDENTITY_PATTERN)
    version_label: str = Field(min_length=1, max_length=128)
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    revision_ref: CommitRef | None = None


class ModelSnapshotRef(FrozenModel):
    model_id: str = Field(pattern=IDENTITY_PATTERN)
    version_id: str = Field(pattern=IDENTITY_PATTERN)
    snapshot_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    artifact_ref: ArtifactRef


class ComponentRef(FrozenModel):
    model_id: str = Field(pattern=IDENTITY_PATTERN)
    version_id: str = Field(pattern=IDENTITY_PATTERN)
    component_id: str = Field(pattern=IDENTITY_PATTERN)


class DigitalModelQueryPort(Protocol):
    def get_snapshot(self, ref: ModelSnapshotRef, *, tenant_id: str, actor_id: str) -> Mapping[str, object]: ...
    def search_components(self, model_id: str, version_id: str, query: str, *, limit: int, tenant_id: str, actor_id: str) -> Sequence[ComponentRef]: ...


__all__ = [
    "ComponentRef", "DigitalModelQueryPort", "ModelRef", "ModelSnapshotRef",
    "ModelVersionRef",
]

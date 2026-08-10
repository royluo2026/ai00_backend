"""Public immutable references and application ports owned by Simulation."""
from __future__ import annotations

from typing import Any, Mapping, Protocol

from pydantic import Field

from backend.capability_v2.contracts import ArtifactRef, FrozenModel, IDENTITY_PATTERN


HASH_PATTERN = r"^sha256:[0-9a-f]{64}$"


class ExecutionPlanRef(FrozenModel):
    version_gid: str = Field(pattern=IDENTITY_PATTERN)
    revision: int = Field(ge=1)
    content_hash: str = Field(pattern=HASH_PATTERN)


class ParameterSetRef(FrozenModel):
    parameter_set_id: str = Field(pattern=IDENTITY_PATTERN)
    version: int = Field(ge=1)
    content_hash: str = Field(pattern=HASH_PATTERN)


class SimulationProfileRef(FrozenModel):
    profile_id: str = Field(pattern=IDENTITY_PATTERN)
    version: int = Field(ge=1)
    content_hash: str = Field(pattern=HASH_PATTERN)


class SimulationEnvironmentRef(FrozenModel):
    environment_id: str = Field(pattern=IDENTITY_PATTERN)
    source_fingerprint: str = Field(pattern=HASH_PATTERN)


class SimulationRunRef(FrozenModel):
    run_id: str = Field(pattern=IDENTITY_PATTERN)
    environment_id: str = Field(pattern=IDENTITY_PATTERN)
    source_fingerprint: str = Field(pattern=HASH_PATTERN)


class SimulationResultRef(FrozenModel):
    run_id: str = Field(pattern=IDENTITY_PATTERN)
    result_artifact_refs: tuple[ArtifactRef, ...]


class SimulationSourceResolverPort(Protocol):
    def resolve_execution_plan(self, ref: Mapping[str, Any], context: Any) -> Mapping[str, Any]: ...
    def resolve_model_snapshot(self, ref: Mapping[str, Any], context: Any) -> Mapping[str, Any]: ...


__all__ = [
    "ExecutionPlanRef", "ParameterSetRef", "SimulationEnvironmentRef",
    "SimulationProfileRef", "SimulationResultRef", "SimulationRunRef",
    "SimulationSourceResolverPort",
]

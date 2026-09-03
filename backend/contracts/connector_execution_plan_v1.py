"""Immutable AI00 Connector execution-plan V1 contracts."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Mapping

from pydantic import Field, model_validator

from backend.capability_v2.contracts import FrozenModel, IDENTITY_PATTERN
from backend.domain_ports.local_integration import HASH_PATTERN, canonical_json_bytes


PROTOCOL_V1 = "ai00.connector.execution-plan.v1"


def canonical_hash(value: Any) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


class ConnectorStepV1(FrozenModel):
    step_id: str = Field(pattern=IDENTITY_PATTERN)
    operation_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}@1$")
    contract_hash: str = Field(pattern=HASH_PATTERN)
    depends_on: tuple[str, ...] = ()
    payload: Mapping[str, Any]
    payload_hash: str = Field(pattern=HASH_PATTERN)
    timeout_seconds: int = Field(ge=1, le=900)

    @model_validator(mode="after")
    def verify_payload_hash(self) -> "ConnectorStepV1":
        if self.payload_hash != canonical_hash(self.payload):
            raise ValueError("payload_hash_mismatch")
        if len(self.depends_on) != len(set(self.depends_on)):
            raise ValueError("duplicate_step_dependency")
        return self


class ConnectorExecutionPlanV1(FrozenModel):
    protocol: Literal["ai00.connector.execution-plan.v1"]
    plan_id: str = Field(pattern=IDENTITY_PATTERN)
    tenant_id: str = Field(pattern=IDENTITY_PATTERN)
    user_id: str = Field(pattern=IDENTITY_PATTERN)
    device_id: str = Field(pattern=IDENTITY_PATTERN)
    capability_version_gid: str = Field(pattern=IDENTITY_PATTERN)
    business_definition_hash: str = Field(pattern=HASH_PATTERN)
    adapter_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}$")
    adapter_major: Literal[1]
    steps: tuple[ConnectorStepV1, ...] = Field(min_length=1, max_length=10_000)
    issued_at: datetime
    expires_at: datetime
    plan_hash: str = Field(pattern=HASH_PATTERN)

    def compute_hash(self) -> str:
        return canonical_hash(self.model_dump(mode="json", exclude={"plan_hash"}))

    @model_validator(mode="after")
    def verify_plan(self) -> "ConnectorExecutionPlanV1":
        if self.issued_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("plan timestamps must be timezone-aware")
        if self.expires_at <= self.issued_at:
            raise ValueError("plan must expire after it is issued")
        seen: set[str] = set()
        for step in self.steps:
            if step.step_id in seen:
                raise ValueError("duplicate_step_id")
            if any(dependency not in seen for dependency in step.depends_on):
                raise ValueError("invalid_step_dependency")
            seen.add(step.step_id)
        if self.plan_hash != self.compute_hash():
            raise ValueError("plan_hash_mismatch")
        return self


class ConnectorStepResultV1(FrozenModel):
    step_id: str = Field(pattern=IDENTITY_PATTERN)
    status: Literal["completed", "failed", "outcome_unknown"]
    result: Any = None
    result_hash: str | None = Field(default=None, pattern=HASH_PATTERN)
    error_code: str = Field(default="", pattern=r"^[a-z0-9_.-]{0,128}$")
    started_at: datetime
    completed_at: datetime

    @model_validator(mode="after")
    def verify_result(self) -> "ConnectorStepResultV1":
        if self.started_at.tzinfo is None or self.completed_at.tzinfo is None:
            raise ValueError("step result timestamps must be timezone-aware")
        if self.completed_at < self.started_at:
            raise ValueError("step result completed before it started")
        if self.status == "completed":
            if self.error_code:
                raise ValueError("completed step cannot contain error_code")
            if self.result_hash != canonical_hash(self.result):
                raise ValueError("result_hash_mismatch")
        elif not self.error_code:
            raise ValueError("error_code_required")
        return self


class ConnectorPlanOutcomeV1(FrozenModel):
    protocol: Literal["ai00.connector.execution-plan.v1"]
    plan_id: str = Field(pattern=IDENTITY_PATTERN)
    status: Literal["completed", "failed", "cancelled", "outcome_unknown"]
    steps: tuple[ConnectorStepResultV1, ...]
    reported_at: datetime

    @model_validator(mode="after")
    def verify_reported_at(self) -> "ConnectorPlanOutcomeV1":
        if self.reported_at.tzinfo is None:
            raise ValueError("plan outcome timestamp must be timezone-aware")
        return self


__all__ = [
    "ConnectorExecutionPlanV1", "ConnectorPlanOutcomeV1", "ConnectorStepResultV1",
    "ConnectorStepV1", "PROTOCOL_V1", "canonical_hash",
]

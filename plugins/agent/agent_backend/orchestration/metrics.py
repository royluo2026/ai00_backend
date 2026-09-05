from __future__ import annotations

from datetime import UTC, datetime, timezone
from decimal import Decimal
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class UntrustedWorkloadEvidence(RuntimeError):
    pass


class WorkloadMeasurement(BaseModel):
    """Caller-visible selector. All KPI facts come from the trusted evidence resolver."""

    model_config = ConfigDict(extra="forbid")

    evidence_gid: str = Field(min_length=1)


class ResolvedWorkloadEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_gid: str = Field(min_length=1)
    task_key: str = Field(min_length=1)
    run_gid: str = Field(min_length=1)
    version_gid: str = Field(min_length=1)
    catalog_release_gid: str = Field(min_length=1)
    workload_baseline_gid: str = Field(min_length=1)
    authorization_evidence_gid: str = Field(min_length=1)
    acceptance_evidence_gid: str = Field(min_length=1)
    authorization_artifact_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    acceptance_artifact_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    annual_task_volume: Decimal = Field(ge=0)
    standard_manual_hours: Decimal = Field(ge=0)
    agent_share: Decimal = Field(ge=0, le=1)
    acceptance_pass_rate: Decimal = Field(ge=0, le=1)
    safety_gate_passed: bool
    mandatory_human: bool
    revoked: bool
    valid_from: datetime
    valid_until: datetime


class WorkloadEvidenceResolver(Protocol):
    def resolve(self, evidence_gid: str) -> ResolvedWorkloadEvidence: ...


class RepositoryWorkloadEvidenceResolver:
    """Production resolver backed by the Agent-owned repository.

    Callers provide only an evidence GID; tenant/project/actor scope is fixed
    when the resolver is constructed and cannot be smuggled through KPI input.
    """
    def __init__(self, repository: Any, *, actor_gid: str, tenant_gid: str, project_gid: str):
        self._repository = repository
        self._actor_gid = actor_gid
        self._tenant_gid = tenant_gid
        self._project_gid = project_gid

    def resolve(self, evidence_gid: str) -> ResolvedWorkloadEvidence:
        row = self._repository.get_workload_evidence(
            evidence_gid,
            actor_gid=self._actor_gid,
            tenant_gid=self._tenant_gid,
            project_gid=self._project_gid,
        )
        # A legacy row without both independently hash-bound evidence records
        # is deliberately unusable; no caller-supplied fallback is accepted.
        for key in (
            "authorization_artifact_hash", "acceptance_artifact_hash",
            "valid_from", "valid_until",
        ):
            if not row.get(key):
                raise UntrustedWorkloadEvidence(f"trusted evidence field missing: {key}")
        acceptance_from = row.pop("acceptance_valid_from", None)
        acceptance_until = row.pop("acceptance_valid_until", None)
        if acceptance_from is None or acceptance_until is None:
            raise UntrustedWorkloadEvidence("trusted acceptance validity window missing")
        # DB drivers commonly return naive DATETIME values.  The domain stores
        # them in UTC; normalize before the validity comparison.
        for key in ("valid_from", "valid_until"):
            value = row[key]
            if value.tzinfo is None:
                row[key] = value.replace(tzinfo=UTC)
        if acceptance_from.tzinfo is None:
            acceptance_from = acceptance_from.replace(tzinfo=UTC)
        if acceptance_until.tzinfo is None:
            acceptance_until = acceptance_until.replace(tzinfo=UTC)
        row["valid_from"] = max(row["valid_from"], acceptance_from)
        row["valid_until"] = min(row["valid_until"], acceptance_until)
        if row["valid_from"] > row["valid_until"]:
            raise UntrustedWorkloadEvidence("authorization and acceptance validity windows do not overlap")
        return ResolvedWorkloadEvidence.model_validate(row)


class EffectiveWorkTask(BaseModel):
    evidence_gid: str
    task_key: str
    total_workload_hours: Decimal
    agent_share: Decimal
    acceptance_pass_rate: Decimal
    effective_agent_workload_hours: Decimal


class EffectiveWorkRate(BaseModel):
    tasks: list[EffectiveWorkTask]
    total_workload_hours: Decimal
    effective_agent_workload_hours: Decimal
    rate: Decimal


class AutomationRatio(BaseModel):
    automated_workflow_count: int
    total_workflow_count: int
    rate: Decimal


class AutomationEvidenceResolver(Protocol):
    def list_automation_workflows(self, *, tenant_gid: str, project_gid: str) -> tuple[set[str], set[str]]: ...


def calculate_automation_ratio_from_evidence(
    *, evidence_resolver: AutomationEvidenceResolver, tenant_gid: str, project_gid: str,
) -> AutomationRatio:
    """Calculate automation from server-derived publication/runtime evidence."""
    published, successful = evidence_resolver.list_automation_workflows(
        tenant_gid=tenant_gid, project_gid=project_gid,
    )
    if not isinstance(published, set) or not isinstance(successful, set):
        raise UntrustedWorkloadEvidence("automation evidence resolver returned invalid collections")
    return calculate_automation_ratio(published, successful)


def _trusted_evidence(
    measurement: WorkloadMeasurement,
    resolver: WorkloadEvidenceResolver,
    as_of: datetime,
) -> ResolvedWorkloadEvidence:
    evidence = resolver.resolve(measurement.evidence_gid)
    if evidence.evidence_gid != measurement.evidence_gid:
        raise UntrustedWorkloadEvidence("workload evidence identity mismatch")
    if evidence.revoked:
        raise UntrustedWorkloadEvidence("workload evidence is revoked")
    if not evidence.valid_from <= as_of <= evidence.valid_until:
        raise UntrustedWorkloadEvidence("workload evidence is outside its validity window")
    return evidence


def calculate_effective_intelligent_work_rate(
    measurements: list[WorkloadMeasurement],
    *,
    evidence_resolver: WorkloadEvidenceResolver,
    as_of: datetime | None = None,
) -> EffectiveWorkRate:
    evaluated_at = as_of or datetime.now(timezone.utc)
    tasks: list[EffectiveWorkTask] = []
    for measurement in measurements:
        evidence = _trusted_evidence(measurement, evidence_resolver, evaluated_at)
        total = evidence.annual_task_volume * evidence.standard_manual_hours
        effective = Decimal("0")
        if evidence.safety_gate_passed and not evidence.mandatory_human:
            effective = total * evidence.agent_share * evidence.acceptance_pass_rate
        tasks.append(EffectiveWorkTask(
            evidence_gid=evidence.evidence_gid,
            task_key=evidence.task_key,
            total_workload_hours=total,
            agent_share=evidence.agent_share,
            acceptance_pass_rate=evidence.acceptance_pass_rate,
            effective_agent_workload_hours=effective,
        ))
    total = sum((item.total_workload_hours for item in tasks), Decimal("0"))
    effective = sum((item.effective_agent_workload_hours for item in tasks), Decimal("0"))
    return EffectiveWorkRate(
        tasks=tasks,
        total_workload_hours=total,
        effective_agent_workload_hours=effective,
        rate=(effective / total).quantize(Decimal("0.0001")) if total else Decimal("0.0000"),
    )


def calculate_automation_ratio(
    published_workflow_gids: set[str],
    successful_run_workflow_gids: set[str],
) -> AutomationRatio:
    if not isinstance(published_workflow_gids, set) or not isinstance(successful_run_workflow_gids, set):
        raise UntrustedWorkloadEvidence("automation ratio requires repository-derived sets")
    total = len(published_workflow_gids)
    automated = len(published_workflow_gids & successful_run_workflow_gids)
    return AutomationRatio(
        automated_workflow_count=automated,
        total_workflow_count=total,
        rate=(Decimal(automated) / Decimal(total)).quantize(Decimal("0.0001"))
        if total else Decimal("0.0000"),
    )

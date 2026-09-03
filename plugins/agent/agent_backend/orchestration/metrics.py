from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, computed_field


class WorkloadMeasurement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_key: str = Field(min_length=1)
    annual_task_volume: Decimal = Field(ge=0)
    standard_manual_hours: Decimal = Field(ge=0)
    agent_share: Decimal = Field(ge=0, le=1)
    acceptance_pass_rate: Decimal | None = Field(default=None, ge=0, le=1)
    authorization_policy_ref: str | None = Field(default=None, min_length=1)
    acceptance_evidence_ref: str | None = Field(default=None, min_length=1)
    safety_gate_passed: bool = False
    mandatory_human: bool = False

    @computed_field
    @property
    def total_workload_hours(self) -> Decimal:
        return self.annual_task_volume * self.standard_manual_hours

    @computed_field
    @property
    def effective_agent_workload_hours(self) -> Decimal:
        if (
            not self.safety_gate_passed
            or self.mandatory_human
            or self.acceptance_pass_rate is None
            or not self.authorization_policy_ref
            or not self.acceptance_evidence_ref
        ):
            return Decimal("0")
        return self.total_workload_hours * self.agent_share * self.acceptance_pass_rate


class EffectiveWorkRate(BaseModel):
    tasks: list[WorkloadMeasurement]
    total_workload_hours: Decimal
    effective_agent_workload_hours: Decimal
    rate: Decimal


class AutomationRatio(BaseModel):
    automated_workflow_count: int
    total_workflow_count: int
    rate: Decimal


def calculate_effective_intelligent_work_rate(
    measurements: list[WorkloadMeasurement],
) -> EffectiveWorkRate:
    total = sum((item.total_workload_hours for item in measurements), Decimal("0"))
    effective = sum((item.effective_agent_workload_hours for item in measurements), Decimal("0"))
    return EffectiveWorkRate(
        tasks=measurements,
        total_workload_hours=total,
        effective_agent_workload_hours=effective,
        rate=(effective / total).quantize(Decimal("0.0001")) if total else Decimal("0.0000"),
    )


def calculate_automation_ratio(
    published_workflow_gids: set[str],
    successful_run_workflow_gids: set[str],
) -> AutomationRatio:
    total = len(published_workflow_gids)
    automated = len(published_workflow_gids & successful_run_workflow_gids)
    return AutomationRatio(
        automated_workflow_count=automated,
        total_workflow_count=total,
        rate=(Decimal(automated) / Decimal(total)).quantize(Decimal("0.0001"))
        if total else Decimal("0.0000"),
    )

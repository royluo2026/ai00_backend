import pytest
from decimal import Decimal

from plugins.agent.agent_backend.orchestration.metrics import (
    WorkloadMeasurement,
    calculate_automation_ratio,
    calculate_effective_intelligent_work_rate,
)


def test_effective_intelligent_work_rate_matches_canonical_example():
    measurements = [
        WorkloadMeasurement(task_key="collect", annual_task_volume=1, standard_manual_hours=500, agent_share=0.8, acceptance_pass_rate=0.95, safety_gate_passed=True, authorization_policy_ref="policy-collect", acceptance_evidence_ref="evidence-collect"),
        WorkloadMeasurement(task_key="analyse", annual_task_volume=1, standard_manual_hours=300, agent_share=0.5, acceptance_pass_rate=0.9, safety_gate_passed=True, authorization_policy_ref="policy-analyse", acceptance_evidence_ref="evidence-analyse"),
        WorkloadMeasurement(task_key="approve", annual_task_volume=1, standard_manual_hours=200, agent_share=1, acceptance_pass_rate=1, safety_gate_passed=False),
    ]

    result = calculate_effective_intelligent_work_rate(measurements)

    assert result.total_workload_hours == Decimal("1000")
    assert result.effective_agent_workload_hours == Decimal("515.000")
    assert result.rate == Decimal("0.5150")
    assert result.tasks[2].effective_agent_workload_hours == 0


def test_empty_workload_has_zero_rate():
    result = calculate_effective_intelligent_work_rate([])

    assert result.rate == 0
    assert result.total_workload_hours == 0


def test_missing_acceptance_and_mandatory_human_contribute_zero():
    result = calculate_effective_intelligent_work_rate([
        WorkloadMeasurement(task_key="unaccepted", annual_task_volume=10, standard_manual_hours=2, agent_share=1, acceptance_pass_rate=None),
        WorkloadMeasurement(task_key="human", annual_task_volume=5, standard_manual_hours=2, agent_share=1, acceptance_pass_rate=1, mandatory_human=True),
    ])

    assert result.total_workload_hours == Decimal("30")
    assert result.effective_agent_workload_hours == Decimal("0")
    assert result.rate == Decimal("0.0000")


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"safety_gate_passed": True},
        {"safety_gate_passed": True, "authorization_policy_ref": "policy-1"},
        {"safety_gate_passed": True, "acceptance_evidence_ref": "evidence-1"},
    ],
)
def test_effective_workload_is_zero_without_complete_safety_evidence(overrides):
    measurement = WorkloadMeasurement.model_validate({
        "task_key": "collect",
        "annual_task_volume": 1,
        "standard_manual_hours": 10,
        "agent_share": 1,
        "acceptance_pass_rate": 1,
        **overrides,
    })

    assert measurement.effective_agent_workload_hours == Decimal("0")


def test_automation_ratio_counts_published_workflows_with_successful_runs():
    result = calculate_automation_ratio(
        published_workflow_gids={"wf-1", "wf-2", "wf-3"},
        successful_run_workflow_gids={"wf-1", "wf-3", "draft-only"},
    )

    assert result.automated_workflow_count == 2
    assert result.total_workflow_count == 3
    assert result.rate == Decimal("0.6667")

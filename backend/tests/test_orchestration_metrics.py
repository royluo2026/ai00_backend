from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from plugins.agent.agent_backend.orchestration.metrics import (
    ResolvedWorkloadEvidence,
    UntrustedWorkloadEvidence,
    WorkloadMeasurement,
    calculate_automation_ratio,
    calculate_effective_intelligent_work_rate,
)


NOW = datetime(2026, 9, 3, tzinfo=timezone.utc)
HASH = "sha256:" + "a" * 64


class EvidenceResolver:
    def __init__(self, rows):
        self.rows = rows

    def resolve(self, evidence_gid):
        return ResolvedWorkloadEvidence.model_validate(self.rows[evidence_gid])


def evidence(evidence_gid, task_key, hours, agent_share, acceptance_rate, **overrides):
    return {
        "evidence_gid": evidence_gid,
        "task_key": task_key,
        "run_gid": "run-1",
        "version_gid": "version-1",
        "catalog_release_gid": "release-1",
        "workload_baseline_gid": f"baseline-{evidence_gid}",
        "authorization_evidence_gid": f"authorization-{evidence_gid}",
        "acceptance_evidence_gid": f"acceptance-{evidence_gid}",
        "authorization_artifact_hash": HASH,
        "acceptance_artifact_hash": HASH,
        "annual_task_volume": 1,
        "standard_manual_hours": hours,
        "agent_share": agent_share,
        "acceptance_pass_rate": acceptance_rate,
        "safety_gate_passed": True,
        "mandatory_human": False,
        "revoked": False,
        "valid_from": NOW - timedelta(days=1),
        "valid_until": NOW + timedelta(days=1),
        **overrides,
    }


def test_effective_intelligent_work_rate_matches_canonical_example():
    rows = {
        "e1": evidence("e1", "数据收集整理", 500, 0.8, 0.95),
        "e2": evidence("e2", "异常原因分析", 300, 0.5, 0.9),
        "e3": evidence("e3", "最终放行审批", 200, 1, 1, mandatory_human=True),
    }
    result = calculate_effective_intelligent_work_rate(
        [WorkloadMeasurement(evidence_gid=gid) for gid in rows],
        evidence_resolver=EvidenceResolver(rows),
        as_of=NOW,
    )

    assert result.total_workload_hours == Decimal("1000")
    assert result.effective_agent_workload_hours == Decimal("515.000")
    assert result.rate == Decimal("0.5150")
    assert result.tasks[2].effective_agent_workload_hours == 0


def test_caller_cannot_assert_safety_or_acceptance_facts():
    with pytest.raises(ValidationError):
        WorkloadMeasurement.model_validate({
            "evidence_gid": "e1",
            "safety_gate_passed": True,
            "authorization_policy_ref": "attacker",
            "acceptance_evidence_ref": "attacker",
            "agent_share": 1,
            "acceptance_pass_rate": 1,
        })


@pytest.mark.parametrize(
    "overrides",
    [
        {"revoked": True},
        {"valid_until": NOW - timedelta(seconds=1)},
        {"evidence_gid": "different"},
    ],
)
def test_calculation_rejects_revoked_expired_or_mismatched_evidence(overrides):
    row = evidence("e1", "任务", 10, 1, 1)
    row.update(overrides)
    rows = {"e1": row}

    with pytest.raises(UntrustedWorkloadEvidence):
        calculate_effective_intelligent_work_rate(
            [WorkloadMeasurement(evidence_gid="e1")],
            evidence_resolver=EvidenceResolver(rows),
            as_of=NOW,
        )


def test_empty_workload_has_zero_rate():
    result = calculate_effective_intelligent_work_rate(
        [], evidence_resolver=EvidenceResolver({}), as_of=NOW
    )

    assert result.rate == 0
    assert result.total_workload_hours == 0


def test_unsafe_and_mandatory_human_authoritative_evidence_contribute_zero():
    rows = {
        "unsafe": evidence("unsafe", "不安全", 20, 1, 1, safety_gate_passed=False),
        "human": evidence("human", "人工", 10, 1, 1, mandatory_human=True),
    }
    result = calculate_effective_intelligent_work_rate(
        [WorkloadMeasurement(evidence_gid=gid) for gid in rows],
        evidence_resolver=EvidenceResolver(rows),
        as_of=NOW,
    )

    assert result.total_workload_hours == Decimal("30")
    assert result.effective_agent_workload_hours == Decimal("0")
    assert result.rate == Decimal("0.0000")


def test_automation_ratio_counts_published_workflows_with_successful_runs():
    result = calculate_automation_ratio(
        published_workflow_gids={"wf-1", "wf-2", "wf-3"},
        successful_run_workflow_gids={"wf-1", "wf-3", "draft-only"},
    )

    assert result.automated_workflow_count == 2
    assert result.total_workflow_count == 3
    assert result.rate == Decimal("0.6667")

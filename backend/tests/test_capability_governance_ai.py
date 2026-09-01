from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from backend.capability_governance_test.ai_advisory import (
    AdvisoryContractError,
    GovernedAgentAdvisor,
    advisory_result,
    explain_relation,
    validate_advisory,
)
from backend.capability_governance_test.business_models import CapabilityRelationCandidate
from backend.capability_governance_test.audit import AuditSink
from backend.capability_governance_test.service import CapabilityGovernanceService
from backend.capability_v2.contracts import CapabilityResultV2, CapabilityStatus, CorrelationRef, OperationRef, OperationStatus


class RecordingDomainClient:
    def __init__(self, data):
        self.data = data
        self.invocations = []

    async def invoke(self, invocation, identity, correlation, deadline=None):
        self.invocations.append((invocation, identity, correlation, deadline))
        return CapabilityResultV2(
            ok=True,
            status=CapabilityStatus.COMPLETED,
            capability_id="agent.interaction.request",
            major_version=1,
            data=self.data,
            correlation=CorrelationRef(request_id=correlation.request_id),
        )


def test_ai_result_cannot_confirm_finding():
    result = advisory_result(status="confirmed")

    with pytest.raises(AdvisoryContractError, match="candidate_only"):
        validate_advisory(result)


def test_ai_relation_explanation_is_advisory_and_cannot_change_deterministic_blocking_evidence():
    candidate = CapabilityRelationCandidate(
        relation_candidate_gid=7,
        snapshot_gid=9,
        candidate_hash="sha256:" + "a" * 64,
        relation_type="conflict",
        source="deterministic",
        capability_keys=("ergonomics.height.validate@1", "person.height.write@1"),
        evidence={"constraint_field": "height", "left_interval": (None, 2.5), "right_interval": (2.6, None)},
    )

    advisory = explain_relation(candidate, evidence={"summary": "possibly similar", "severity": "blocking"})

    assert advisory.authority == "advisory"
    assert advisory.severity != "blocking"
    assert advisory.capability_keys == candidate.capability_keys
    assert candidate.source == "deterministic"
    assert candidate.evidence["constraint_field"] == "height"


@pytest.mark.parametrize("finding", [
    {"finding_type": "unknown", "subject_version_gids": ["7"], "confidence": 0.5, "evidence_keys": [], "recommendation": "review", "status": "candidate"},
    {"finding_type": "gap", "subject_version_gids": [7], "confidence": 0.5, "evidence_keys": [], "recommendation": "review", "status": "candidate"},
    {"finding_type": "gap", "subject_version_gids": ["٧"], "confidence": 0.5, "evidence_keys": [], "recommendation": "review", "status": "candidate"},
    {"finding_type": "gap", "subject_version_gids": ["7"], "confidence": 1.1, "evidence_keys": [], "recommendation": "review", "status": "candidate"},
])
def test_ai_result_rejects_non_contract_findings(finding):
    with pytest.raises(AdvisoryContractError):
        validate_advisory({"findings": [finding]})


@pytest.mark.parametrize("evidence_keys", [
    ["customer Alice source excerpt"],
    [f"evidence:{index}" for index in range(21)],
])
def test_ai_result_rejects_unbounded_or_non_identifier_evidence_keys(evidence_keys):
    with pytest.raises(AdvisoryContractError, match="candidate_only"):
        validate_advisory({"findings": [{
            "finding_type": "gap", "subject_version_gids": ["7"], "confidence": 0.5,
            "evidence_keys": evidence_keys, "recommendation": "review", "status": "candidate",
        }]})


def test_advisor_uses_only_governed_agent_client_with_bounded_redacted_package_and_deadline():
    client = RecordingDomainClient({"findings": [{
        "finding_type": "gap", "subject_version_gids": ["7"], "confidence": 0.75,
        "evidence_keys": ["evidence:7"], "recommendation": "add a review", "status": "candidate",
    }]})
    advisor = GovernedAgentAdvisor(client, max_input_bytes=4096, max_output_bytes=4096, timeout_seconds=5)
    identity = object()
    before = datetime.now(UTC)

    result = asyncio.run(advisor.review({"snapshot_gid": "9", "token": "secret", "business_effect": "orders"}, identity=identity, request_id="request-1"))

    invocation, actual_identity, correlation, deadline = client.invocations[0]
    assert result.findings[0].status == "candidate"
    assert invocation.capability_id == "agent.interaction.request"
    assert invocation.major_version == 1
    assert actual_identity is identity
    assert correlation.request_id == "request-1"
    assert deadline is not None and before < deadline <= before + timedelta(seconds=6)
    assert "secret" not in repr(invocation.payload)
    assert len(str(invocation.payload).encode("utf-8")) <= 4096


def test_advisor_drops_benign_key_business_and_source_content_from_nested_candidate_package():
    client = RecordingDomainClient({"findings": []})
    advisor = GovernedAgentAdvisor(client, max_input_bytes=4096, max_output_bytes=4096)

    asyncio.run(advisor.review({
        "snapshot_gid": "9",
        "capabilities": [{
            "capability_id": "craft.order.submit",
            "input_schema_hash": "sha256:" + "a" * 64,
            "source_excerpt": "customer Alice order 123",
            "benign_note": "business payload",
        }],
        "evidence_summaries": {"evidence_keys": ["evidence:7"], "notes": "customer payload"},
    }, identity=object(), request_id="request-1"))

    transmitted = repr(client.invocations[0][0].payload)
    assert "Alice" not in transmitted
    assert "business payload" not in transmitted
    assert "customer payload" not in transmitted


def test_advisor_rejects_packages_and_results_that_exceed_hard_byte_limits():
    advisor = GovernedAgentAdvisor(RecordingDomainClient({"findings": []}), max_input_bytes=32, max_output_bytes=32)

    with pytest.raises(AdvisoryContractError, match="input_bytes_exceeded"):
        asyncio.run(advisor.review({"summary": "x" * 100}, identity=object(), request_id="request-1"))

    unknown_oversize = GovernedAgentAdvisor(
        RecordingDomainClient({"findings": []}), max_input_bytes=256, max_output_bytes=256,
    )
    with pytest.raises(AdvisoryContractError, match="input_bytes_exceeded"):
        asyncio.run(unknown_oversize.review({"arbitrary": "x" * 1000}, identity=object(), request_id="request-1"))

    output_limited = GovernedAgentAdvisor(
        RecordingDomainClient({"findings": [], "padding": "x" * 100}),
        max_input_bytes=4096,
        max_output_bytes=32,
    )
    with pytest.raises(AdvisoryContractError, match="output_bytes_exceeded"):
        asyncio.run(output_limited.review({}, identity=object(), request_id="request-1"))


def test_service_audits_redacted_governed_advice_without_promoting_candidate_to_confirmation():
    client = RecordingDomainClient({"findings": [{
        "finding_type": "gap", "subject_version_gids": ["7"], "confidence": 0.75,
        "evidence_keys": ["evidence:7"], "recommendation": "review", "status": "candidate",
    }]})
    sink = AuditSink(next_gid=iter(range(1, 10)).__next__)
    service = CapabilityGovernanceService(advisor=GovernedAgentAdvisor(client), audit_sink=sink)

    result = asyncio.run(service.review_advisory(
        {"snapshot_gid": "9", "token": "secret"},
        context=type("Context", (), {"identity": object(), "user_gid": "actor-1"})(),
        request_id="request-1",
    ))

    assert result.findings[0].status == "candidate"
    event = sink.events[0]
    assert event.operation == "agent_invocation"
    assert "secret" not in repr(event.detail)


class SequencedDomainClient:
    def __init__(self, results):
        self._results = iter(results)
        self.invocations = []

    async def invoke(self, invocation, identity, correlation, deadline=None):
        self.invocations.append((invocation, identity, correlation, deadline))
        return next(self._results)


def test_advisor_polls_governed_agent_run_after_accepted_interaction_until_completed():
    accepted = CapabilityResultV2(
        ok=True, status=CapabilityStatus.ACCEPTED, capability_id="agent.interaction.request", major_version=1,
        operation_ref=OperationRef(operation_id="operation-1", status=OperationStatus.ACCEPTED),
        correlation=CorrelationRef(request_id="request-1"),
    )
    completed = CapabilityResultV2(
        ok=True, status=CapabilityStatus.COMPLETED, capability_id="agent.run.read", major_version=1,
        data={"content": {"findings": []}}, correlation=CorrelationRef(request_id="request-1"),
    )
    client = SequencedDomainClient((accepted, completed))

    result = asyncio.run(GovernedAgentAdvisor(client).review({}, identity=object(), request_id="request-1"))

    assert result.findings == ()
    assert [item[0].capability_id for item in client.invocations] == ["agent.interaction.request", "agent.run.read"]
    assert client.invocations[1][0].payload == {"resource_gid": "operation-1"}


def test_advisor_rejects_failed_governed_operation_result():
    accepted = CapabilityResultV2(
        ok=True, status=CapabilityStatus.ACCEPTED, capability_id="agent.interaction.request", major_version=1,
        operation_ref=OperationRef(operation_id="operation-1", status=OperationStatus.ACCEPTED),
        correlation=CorrelationRef(request_id="request-1"),
    )
    failed = CapabilityResultV2.model_validate({
        "ok": False, "status": "failed", "capability_id": "agent.run.read", "major_version": 1,
        "error": {"code": "invalid_input", "message": "failed"}, "correlation": {"request_id": "request-1"},
    })

    with pytest.raises(AdvisoryContractError, match="agent_advisory_failed"):
        asyncio.run(GovernedAgentAdvisor(SequencedDomainClient((accepted, failed))).review({}, identity=object(), request_id="request-1"))


def test_advisor_times_out_after_bounded_governed_operation_polls():
    accepted = CapabilityResultV2(
        ok=True, status=CapabilityStatus.ACCEPTED, capability_id="agent.interaction.request", major_version=1,
        operation_ref=OperationRef(operation_id="operation-1", status=OperationStatus.ACCEPTED),
        correlation=CorrelationRef(request_id="request-1"),
    )
    pending = CapabilityResultV2(
        ok=True, status=CapabilityStatus.ACCEPTED, capability_id="agent.run.read", major_version=1,
        operation_ref=OperationRef(operation_id="operation-1", status=OperationStatus.RUNNING),
        correlation=CorrelationRef(request_id="request-1"),
    )

    with pytest.raises(AdvisoryContractError, match="agent_advisory_timeout"):
        asyncio.run(GovernedAgentAdvisor(SequencedDomainClient((accepted, pending, pending, pending, pending))).review({}, identity=object(), request_id="request-1"))

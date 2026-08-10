from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.capability_v2.contracts import (
    ActorIdentity, AutomationLevel, CapabilityDescriptorV2, CapabilityResultV2,
    CapabilityStatus, ConsumerDescriptor, ConsumerIdentity, ConsumerType,
    CorrelationRef, DelegationContext, ExposurePolicy, InvocationEnvelope,
    TenantIdentity,
)
from backend.capability_v2.outcomes import InMemoryOutcomeStore
from backend.capability_v2.reliability import (
    ApprovalService, InMemoryApprovalStore, InMemoryRateLimiter,
    ReliabilityCoordinator, ReliabilityError,
)


def _descriptor(**updates):
    descriptor = CapabilityDescriptorV2(
        id="craft.routing.update", major_version=1, owner_domain="craft",
        title="Update routing", description="Update a routing.",
        use_when="A routing must change.", do_not_use_when="Only a read is required.",
        exposure=ExposurePolicy(web=True, agent=True),
        automation_level=AutomationLevel.A2, authorization_policy="craft.write",
        side_effect_level="write", confirmation_policy="user",
        idempotency_policy="required", rate_limit_cost=3,
        input_schema={
            "type": "object", "properties": {"value": {"type": "integer"}},
            "required": ["value"], "additionalProperties": False,
        },
        output_schema={"type": "object", "properties": {}, "additionalProperties": False},
        schema_hash="sha256:" + "a" * 64,
    )
    return descriptor.model_copy(update=updates)


def _identity(run_id="run_a"):
    return ConsumerIdentity(
        actor=ActorIdentity(
            user_id="user_1", authentication_method="jwt", authenticated_at=datetime.now(UTC)
        ),
        tenant=TenantIdentity(tenant_id="tenant_1", membership="member"),
        consumer=ConsumerDescriptor(
            type=ConsumerType.AGENT, consumer_id="agent.runtime", agent_run_id=run_id,
        ),
        delegation=DelegationContext(
            delegation_id=f"delegation_{run_id}", delegated_by="user_1",
            capability_scopes=("craft.routing.update",), resource_scopes=("project:p1",),
            data_scopes=("confidential",), catalog_release="rel_1",
            maximum_automation_level=AutomationLevel.A2,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        ),
    )


def _envelope(run_id="run_a", *, value=1, key="idem_1", approval=None):
    return InvocationEnvelope(
        capability_id="craft.routing.update", major_version=1, catalog_release="rel_1",
        payload={"value": value}, identity=_identity(run_id), idempotency_key=key,
        approval_reference=approval, request_id=f"request_{run_id}_{value}", trace_id="trace_1",
    )


def _result(envelope):
    return CapabilityResultV2(
        ok=True, status=CapabilityStatus.COMPLETED,
        capability_id=envelope.capability_id, major_version=envelope.major_version,
        data={}, correlation=CorrelationRef(
            request_id=envelope.request_id, trace_id=envelope.trace_id
        ),
    )


def test_approval_is_bound_to_agent_run_resource_policy_and_payload_and_is_one_time():
    service = ApprovalService(InMemoryApprovalStore())
    issued = service.issue(
        _descriptor(), _envelope(), resource_refs=("project:p1",),
        policy_version="policy-7", ttl_seconds=60,
    )
    assert issued.token.startswith("apr_")

    assert service.consume(
        issued.token, _descriptor(), _envelope("run_b"),
        resource_refs=("project:p1",), policy_version="policy-7",
    ) is False
    assert service.consume(
        issued.token, _descriptor(), _envelope(approval=issued.token),
        resource_refs=("project:p1",), policy_version="policy-7",
    ) is True
    assert service.consume(
        issued.token, _descriptor(), _envelope(approval=issued.token),
        resource_refs=("project:p1",), policy_version="policy-7",
    ) is False


def test_idempotency_scope_includes_consumer_and_normalized_payload_hash():
    coordinator = ReliabilityCoordinator(InMemoryOutcomeStore(), InMemoryRateLimiter(limit=100))
    first = coordinator.begin(_envelope("run_a", value=1), _descriptor(), policy_version="policy-7")
    coordinator.complete(first, _result(_envelope("run_a", value=1)))

    replay = coordinator.begin(
        _envelope("run_a", value=1, key="idem_1"), _descriptor(), policy_version="policy-7"
    )
    assert replay.replay_result is not None

    with pytest.raises(ReliabilityError, match="idempotency_payload_conflict"):
        coordinator.begin(
            _envelope("run_a", value=2, key="idem_1"), _descriptor(), policy_version="policy-7"
        )

    other_consumer = coordinator.begin(
        _envelope("run_b", value=2, key="idem_1"), _descriptor(), policy_version="policy-7"
    )
    assert other_consumer.replay_result is None


def test_completed_write_survives_audit_delivery_failure_and_outbox_remains_pending():
    store = InMemoryOutcomeStore()
    coordinator = ReliabilityCoordinator(store, InMemoryRateLimiter(limit=100))
    envelope = _envelope()
    lease = coordinator.begin(envelope, _descriptor(), policy_version="policy-7")
    coordinator.complete(lease, _result(envelope))

    def unavailable(_event):
        raise RuntimeError("audit transport down")

    assert store.deliver_audit_outbox(unavailable) == 0
    assert store.get(lease.operation_id).status == "completed"
    assert len(store.pending_audit_events()) == 1


def test_weighted_rate_limit_is_scoped_to_agent_run():
    limiter = InMemoryRateLimiter(limit=5, window_seconds=60)
    coordinator = ReliabilityCoordinator(InMemoryOutcomeStore(), limiter)
    coordinator.begin(_envelope("run_a", key="a1"), _descriptor(), policy_version="policy-7")
    with pytest.raises(ReliabilityError, match="rate_limit_exceeded"):
        coordinator.begin(_envelope("run_a", key="a2"), _descriptor(), policy_version="policy-7")
    coordinator.begin(_envelope("run_b", key="b1"), _descriptor(), policy_version="policy-7")


def test_required_idempotency_key_fails_before_outcome_creation():
    store = InMemoryOutcomeStore()
    coordinator = ReliabilityCoordinator(store, InMemoryRateLimiter(limit=100))
    with pytest.raises(ReliabilityError, match="idempotency_key_required"):
        coordinator.begin(
            _envelope(key=None), _descriptor(), policy_version="policy-7"
        )
    assert store.snapshot() == ()


def test_admin_and_dual_approval_policies_fail_closed_for_unqualified_requester():
    service = ApprovalService(InMemoryApprovalStore())
    with pytest.raises(ReliabilityError, match="admin_approval_required"):
        service.issue(
            _descriptor(confirmation_policy="admin"), _envelope(),
            resource_refs=("project:p1",), policy_version="policy-7",
        )
    with pytest.raises(ReliabilityError, match="dual_approval_workflow_required"):
        service.issue(
            _descriptor(confirmation_policy="dual"), _envelope(),
            resource_refs=("project:p1",), policy_version="policy-7",
        )

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from backend.capabilities.models_next import CapabilitySpec
from backend.capabilities.models_next import CapabilityBusinessError
from backend.capabilities.registry_next import CapabilityRegistry
from backend.capability_v2.catalog import CatalogResolver, build_release
from backend.capability_v2.catalog_store import InMemoryCatalogStore
from backend.capability_v2.contracts import (
    ActorIdentity,
    AutomationLevel,
    CapabilityDescriptorV2,
    ConsumerDescriptor,
    ConsumerIdentity,
    ConsumerType,
    ExposurePolicy,
    InvocationEnvelope,
    SideEffectLevel,
    TenantIdentity,
)
from backend.capability_v2.gateway import CapabilityGatewayService
from backend.capability_v2.authorization import AuthorizationDecision
from backend.capability_v2.policies import GatewayPolicyError
from backend.capability_v2.outcomes import InMemoryOutcomeStore
from backend.capability_v2.reliability import (
    InMemoryRateLimiter, ReliabilityCoordinator, TransactionalCapabilityOutput,
    transactional_provider,
)


def _descriptor(*, plugin: bool = False) -> CapabilityDescriptorV2:
    return CapabilityDescriptorV2(
        id="craft.routing.get", major_version=1, owner_domain="craft",
        title="Get routing", description="Return one routing.",
        use_when="A routing is needed.", do_not_use_when="A write is needed.",
        exposure=ExposurePolicy(web=True, plugin=plugin), automation_level=AutomationLevel.A2,
        authorization_policy="craft.routing.read",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        output_schema={
            "type": "object",
            "properties": {"routing_id": {"type": "string"}},
            "required": ["routing_id"],
            "additionalProperties": False,
        },
        schema_hash="sha256:" + "a" * 64,
    )


def _identity(consumer_type: ConsumerType) -> ConsumerIdentity:
    return ConsumerIdentity(
        actor=ActorIdentity(
            user_id="user_1", authentication_method="jwt", authenticated_at=datetime.now(UTC)
        ),
        tenant=TenantIdentity(tenant_id="tenant_1", membership="member", active_roles=("member",)),
        consumer=ConsumerDescriptor(type=consumer_type, consumer_id=f"test.{consumer_type.value}"),
    )


def _gateway(descriptor, handler, policy, reliability=None):
    registry = CapabilityRegistry()
    registry.register(
        CapabilitySpec(
            id="craft.routing.get", version=1, owner="craft",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            output_schema=descriptor.output_schema,
        ),
        handler,
    )
    release = build_release([descriptor])
    store = InMemoryCatalogStore()
    store.publish(release)
    return CapabilityGatewayService(
        CatalogResolver(store, registry), policy, reliability=reliability
    ), release


def _envelope(release, consumer_type=ConsumerType.WEB):
    return InvocationEnvelope(
        capability_id="craft.routing.get", major_version=1, catalog_release=release.release_id,
        payload={}, identity=_identity(consumer_type), request_id="request_1", trace_id="trace_1",
    )


def test_gateway_rejects_exposure_before_authorization_or_provider_dispatch():
    events = []

    class Policy:
        def authorize(self, *_args): events.append("authorize")
        def approve(self, *_args): events.append("approve")
        def project(self, _descriptor, _identity, data): return data

    async def handler(payload, context):
        events.append("dispatch")
        return {"routing_id": "routing_1"}

    gateway, release = _gateway(_descriptor(plugin=False), handler, Policy())
    result = asyncio.run(gateway.invoke(_envelope(release, ConsumerType.PLUGIN)))

    assert result.ok is False
    assert result.error.code == "consumer_not_allowed"
    assert events == []


def test_gateway_executes_fixed_validate_authorize_approve_dispatch_project_order():
    events = []

    class Policy:
        def authorize(self, *_args): events.append("authorize")
        def approve(self, *_args): events.append("approve")
        def project(self, _descriptor, _identity, data):
            events.append("project")
            return data

    def handler(payload, context):
        events.append("dispatch")
        assert context.user_gid == "user_1"
        assert context.source == "web"
        return {"routing_id": "routing_1"}

    gateway, release = _gateway(_descriptor(), handler, Policy())
    result = asyncio.run(gateway.invoke(_envelope(release)))

    assert result.ok is True
    assert result.data == {"routing_id": "routing_1"}
    assert events == ["authorize", "approve", "dispatch", "project"]


def test_gateway_fails_closed_when_authorization_backend_crashes():
    class Policy:
        def authorize(self, *_args):
            raise RuntimeError("database password and connection details")
        def approve(self, *_args):
            raise AssertionError("approval must not run")
        def project(self, _descriptor, _identity, data):
            return data

    gateway, release = _gateway(
        _descriptor(), lambda _payload, _context: {"routing_id": "routing_1"}, Policy()
    )
    result = asyncio.run(gateway.invoke(_envelope(release)))

    assert result.ok is False
    assert result.status.value == "failed"
    assert result.error.code == "authorization_failed"
    assert "password" not in result.error.message


def test_gateway_does_not_leak_catalog_resolution_details():
    gateway, release = _gateway(
        _descriptor(), lambda _payload, _context: {"routing_id": "routing_1"}, object()
    )
    envelope = _envelope(release).model_copy(update={"catalog_release": "rel_missing"})
    result = asyncio.run(gateway.invoke(envelope))

    assert result.ok is False
    assert result.error.code == "catalog_resolution_failed"
    assert "rel_missing" not in result.error.message


def test_gateway_authorizes_before_returning_input_schema_details():
    class Policy:
        def authorize(self, *_args):
            raise GatewayPolicyError("permission_denied", "Access denied.")
        def approve(self, *_args):
            raise AssertionError("approval must not run")
        def project(self, _descriptor, _identity, data):
            return data

    gateway, release = _gateway(
        _descriptor(), lambda _payload, _context: {"routing_id": "routing_1"}, Policy()
    )
    envelope = _envelope(release).model_copy(update={"payload": {"unknown": "secret probe"}})
    result = asyncio.run(gateway.invoke(envelope))

    assert result.error.code == "permission_denied"


def test_gateway_rejects_closed_schema_unknown_fields_before_dispatch():
    dispatched = []

    class Policy:
        def authorize(self, *_args):
            return None
        def approve(self, *_args):
            return None
        def project(self, _descriptor, _identity, data):
            return data

    def handler(_payload, _context):
        dispatched.append(True)
        return {"routing_id": "routing_1"}

    gateway, release = _gateway(_descriptor(), handler, Policy())
    envelope = _envelope(release).model_copy(update={"payload": {"unknown": "not allowed"}})
    result = asyncio.run(gateway.invoke(envelope))

    assert result.error.code == "invalid_input"
    assert dispatched == []


def test_gateway_applies_ai_projection_with_authorized_data_scopes():
    descriptor = _descriptor().model_copy(update={
        "exposure": ExposurePolicy(web=True, agent=True),
    })

    class Policy:
        def authorize(self, *_args):
            return AuthorizationDecision(
                allowed=True, code="allowed", policy_version="policy-7",
                data_scopes=("internal",),
            )
        def approve(self, *_args):
            return None
        def project(self, _descriptor, _identity, data):
            return data

    gateway, release = _gateway(
        descriptor, lambda _payload, _context: {"routing_id": "routing_1"}, Policy()
    )
    result = asyncio.run(gateway.invoke(_envelope(release, ConsumerType.AGENT)))

    assert result.data["routing_id"]["kind"] == "untrusted_text"
    assert "ai_untrusted_content" in result.warnings


def test_gateway_sanitizes_business_error_details_for_ai_consumers():
    descriptor = _descriptor().model_copy(update={
        "exposure": ExposurePolicy(web=True, agent=True),
    })

    class Policy:
        def authorize(self, *_args):
            return AuthorizationDecision(
                allowed=True, code="allowed", policy_version="policy-7"
            )
        def approve(self, *_args):
            return None
        def project(self, _descriptor, _identity, data):
            return data

    def handler(_payload, _context):
        raise CapabilityBusinessError(
            "resource_not_found", "person@example.com token=top-secret",
            details={"api_token": "top-secret"},
        )

    gateway, release = _gateway(descriptor, handler, Policy())
    result = asyncio.run(gateway.invoke(_envelope(release, ConsumerType.AGENT)))

    assert result.error.details == {}
    assert "top-secret" not in result.error.message
    assert "projection_redacted" in result.warnings


def test_gateway_fails_closed_for_write_when_durable_reliability_is_unavailable():
    descriptor = _descriptor().model_copy(update={"side_effect_level": SideEffectLevel.WRITE})

    class Policy:
        def authorize(self, *_args):
            return AuthorizationDecision(allowed=True, code="allowed", policy_version="policy-7")
        def approve(self, *_args):
            return None
        def project(self, _descriptor, _identity, data):
            return data

    dispatched = []
    gateway, release = _gateway(
        descriptor, lambda *_args: dispatched.append(True) or {"routing_id": "routing_1"}, Policy()
    )
    result = asyncio.run(gateway.invoke(_envelope(release)))

    assert result.error.code == "reliability_unavailable"
    assert dispatched == []


def test_gateway_records_write_outcome_and_audit_outbox_atomically():
    descriptor = _descriptor().model_copy(update={
        "side_effect_level": SideEffectLevel.WRITE, "idempotency_policy": "required",
        "consistency_policy": "eventual",
    })

    class Policy:
        def authorize(self, *_args):
            return AuthorizationDecision(allowed=True, code="allowed", policy_version="policy-7")
        def approve(self, *_args):
            return None
        def project(self, _descriptor, _identity, data):
            return data

    store = InMemoryOutcomeStore()
    coordinator = ReliabilityCoordinator(store, InMemoryRateLimiter(limit=100))
    gateway, release = _gateway(
        descriptor, lambda *_args: {"routing_id": "routing_1"}, Policy(), coordinator
    )
    envelope = _envelope(release).model_copy(update={"idempotency_key": "idem_1"})
    result = asyncio.run(gateway.invoke(envelope))

    assert result.ok is True
    assert store.snapshot()[0].status == "completed"
    assert len(store.pending_audit_events()) == 1


def test_gateway_returns_outcome_unknown_if_provider_returns_but_outcome_commit_fails():
    descriptor = _descriptor().model_copy(update={
        "side_effect_level": SideEffectLevel.WRITE, "idempotency_policy": "required",
        "consistency_policy": "eventual",
    })

    class Policy:
        def authorize(self, *_args):
            return AuthorizationDecision(allowed=True, code="allowed", policy_version="policy-7")
        def approve(self, *_args):
            return None
        def project(self, _descriptor, _identity, data):
            return data

    class FailingCompletionStore(InMemoryOutcomeStore):
        def complete(self, operation_id, result):
            raise RuntimeError("database unavailable after provider return")

    store = FailingCompletionStore()
    coordinator = ReliabilityCoordinator(store, InMemoryRateLimiter(limit=100))
    gateway, release = _gateway(
        descriptor, lambda *_args: {"routing_id": "routing_1"}, Policy(), coordinator
    )
    envelope = _envelope(release).model_copy(update={"idempotency_key": "idem_1"})
    result = asyncio.run(gateway.invoke(envelope))

    assert result.status.value == "outcome_unknown"
    assert result.operation_ref.status.value == "outcome_unknown"
    assert result.error.code == "outcome_persistence_failed"
    assert store.snapshot()[0].status == "outcome_unknown"
    assert store.pending_audit_events()[0].payload["status"] == "outcome_unknown"


def test_idempotent_replay_does_not_require_or_consume_a_second_approval():
    descriptor = _descriptor().model_copy(update={
        "side_effect_level": SideEffectLevel.WRITE, "idempotency_policy": "required",
        "consistency_policy": "eventual",
    })
    approvals = []

    class Policy:
        def authorize(self, *_args):
            return AuthorizationDecision(allowed=True, code="allowed", policy_version="policy-7")
        def approve(self, *_args):
            approvals.append(True)
        def project(self, _descriptor, _identity, data):
            return data

    store = InMemoryOutcomeStore()
    coordinator = ReliabilityCoordinator(store, InMemoryRateLimiter(limit=100))
    gateway, release = _gateway(
        descriptor, lambda *_args: {"routing_id": "routing_1"}, Policy(), coordinator
    )
    envelope = _envelope(release).model_copy(update={"idempotency_key": "idem_1"})

    first = asyncio.run(gateway.invoke(envelope))
    replay = asyncio.run(gateway.invoke(envelope.model_copy(update={"approval_reference": None})))

    assert replay.ok is True and replay.status == first.status
    assert replay.operation_ref == first.operation_ref
    assert replay.data is None
    assert approvals == [True]


def test_gateway_enlists_transactional_provider_outcome_in_same_transaction():
    descriptor = _descriptor().model_copy(update={
        "side_effect_level": SideEffectLevel.WRITE, "idempotency_policy": "required",
    })

    class Policy:
        def authorize(self, *_args):
            return AuthorizationDecision(allowed=True, code="allowed", policy_version="policy-7")
        def approve(self, *_args):
            return None
        def project(self, _descriptor, _identity, data):
            return data

    class TransactionalStore(InMemoryOutcomeStore):
        enlisted = None
        def complete_in_transaction(self, transaction, operation_id, result):
            self.enlisted = transaction
            return self.complete(operation_id, result)

    class Transaction:
        committed = False
        rolled_back = False
        closed = False
        def commit(self): self.committed = True
        def rollback(self): self.rolled_back = True
        def close(self): self.closed = True

    transaction = Transaction()
    store = TransactionalStore()
    coordinator = ReliabilityCoordinator(store, InMemoryRateLimiter(limit=100))
    @transactional_provider
    def handler(*_args):
        return TransactionalCapabilityOutput(
            data={"routing_id": "routing_1"}, transaction=transaction
        )
    gateway, release = _gateway(descriptor, handler, Policy(), coordinator)
    envelope = _envelope(release).model_copy(update={"idempotency_key": "idem_1"})
    result = asyncio.run(gateway.invoke(envelope))

    assert result.ok is True
    assert store.enlisted is transaction
    assert transaction.committed is True
    assert transaction.rolled_back is False
    assert transaction.closed is True


def test_gateway_rolls_back_transactional_provider_when_output_contract_is_invalid():
    descriptor = _descriptor().model_copy(update={
        "side_effect_level": SideEffectLevel.WRITE, "idempotency_policy": "required",
    })

    class Policy:
        def authorize(self, *_args):
            return AuthorizationDecision(allowed=True, code="allowed", policy_version="policy-7")
        def approve(self, *_args): return None
        def project(self, _descriptor, _identity, data): return data

    class Transaction:
        committed = False
        rolled_back = False
        closed = False
        def commit(self): self.committed = True
        def rollback(self): self.rolled_back = True
        def close(self): self.closed = True

    transaction = Transaction()
    store = InMemoryOutcomeStore()
    @transactional_provider
    def handler(*_args):
        return TransactionalCapabilityOutput(
            data={"unexpected": "field"}, transaction=transaction
        )
    gateway, release = _gateway(
        descriptor, handler, Policy(), ReliabilityCoordinator(store, InMemoryRateLimiter(limit=100))
    )
    envelope = _envelope(release).model_copy(update={"idempotency_key": "idem_1"})
    result = asyncio.run(gateway.invoke(envelope))

    assert result.error.code == "provider_failed"
    assert transaction.committed is False
    assert transaction.rolled_back is True
    assert transaction.closed is True
    assert store.snapshot()[0].status == "failed"


def test_gateway_rejects_strong_write_before_nontransactional_provider_dispatch():
    descriptor = _descriptor().model_copy(update={
        "side_effect_level": SideEffectLevel.WRITE,
        "idempotency_policy": "required",
        "consistency_policy": "strong",
    })

    class Policy:
        def authorize(self, *_args):
            return AuthorizationDecision(allowed=True, code="allowed", policy_version="policy-7")
        def approve(self, *_args): return None
        def project(self, _descriptor, _identity, data): return data

    dispatched = []
    gateway, release = _gateway(
        descriptor,
        lambda *_args: dispatched.append(True) or {"routing_id": "routing_1"},
        Policy(), ReliabilityCoordinator(InMemoryOutcomeStore(), InMemoryRateLimiter(limit=100)),
    )
    envelope = _envelope(release).model_copy(update={"idempotency_key": "idem_1"})
    result = asyncio.run(gateway.invoke(envelope))

    assert result.error.code == "transaction_participant_required"
    assert dispatched == []

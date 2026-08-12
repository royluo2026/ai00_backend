from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from backend.capability_v2.contracts import (
    ActorIdentity,
    CapabilityResultV2,
    CapabilityStatus,
    ConsumerDescriptor,
    ConsumerIdentity,
    ConsumerType,
    CorrelationRef,
    SideEffectLevel,
    TenantIdentity,
)
from backend.capability_v2.domain_client import (
    DomainCapabilityClient,
    DomainInvocation,
    DomainInvocationError,
)


@pytest.fixture
def identity():
    return ConsumerIdentity(
        actor=ActorIdentity(
            user_id="user_1",
            authentication_method="service-token",
            authenticated_at=datetime.now(UTC),
        ),
        tenant=TenantIdentity(tenant_id="tenant_1", membership="service"),
        consumer=ConsumerDescriptor(
            type=ConsumerType.AGENT,
            consumer_id="agent.factory-orchestrator",
            agent_run_id="run_1",
        ),
    )


class Descriptor:
    def __init__(self, *, side_effect_level=SideEffectLevel.READ, idempotency_policy="none"):
        self.side_effect_level = side_effect_level
        self.idempotency_policy = idempotency_policy


class Catalog:
    def __init__(self, descriptor):
        self._descriptor = descriptor

    def descriptor(self, capability_id, major_version):
        assert (capability_id, major_version) == ("factory.asset.get", 1)
        return self._descriptor


class RecordingGateway:
    def __init__(self, *, descriptor=None, catalog_release="rel_" + "a" * 32):
        self.catalog_release = catalog_release
        self.envelopes = []
        self._catalog = Catalog(descriptor or Descriptor())
        self.result = CapabilityResultV2(
            ok=True,
            status=CapabilityStatus.COMPLETED,
            capability_id="factory.asset.get",
            major_version=1,
            data={"asset_id": "asset_1"},
            correlation=CorrelationRef(request_id="req_1", trace_id="trace_1"),
        )

    def catalog(self, release_id=None):
        assert release_id in (None, self.catalog_release)
        return self._catalog

    async def invoke(self, envelope):
        self.envelopes.append(envelope)
        return self.result


def test_internal_client_preserves_identity_and_pins_gateway_release(identity):
    gateway = RecordingGateway()
    client = DomainCapabilityClient(gateway)
    deadline = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)

    result = asyncio.run(
        client.invoke(
            DomainInvocation(
                "factory.asset.get",
                1,
                {"asset_id": "asset_1"},
                expected_resource_version="asset-v7",
                approval_reference="approval_1",
            ),
            identity,
            CorrelationRef(request_id="req_1", trace_id="trace_1"),
            deadline=deadline,
        )
    )

    envelope = gateway.envelopes[0]
    assert envelope.identity == identity
    assert envelope.catalog_release == gateway.catalog_release
    assert envelope.capability_id == "factory.asset.get"
    assert envelope.major_version == 1
    assert envelope.payload == {"asset_id": "asset_1"}
    assert envelope.expected_resource_version == "asset-v7"
    assert envelope.approval_reference == "approval_1"
    assert envelope.request_id == "req_1"
    assert envelope.trace_id == "trace_1"
    assert envelope.deadline == deadline
    assert result is gateway.result


@pytest.mark.parametrize("reserved", ["tenant_id", "tenant_gid"])
def test_internal_client_rejects_tenant_in_payload(identity, reserved):
    gateway = RecordingGateway()
    client = DomainCapabilityClient(gateway)

    with pytest.raises(DomainInvocationError, match="tenant_payload_forbidden"):
        asyncio.run(
            client.invoke(
                DomainInvocation(
                    "factory.asset.get",
                    1,
                    {reserved: "other", "asset_id": "asset_1"},
                ),
                identity,
                CorrelationRef(request_id="req_1", trace_id="trace_1"),
            )
        )

    assert gateway.envelopes == []


def test_internal_client_requires_idempotency_from_write_descriptor(identity):
    gateway = RecordingGateway(
        descriptor=Descriptor(
            side_effect_level=SideEffectLevel.WRITE,
            idempotency_policy="required",
        )
    )
    client = DomainCapabilityClient(gateway)

    with pytest.raises(DomainInvocationError, match="idempotency_key_required"):
        asyncio.run(
            client.invoke(
                DomainInvocation("factory.asset.get", 1, {"asset_id": "asset_1"}),
                identity,
                CorrelationRef(request_id="req_1", trace_id="trace_1"),
            )
        )

    assert gateway.envelopes == []


def test_internal_client_forwards_write_when_descriptor_requirements_are_met(identity):
    gateway = RecordingGateway(
        descriptor=Descriptor(
            side_effect_level=SideEffectLevel.WRITE,
            idempotency_policy="required",
        )
    )
    client = DomainCapabilityClient(gateway)

    asyncio.run(
        client.invoke(
            DomainInvocation(
                "factory.asset.get",
                1,
                {"asset_id": "asset_1"},
                idempotency_key="factory-asset-get-1",
            ),
            identity,
            CorrelationRef(request_id="req_1", trace_id=None),
        )
    )

    assert gateway.envelopes[0].idempotency_key == "factory-asset-get-1"
    assert gateway.envelopes[0].trace_id == "req_1"

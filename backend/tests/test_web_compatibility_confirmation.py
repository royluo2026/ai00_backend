from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from backend.capability_v2.contracts import (
    ActorIdentity,
    ConsumerDescriptor,
    ConsumerIdentity,
    ConsumerType,
    InvocationEnvelope,
    TenantIdentity,
)
from backend.capability_v2.web_compatibility import invoke_trusted_web_compatibility


def _envelope(
    *,
    approval_reference: str | None = None,
    consumer_type: ConsumerType = ConsumerType.WEB,
) -> InvocationEnvelope:
    return InvocationEnvelope(
        capability_id="project.list.change.apply",
        major_version=1,
        catalog_release="rel_test",
        payload={"operation": "lists.create", "arguments": {"name": "任务清单"}},
        identity=ConsumerIdentity(
            actor=ActorIdentity(
                user_id="user-1",
                authentication_method="jwt",
                authenticated_at=datetime(2026, 8, 14, tzinfo=UTC),
            ),
            tenant=TenantIdentity(tenant_id="team-1", membership="member"),
            consumer=ConsumerDescriptor(
                type=consumer_type,
                consumer_id="ai00.web.compatibility",
            ),
        ),
        approval_reference=approval_reference,
        request_id="request-1",
        trace_id="trace-1",
    )


class RecordingGateway:
    def __init__(self, first_result):
        self.first_result = first_result
        self.invocations = []
        self.approval_requests = []

    async def invoke(self, envelope):
        self.invocations.append(envelope)
        if len(self.invocations) == 1:
            return self.first_result
        if envelope.approval_reference != "approval-1":
            raise AssertionError("approved retry must carry the issued token")
        return SimpleNamespace(ok=True, data={"data": {"gid": "list-1"}}, error=None)

    async def request_approval(self, envelope):
        self.approval_requests.append(envelope)
        return SimpleNamespace(token="approval-1")


def _failure(code: str):
    return SimpleNamespace(
        ok=False,
        data=None,
        error=SimpleNamespace(code=code, message=code),
    )


def test_confirmation_required_is_approved_and_retried_once_with_same_request():
    gateway = RecordingGateway(_failure("confirmation_required"))
    original = _envelope()

    result = asyncio.run(invoke_trusted_web_compatibility(gateway, original))

    assert result.ok is True
    assert len(gateway.invocations) == 2
    assert len(gateway.approval_requests) == 1
    challenge = gateway.approval_requests[0]
    retried = gateway.invocations[1]
    assert challenge.payload == original.payload
    assert challenge.identity == original.identity
    assert challenge.idempotency_key == "request-1"
    assert retried.payload == original.payload
    assert retried.identity == original.identity
    assert retried.idempotency_key == "request-1"
    assert retried.approval_reference == "approval-1"


def test_successful_read_is_not_approved_or_retried():
    first = SimpleNamespace(ok=True, data={"data": []}, error=None)
    gateway = RecordingGateway(first)

    result = asyncio.run(invoke_trusted_web_compatibility(gateway, _envelope()))

    assert result is first
    assert len(gateway.invocations) == 1
    assert gateway.approval_requests == []


def test_unrelated_gateway_error_is_not_approved_or_retried():
    first = _failure("permission_denied")
    gateway = RecordingGateway(first)

    result = asyncio.run(invoke_trusted_web_compatibility(gateway, _envelope()))

    assert result is first
    assert len(gateway.invocations) == 1
    assert gateway.approval_requests == []


def test_rejected_explicit_approval_is_not_silently_replaced():
    first = _failure("confirmation_required")
    gateway = RecordingGateway(first)

    result = asyncio.run(
        invoke_trusted_web_compatibility(
            gateway, _envelope(approval_reference="caller-approval")
        )
    )

    assert result is first
    assert len(gateway.invocations) == 1
    assert gateway.approval_requests == []


def test_non_web_consumer_is_never_auto_approved():
    first = _failure("confirmation_required")
    gateway = RecordingGateway(first)

    result = asyncio.run(
        invoke_trusted_web_compatibility(
            gateway, _envelope(consumer_type=ConsumerType.AGENT)
        )
    )

    assert result is first
    assert len(gateway.invocations) == 1
    assert gateway.approval_requests == []

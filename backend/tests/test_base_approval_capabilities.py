from __future__ import annotations

import pytest

from backend.base.approval import (
    APPROVAL_CAPABILITY_IDS,
    ApprovalService,
    InMemoryApprovalRepository,
    approval_service_port,
    register_approval_capabilities,
)
from backend.capabilities.models_next import CapabilityBusinessError, CapabilityContext
from backend.capabilities.registry_next import CapabilityRegistry


def _create(service: ApprovalService, *, subject_ref: str = "agent-run-1"):
    return service.create(
        tenant_gid="tenant-1",
        requester_gid="user-1",
        payload={
            "subject_ref": subject_ref,
            "resource_ref": "craft:bop:version-1",
            "revision": "7",
            "content_hash": "sha256:" + "a" * 64,
            "reason": "Publish the reviewed version.",
            "approver_ids": ["reviewer-1"],
        },
    )


def test_pending_approval_search_is_scoped_by_tenant_and_subject_ref():
    service = ApprovalService(InMemoryApprovalRepository())
    first = _create(service)
    _create(service, subject_ref="agent-run-2")
    service.create(
        tenant_gid="tenant-2",
        requester_gid="user-2",
        payload={
            "subject_ref": "agent-run-1",
            "resource_ref": "craft:bop:version-2",
            "revision": "1",
            "content_hash": "sha256:" + "b" * 64,
            "reason": "A different tenant request.",
            "approver_ids": ["reviewer-2"],
        },
    )

    found = service.search(
        tenant_gid="tenant-1",
        subject_ref="agent-run-1",
        status="pending",
    )

    assert [item.approval_id for item in found] == [first.approval_id]


def test_cancel_is_idempotent_per_approval_with_expected_pending_state():
    service = ApprovalService(InMemoryApprovalRepository())
    request = _create(service)

    first = service.cancel(
        tenant_gid="tenant-1",
        approval_id=request.approval_id,
        expected_state="pending",
        actor_gid="user-1",
    )
    repeated = service.cancel(
        tenant_gid="tenant-1",
        approval_id=request.approval_id,
        expected_state="pending",
        actor_gid="user-1",
    )

    assert first.status == repeated.status == "cancelled"
    assert first.updated_at == repeated.updated_at


def test_decide_and_cancel_compete_on_expected_pending_state():
    service = ApprovalService(InMemoryApprovalRepository())
    request = _create(service)
    decided = service.decide(
        tenant_gid="tenant-1",
        approval_id=request.approval_id,
        expected_state="pending",
        actor_gid="reviewer-1",
        decision="approved",
        reason="Evidence matches.",
    )

    assert decided.status == "approved"
    with pytest.raises(CapabilityBusinessError) as raised:
        service.cancel(
            tenant_gid="tenant-1",
            approval_id=request.approval_id,
            expected_state="pending",
            actor_gid="user-1",
        )
    assert raised.value.code == "state_conflict"


def test_approval_requires_explicit_tenant_and_exact_revision_hash():
    service = ApprovalService(InMemoryApprovalRepository())

    with pytest.raises(CapabilityBusinessError) as missing_tenant:
        service.create(
            tenant_gid="",
            requester_gid="user-1",
            payload={
                "subject_ref": "run-1",
                "resource_ref": "craft:bop:v1",
                "revision": "1",
                "content_hash": "sha256:" + "a" * 64,
                "reason": "Review it.",
                "approver_ids": ["reviewer-1"],
            },
        )
    assert missing_tenant.value.code == "tenant_required"

    with pytest.raises(CapabilityBusinessError) as bad_hash:
        service.create(
            tenant_gid="tenant-1",
            requester_gid="user-1",
            payload={
                "subject_ref": "run-1",
                "resource_ref": "craft:bop:v1",
                "revision": "1",
                "content_hash": "not-a-digest",
                "reason": "Review it.",
                "approver_ids": ["reviewer-1"],
            },
        )
    assert bad_hash.value.code == "validation_failed"


def test_approval_capabilities_register_and_search_by_subject_ref():
    registry = CapabilityRegistry()
    service = ApprovalService(InMemoryApprovalRepository())
    approval_service_port.bind(service)
    register_approval_capabilities(registry)
    context = CapabilityContext(user_gid="user-1", team_gid="tenant-1")
    try:
        created = registry.get("base.approval.request.create", 1).handler(
            {
                "subject_ref": "agent-run-1",
                "resource_ref": "craft:bop:v1",
                "revision": "1",
                "content_hash": "sha256:" + "a" * 64,
                "reason": "Review exact revision.",
                "approver_ids": ["reviewer-1"],
            },
            context,
        )
        found = registry.get("base.approval.request.search", 1).handler(
            {"subject_ref": "agent-run-1", "status": "pending"}, context
        )
    finally:
        approval_service_port.clear()

    assert {item.spec.id for item in registry.snapshot()} == APPROVAL_CAPABILITY_IDS
    assert found["items"][0]["approval_id"] == created["approval_id"]

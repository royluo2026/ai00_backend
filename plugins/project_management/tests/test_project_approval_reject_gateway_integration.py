from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from backend.capabilities.registry_next import CapabilityRegistry
from backend.capability_v2.authorization import AuthorizationGrants
from backend.capability_v2.catalog import CatalogResolver, build_release
from backend.capability_v2.catalog_store import InMemoryCatalogStore
from backend.capability_v2.contracts import (
    ActorIdentity,
    CapabilityStatus,
    ConsumerDescriptor,
    ConsumerIdentity,
    ConsumerType,
    InvocationEnvelope,
    TenantIdentity,
)
from backend.capability_v2.gateway import CapabilityGatewayService
from backend.capability_v2.operations import InMemoryOperationStore, OperationService
from backend.capability_v2.outcomes import InMemoryOutcomeStore
from backend.capability_v2.policies import LegacyServerGatewayPolicy
from backend.capability_v2.reliability import (
    ApprovalService,
    InMemoryApprovalStore,
    InMemoryRateLimiter,
    ReliabilityCoordinator,
)
from plugins.project_management.project_management_backend.application.outcomes import (
    project_outcome_port,
)
from plugins.project_management.project_management_backend.application.service import (
    ProjectManagementApplication,
)
from plugins.project_management.project_management_backend.capabilities.reviewed import (
    register_reviewed_capabilities,
)
from plugins.project_management.tests.test_project_approval_reject_capability import (
    InMemoryApprovalRejectRepository,
)


CAPABILITY_ID = "project.approval.order.reject"
PAYLOAD = {
    "order_gid": "order-1",
    "comment": "资料不完整",
    "expected_revision": 7,
}


def test_real_gateway_project_provider_rejects_once_and_replays_terminal_result(monkeypatch):
    repository = InMemoryApprovalRejectRepository()
    application = ProjectManagementApplication(
        repository=repository,
        next_id=iter(("notification-1", "audit-1")).__next__,
    )
    monkeypatch.setattr(project_outcome_port, "provider", application)

    registry = CapabilityRegistry()
    register_reviewed_capabilities(registry)
    provider = registry.get(CAPABILITY_ID, 1)
    release = build_release([provider.descriptor])
    catalog = InMemoryCatalogStore()
    catalog.publish(release)
    policy = LegacyServerGatewayPolicy(
        user_loader=lambda user_gid: {"gid": user_gid, "is_active": True},
        grants_resolver=lambda identity, _user: AuthorizationGrants(
            permissions=("project.manage_any",), capability_scopes=("*",),
            resource_scopes=("*",), data_scopes=("*",),
            policy_version="project-approval-gateway-test",
            tenant_id=identity.tenant.tenant_id,
        ),
        approval_service=ApprovalService(InMemoryApprovalStore()),
    )
    gateway = CapabilityGatewayService(
        CatalogResolver(catalog, registry), policy,
        reliability=ReliabilityCoordinator(
            InMemoryOutcomeStore(), InMemoryRateLimiter(limit=100),
        ),
        operations=OperationService(InMemoryOperationStore()),
    ).bind_release(release.release_id)
    identity = ConsumerIdentity(
        actor=ActorIdentity(
            user_id="reviewer-1", authentication_method="session",
            authenticated_at=datetime.now(UTC),
        ),
        tenant=TenantIdentity(tenant_id="team-1", membership="member"),
        consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id="ai00.web"),
    )

    def envelope(payload, *, key, confirmation=None):
        return InvocationEnvelope(
            capability_id=CAPABILITY_ID,
            major_version=1,
            catalog_release=release.release_id,
            payload=payload,
            identity=identity,
            idempotency_key=key,
            expected_resource_version=str(payload["expected_revision"]),
            approval_reference=confirmation,
            request_id="approval-reject-request",
            trace_id="approval-reject-trace",
        )

    initial = asyncio.run(gateway.invoke(envelope(PAYLOAD, key="reject-operation-1")))
    issued = asyncio.run(gateway.request_approval(envelope(PAYLOAD, key="reject-operation-1")))
    confirmed = asyncio.run(gateway.invoke(envelope(
        PAYLOAD, key="reject-operation-1", confirmation=issued.token,
    )))
    replay = asyncio.run(gateway.invoke(envelope(
        PAYLOAD, key="reject-operation-1", confirmation=issued.token,
    )))

    assert initial.error.code == "confirmation_required"
    assert issued.challenge.capability_id == CAPABILITY_ID
    assert issued.challenge.major_version == 1
    assert confirmed.ok is True and confirmed.status is CapabilityStatus.COMPLETED
    assert confirmed.data == {
        "order_gid": "order-1",
        "status": "rejected",
        "revision": 8,
        "notification_event_gid": "notification-1",
    }
    assert replay.data == confirmed.data
    assert repository.orders["order-1"]["status"] == "rejected"
    assert len(repository.operations) == 1
    assert len(repository.audits) == 1
    assert repository.count_notifications("notification-1") == 1

    stale_payload = {**PAYLOAD, "expected_revision": 7}
    stale_approval = asyncio.run(gateway.request_approval(envelope(
        stale_payload, key="reject-operation-2",
    )))
    stale = asyncio.run(gateway.invoke(envelope(
        stale_payload, key="reject-operation-2", confirmation=stale_approval.token,
    )))
    assert stale.error.code == "version_conflict"
    assert len(repository.operations) == 1
    assert len(repository.audits) == 1
    assert repository.count_notifications("notification-1") == 1

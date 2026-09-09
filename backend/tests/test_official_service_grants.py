from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.capability_v2.delegation import InMemoryDelegationStore
from backend.capability_v2.identity import AuthenticatedPrincipal, IdentityBroker, IdentityError, InMemoryMountStore
from backend.capability_v2.official_service_grants import OfficialServiceIdentityRegistry


NOW = datetime(2026, 9, 9, tzinfo=UTC)


def _principal(service_id: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(service_id=service_id, authentication_method="mtls", authenticated_at=NOW)


def test_official_service_membership_precedes_exact_gateway_grants():
    registry = OfficialServiceIdentityRegistry()
    broker = IdentityBroker(registry, InMemoryDelegationStore(), InMemoryMountStore())
    with registry.trusted_tenant(
        service_id="base-project-validator", tenant_id="team-1",
        source_kind="authenticated_request", source_ref="request-1",
    ):
        identity = broker.for_local_runtime(
            _principal("base-project-validator"), tenant_id="team-1",
            runtime_id="base-project-validator",
        )
        grants = registry.grants(identity)
    assert grants.tenant_id == "team-1"
    assert grants.capability_scopes == ("project.project.validation.get",)
    assert grants.data_scopes == ("confidential",)


def test_unknown_or_cross_tenant_service_fails_during_identity_creation():
    registry = OfficialServiceIdentityRegistry()
    broker = IdentityBroker(registry, InMemoryDelegationStore(), InMemoryMountStore())
    with pytest.raises(IdentityError, match="official_service_unknown"):
        with registry.trusted_tenant(
            service_id="browser-supplied", tenant_id="team-1",
            source_kind="authenticated_request", source_ref="request-1",
        ):
            pass
    with registry.trusted_tenant(
        service_id="project-org-projection", tenant_id="team-1",
        source_kind="project_outbox", source_ref="operation-1",
    ):
        with pytest.raises(IdentityError, match="official_service_tenant_denied"):
            broker.for_worker(
                _principal("project-org-projection"), tenant_id="team-2",
                worker_id="project-org-projection",
            )
    with pytest.raises(IdentityError, match="official_service_tenant_denied"):
        broker.for_worker(
            _principal("project-org-projection"), tenant_id="team-1",
            worker_id="project-org-projection",
        )


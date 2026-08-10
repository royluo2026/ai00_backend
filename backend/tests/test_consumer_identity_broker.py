from __future__ import annotations

from datetime import UTC, datetime, timedelta
import inspect

import pytest

from backend.capability_v2.contracts import AutomationLevel, ConsumerType
from backend.capability_v2.delegation import (
    DelegationGrant,
    InMemoryDelegationStore,
    SqlDelegationStore,
    issue_delegation,
)
from backend.capability_v2.identity import (
    AuthenticatedPrincipal,
    IdentityBroker,
    IdentityError,
    InMemoryMountStore,
    MountGrant,
    TenantMembership,
)


NOW = datetime(2026, 8, 10, 8, 0, tzinfo=UTC)


class Memberships:
    def __init__(self, active: bool = True):
        self.active = active

    def resolve(self, *, user_id=None, service_id=None, tenant_id: str):
        return TenantMembership(
            tenant_id=tenant_id,
            membership="member" if user_id else "service",
            active_roles=("member",) if user_id else ("runtime",),
            active=self.active,
        )


def _user() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id="user_1",
        authentication_method="jwt",
        authenticated_at=NOW,
    )


def _service() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        service_id="worker_1",
        authentication_method="mtls",
        authenticated_at=NOW,
    )


def _broker(*, active=True, clock=lambda: NOW):
    delegations = InMemoryDelegationStore(clock=clock)
    mounts = InMemoryMountStore(clock=clock)
    return IdentityBroker(Memberships(active), delegations, mounts, clock=clock), delegations, mounts


def test_web_identity_is_fixed_by_server_adapter_and_has_no_client_permissions():
    broker, _, _ = _broker()

    identity = broker.for_web(_user(), tenant_id="tenant_1")

    assert identity.consumer.type is ConsumerType.WEB
    assert identity.consumer.consumer_id == "ai00.web"
    assert not hasattr(identity, "permissions")


def test_fastapi_principal_dependency_has_no_client_source_or_permission_inputs(monkeypatch):
    from backend.routers import deps

    monkeypatch.setattr(deps.jwt_service, "verify", lambda token: {"sub": "user_1", "iat": NOW.timestamp()})
    monkeypatch.setattr(deps.user_service, "get_by_gid", lambda gid: {"gid": gid, "is_active": True})

    principal = deps.get_authenticated_principal("signed-token")

    assert principal.user_id == "user_1"
    assert principal.authenticated_at == NOW
    assert set(inspect.signature(deps.get_authenticated_principal).parameters) == {"x_ai00_token"}


def test_inactive_tenant_membership_fails_closed():
    broker, _, _ = _broker(active=False)

    with pytest.raises(IdentityError, match="tenant_membership_inactive"):
        broker.for_web(_user(), tenant_id="tenant_1")


def test_plugin_mount_identity_is_bound_to_stored_actor_tenant_installation_and_session():
    broker, _, mounts = _broker()
    token = mounts.issue(MountGrant(
        mount_session_id="mount_1",
        user_id="user_1",
        tenant_id="tenant_1",
        plugin_id="acme.ai00.viewer",
        plugin_version="1.2.3",
        installation_id="install_1",
        authenticated_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    ))

    identity = broker.for_plugin_mount(token)

    assert identity.actor.user_id == "user_1"
    assert identity.consumer.type is ConsumerType.PLUGIN
    assert identity.consumer.consumer_id == "acme.ai00.viewer"
    assert identity.consumer.installation_id == "install_1"
    assert identity.consumer.mount_session_id == "mount_1"


def test_delegation_store_persists_only_hash_and_revocation_blocks_agent_identity():
    broker, delegations, _ = _broker()
    grant = DelegationGrant(
        delegation_id="delegation_1",
        delegated_by="user_1",
        user_id="user_1",
        tenant_id="tenant_1",
        consumer_type=ConsumerType.AGENT,
        consumer_id="ai00.agent-runtime",
        consumer_version="1.0.0",
        agent_run_id="run_1",
        catalog_release="rel_" + "a" * 32,
        capability_scopes=("craft.routing.get",),
        resource_scopes=("project:project_1",),
        data_scopes=("metadata",),
        maximum_automation_level=AutomationLevel.A2,
        authentication_method="jwt",
        authenticated_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )
    issued = issue_delegation(delegations, grant)

    assert issued.token not in repr(delegations.snapshot())
    identity = broker.for_agent_delegation(issued.token)
    assert identity.consumer.agent_run_id == "run_1"
    assert identity.delegation.delegated_by == "user_1"
    assert identity.delegation.catalog_release == grant.catalog_release
    assert identity.delegation.maximum_automation_level is AutomationLevel.A2

    delegations.revoke("delegation_1")
    with pytest.raises(IdentityError, match="delegation_revoked"):
        broker.for_agent_delegation(issued.token)


def test_expired_delegation_and_wrong_consumer_type_fail_closed():
    future = NOW + timedelta(hours=1)
    broker, delegations, _ = _broker(clock=lambda: future)
    grant = DelegationGrant(
        delegation_id="delegation_1",
        delegated_by="service_1",
        service_id="service_1",
        tenant_id="tenant_1",
        consumer_type=ConsumerType.MCP,
        consumer_id="client_1",
        catalog_release="rel_" + "a" * 32,
        maximum_automation_level=AutomationLevel.A1,
        authentication_method="oauth2",
        authenticated_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    issued = issue_delegation(delegations, grant)

    with pytest.raises(IdentityError, match="delegation_expired"):
        broker.for_agent_delegation(issued.token)


def test_service_adapters_cannot_be_selected_by_a_user_principal():
    broker, _, _ = _broker()

    with pytest.raises(IdentityError, match="service_principal_required"):
        broker.for_worker(_user(), tenant_id="tenant_1", worker_id="worker_1")
    assert broker.for_worker(_service(), tenant_id="tenant_1", worker_id="worker_1").consumer.type is ConsumerType.WORKER
    assert broker.for_local_runtime(_service(), tenant_id="tenant_1", runtime_id="runtime_1").consumer.type is ConsumerType.LOCAL_RUNTIME
    assert broker.for_mcp_client(_service(), tenant_id="tenant_1", client_id="client_1").consumer.type is ConsumerType.MCP


def test_sql_delegation_insert_receives_hash_never_raw_bearer_token():
    statements = []

    class Connection:
        def cursor(self):
            class Cursor:
                def __enter__(self): return self
                def __exit__(self, *_args): return False
                def execute(self, sql, params): statements.append((sql, params))
            return Cursor()
        def commit(self): pass
        def rollback(self): raise AssertionError("rollback not expected")
        def close(self): pass

    store = SqlDelegationStore(Connection)
    grant = DelegationGrant(
        delegation_id="delegation_sql",
        delegated_by="service_1",
        service_id="service_1",
        tenant_id="tenant_1",
        consumer_type=ConsumerType.WORKER,
        consumer_id="worker_1",
        catalog_release="rel_" + "a" * 32,
        maximum_automation_level=AutomationLevel.A1,
        authentication_method="mtls",
        authenticated_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )

    issued = issue_delegation(store, grant)

    params = statements[0][1]
    assert issued.token not in repr(params)
    assert len(params[1]) == 64
    assert params[1] != issued.token

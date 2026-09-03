from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.capability_v2.authorization import AuthorizationGrants, CapabilityAuthorizer
from backend.capability_v2.contracts import (
    ActorIdentity,
    AutomationLevel,
    CapabilityDescriptorV2,
    ConsumerDescriptor,
    ConsumerIdentity,
    ConsumerType,
    DelegationContext,
    ExposurePolicy,
    InvocationEnvelope,
    ResourceSelector,
    TenantIdentity,
)


def _descriptor() -> CapabilityDescriptorV2:
    return CapabilityDescriptorV2(
        id="craft.routing.update", major_version=1, owner_domain="craft",
        title="Update routing", description="Update one routing.",
        use_when="A routing must change.", do_not_use_when="The routing is read only.",
        exposure=ExposurePolicy(web=True, plugin=True, agent=True),
        automation_level=AutomationLevel.A2,
        authorization_policy="craft.write",
        resource_selectors=(ResourceSelector(resource_type="project", payload_path="project_gid"),),
        data_classification="confidential",
        input_schema={
            "type": "object",
            "properties": {"project_gid": {"type": "string"}},
            "required": ["project_gid"],
            "additionalProperties": False,
        },
        output_schema={"type": "object", "properties": {}, "additionalProperties": False},
        schema_hash="sha256:" + "a" * 64,
    )


def _identity(consumer: ConsumerType, *, tenant: str = "tenant_1", delegated_resource="project:p1"):
    delegation = None
    if consumer in {ConsumerType.PLUGIN, ConsumerType.AGENT}:
        delegation = DelegationContext(
            delegation_id=f"delegation_{consumer.value}", delegated_by="user_1",
            capability_scopes=("craft.routing.update",),
            resource_scopes=(delegated_resource,), data_scopes=("confidential",),
            catalog_release="rel_1", maximum_automation_level=AutomationLevel.A2,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
    return ConsumerIdentity(
        actor=ActorIdentity(
            user_id="user_1", authentication_method="jwt", authenticated_at=datetime.now(UTC)
        ),
        tenant=TenantIdentity(tenant_id=tenant, membership="member", active_roles=("engineer",)),
        consumer=ConsumerDescriptor(
            type=consumer, consumer_id=f"test.{consumer.value}",
            agent_run_id="run_1" if consumer is ConsumerType.AGENT else None,
            installation_id="install_1" if consumer is ConsumerType.PLUGIN else None,
            mount_session_id="mount_1" if consumer is ConsumerType.PLUGIN else None,
        ),
        delegation=delegation,
    )


def _envelope(identity, project_gid="p1"):
    return InvocationEnvelope(
        capability_id="craft.routing.update", major_version=1, catalog_release="rel_1",
        payload={"project_gid": project_gid}, identity=identity,
        request_id="request_1", trace_id="trace_1",
    )


@pytest.mark.parametrize(
    ("consumer", "project_gid", "delegated_resource", "expected_code"),
    [
        (ConsumerType.WEB, "p1", "project:p1", "allowed"),
        (ConsumerType.PLUGIN, "p2", "project:p1", "resource_scope_denied"),
        (ConsumerType.AGENT, "p1", "project:p1", "allowed"),
    ],
)
def test_resource_scope_matrix(consumer, project_gid, delegated_resource, expected_code):
    authorizer = CapabilityAuthorizer(
        lambda _identity: AuthorizationGrants(
            permissions=("craft.write",), resource_scopes=("project:*",),
            data_scopes=("confidential",), policy_version="policy-7",
        )
    )
    decision = authorizer.authorize(
        _descriptor(), _envelope(_identity(consumer, delegated_resource=delegated_resource), project_gid),
        required_permissions=("craft.write",),
    )

    assert decision.code == expected_code
    assert decision.allowed is (expected_code == "allowed")
    assert decision.policy_version == "policy-7"


def test_cross_tenant_and_expired_or_overpowered_delegations_fail_closed():
    grants = AuthorizationGrants(
        permissions=("craft.write",), resource_scopes=("project:p1",),
        data_scopes=("confidential",), policy_version="policy-7",
    )
    authorizer = CapabilityAuthorizer(lambda _identity: grants)
    identity = _identity(ConsumerType.AGENT, tenant="tenant_other")
    foreign_tenant_grants = grants.model_copy(update={"tenant_id": "tenant_1"})
    decision = CapabilityAuthorizer(lambda _identity: foreign_tenant_grants).authorize(
        _descriptor(), _envelope(identity), required_permissions=("craft.write",)
    )
    assert decision.code == "tenant_scope_denied"

    excessive = _descriptor().model_copy(update={"automation_level": AutomationLevel.A3})
    decision = authorizer.authorize(excessive, _envelope(_identity(ConsumerType.AGENT)),
                                    required_permissions=("craft.write",))
    assert decision.code == "automation_scope_denied"

    expired_identity = _identity(ConsumerType.AGENT)
    expired_identity = expired_identity.model_copy(update={
        "delegation": expired_identity.delegation.model_copy(update={
            "expires_at": datetime.now(UTC) - timedelta(seconds=1)
        })
    })
    decision = authorizer.authorize(
        _descriptor(), _envelope(expired_identity), required_permissions=("craft.write",)
    )
    assert decision.code == "delegation_expired"


def test_required_resource_selector_missing_fails_closed():
    authorizer = CapabilityAuthorizer(lambda _identity: AuthorizationGrants(
        permissions=("craft.write",), resource_scopes=("project:*",),
        data_scopes=("confidential",), policy_version="policy-7",
    ))
    envelope = _envelope(_identity(ConsumerType.WEB)).model_copy(update={"payload": {}})
    decision = authorizer.authorize(_descriptor(), envelope, required_permissions=("craft.write",))
    assert decision.code == "resource_selector_missing"


def test_effective_data_scopes_are_intersection_of_actor_grant_and_delegation():
    authorizer = CapabilityAuthorizer(lambda _identity: AuthorizationGrants(
        permissions=("craft.write",), resource_scopes=("project:*",),
        data_scopes=("*",), policy_version="policy-7",
    ))
    decision = authorizer.authorize(
        _descriptor(), _envelope(_identity(ConsumerType.AGENT)),
        required_permissions=("craft.write",),
    )

    assert decision.allowed is True
    assert decision.data_scopes == ("confidential",)


def test_legacy_role_bridge_derives_exact_resource_scopes_without_global_widening(monkeypatch):
    from backend.routers import deps

    monkeypatch.setattr(deps, "build_profile", lambda _user: {
        "permissions": ["craft.view"],
        "org_role": "member",
        "grants": [{"grant_type": "project_owner", "scope_gid": "p1"}],
    })
    grants = deps.build_capability_authorization_grants({"gid": "user_1"}, "tenant_1")

    assert grants.resource_scopes == ("project:p1", "tenant:tenant_1")
    assert grants.capability_scopes == ("*",)
    assert "*" not in grants.resource_scopes
    assert grants.data_scopes == ("confidential", "internal")

    with pytest.raises(PermissionError, match="mount identity"):
        deps.build_capability_authorization_grants(
            {"gid": "user_1"}, "tenant_1", "plugin"
        )


def test_team_plugin_manager_receives_restricted_data_scope_without_global_scope(monkeypatch):
    from backend.routers import deps

    monkeypatch.setattr(deps, "build_profile", lambda _user: {
        "permissions": ["system.plugin.manage"],
        "org_role": "member",
        "grants": [{"grant_type": "team_admin", "scope_gid": "team_1"}],
    })
    grants = deps.build_capability_authorization_grants(
        {"gid": "user_1"}, "team_1"
    )

    assert grants.resource_scopes == ("team:team_1", "tenant:team_1")
    assert grants.data_scopes == ("internal", "restricted")
    assert "*" not in grants.resource_scopes
    assert "*" not in grants.data_scopes


def test_connector_local_runtime_receives_only_outcome_projection_scopes(monkeypatch):
    from backend.routers import deps

    monkeypatch.setattr(deps, "build_profile", lambda _user: {
        "permissions": ["simulation.use"], "org_role": "member", "grants": [],
    })
    identity = _identity(ConsumerType.LOCAL_RUNTIME)
    identity = identity.model_copy(update={
        "consumer": ConsumerDescriptor(
            type=ConsumerType.LOCAL_RUNTIME,
            consumer_id="ai00.connector",
            installation_id="device_1",
        ),
        "actor": identity.actor.model_copy(update={
            "authentication_method": "connector_plan_lease",
        }),
    })

    grants = deps.build_capability_authorization_grants(
        {"gid": "user_1"}, "tenant_1", "local_runtime", identity,
    )

    assert set(grants.capability_scopes) == {
        "simulation.connector_capture_outcome.apply",
        "simulation.connector_materialization_outcome.apply",
        "simulation.connector_document_snapshot_outcome.apply",
    }
    assert grants.data_scopes == ("confidential", "internal")

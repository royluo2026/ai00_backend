from pathlib import Path
from datetime import UTC, datetime, timedelta

import pytest

from backend.capabilities.models_next import CapabilityExecution, CapabilityRisk, CapabilitySpec
from backend.capability_v2.v1_adapter import adapt_v1_spec
from backend.capability_v2.contracts import (
    ActorIdentity, AutomationLevel, ConsumerDescriptor, ConsumerIdentity, ConsumerType,
    DelegationContext, TenantIdentity,
)
from backend.routers import agent_capabilities
from backend.routers import deps


ROOT = Path(__file__).resolve().parents[2]


def _spec(*, risk=CapabilityRisk.READ, execution=CapabilityExecution.CLOUD):
    return CapabilitySpec(
        id="system.agent_test", version=1, owner="base", description="Agent test.",
        execution=execution, risk=risk, confirmation="none",
        permissions=(), input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        output_schema={"type": "object", "properties": {}, "additionalProperties": False},
    )


def test_v1_adapter_exposes_only_cloud_reads_to_agent_until_write_providers_are_transactional():
    adapted = adapt_v1_spec(_spec())
    assert adapted.exposure.agent is True
    assert adapted.agent_output_schema == adapted.output_schema
    assert adapt_v1_spec(_spec(risk=CapabilityRisk.WRITE)).exposure.agent is False
    assert adapt_v1_spec(_spec(execution=CapabilityExecution.LOCAL)).exposure.agent is False


def test_agent_service_authentication_fails_closed(monkeypatch):
    monkeypatch.delenv("AGENT_RUNTIME_SERVICE_TOKEN", raising=False)
    with pytest.raises(Exception) as missing:
        agent_capabilities._require_service("anything")
    assert missing.value.status_code == 503
    monkeypatch.setenv("AGENT_RUNTIME_SERVICE_TOKEN", "server-secret-with-at-least-32-bytes")
    with pytest.raises(Exception) as wrong:
        agent_capabilities._require_service("wrong")
    assert wrong.value.status_code == 401
    agent_capabilities._require_service("server-secret-with-at-least-32-bytes")


def test_agent_router_is_registered_and_grants_are_intersected_with_delegation(monkeypatch):
    paths = {route.path for route in agent_capabilities.router.routes}
    assert "/api/v2/agent-capabilities/delegations" in paths
    assert "/api/v2/agent-capabilities/{capability_id}:invoke" in paths
    monkeypatch.setattr(deps, "build_profile", lambda _user: {
        "permissions": ["craft.view"], "grants": [{"grant_type": "project_owner", "scope_gid": "p1"}],
        "org_role": "member",
    })
    now = datetime.now(UTC)
    identity = ConsumerIdentity(
        actor=ActorIdentity(user_id="user_1", authentication_method="test", authenticated_at=now),
        tenant=TenantIdentity(tenant_id="tenant_1", membership="member"),
        consumer=ConsumerDescriptor(type=ConsumerType.AGENT, consumer_id="ai00.agent-runtime", agent_run_id="run_1"),
        delegation=DelegationContext(
            delegation_id="dlg_1", delegated_by="user_1", capability_scopes=("craft.bop.version.get",),
            resource_scopes=("project:p1",), data_scopes=("confidential",),
            catalog_release="rel_0123456789abcdef0123456789abcdef",
            maximum_automation_level=AutomationLevel.A2, expires_at=now + timedelta(hours=1),
        ),
    )
    grants = deps.build_capability_authorization_grants(
        {"gid": "user_1"}, "tenant_1", "agent", identity)
    assert grants.capability_scopes == ("craft.bop.version.get",)
    assert grants.resource_scopes == ("project:p1",)
    assert grants.data_scopes == ("confidential",)
    assert grants.policy_version == "delegation-v2:dlg_1"


def test_agent_runtime_uses_migrations_and_delegated_capability_transport():
    session_store = (ROOT / "services/agent-runtime/src/session-store.ts").read_text(encoding="utf-8")
    client = (ROOT / "services/agent-runtime/src/capability-client.ts").read_text(encoding="utf-8")
    server = (ROOT / "services/agent-runtime/src/server.ts").read_text(encoding="utf-8")
    proxy = (ROOT / "plugins/agent/agent_backend/routers/agent_runtime_proxy_next.py").read_text(encoding="utf-8")
    migration = (ROOT / "backend/db/migrations/202608100006_agent_runs.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE" not in session_store
    assert '"X-AI00-Delegation": delegationToken' in client
    assert '"X-AI00-Service-Credential": this.serviceCredential' in client
    delegated_transport = client.split("private delegatedHeaders", 1)[1]
    assert "X-AI00-Token" not in delegated_transport
    assert "promptRun" in server and "/v1/runs" in server
    assert "input.participants" not in server
    assert "_start_run" in proxy and "/v1/runs/{quote(run_id" in proxy
    assert "/v1/sessions/{quote(session_gid, safe='')}/messages" not in proxy
    assert "workmanship_agent_runs" in migration
    assert "delegation_ciphertext" in migration and "request_ciphertext" in migration
    assert "run_input_ciphertext" in migration and "goal_json" not in migration
    assert "full_result_json" in migration and "projected_result_json" in migration

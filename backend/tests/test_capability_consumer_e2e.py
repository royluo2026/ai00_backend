from datetime import UTC, datetime

from fastapi.testclient import TestClient

from backend.capability_v2.identity import AuthenticatedPrincipal
from backend.capability_v2.contracts import CapabilityResultV2, CapabilityStatus, CorrelationRef
from backend.capability_v2.reliability import ApprovalChallenge, IssuedApproval
from backend.main import app
from backend.routers.deps import get_authenticated_principal, get_current_user


def test_agent_catalog_is_server_filtered_by_permissions_and_deprecation():
    async def user():
        return {"gid": "u1", "team_id": "t1", "system_role": "engineer", "is_active": True}
    app.dependency_overrides[get_current_user] = user
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/capabilities?consumer=agent")
        assert response.status_code == 200
        specs = response.json()["data"]
        ids = {item["id"] for item in specs}
        assert "knowledge.document.history.get" in ids
        assert "knowledge.document.revisions" not in ids
        assert "ontology.release.activate" not in ids
    finally:
        app.dependency_overrides.clear()


def test_public_rest_returns_same_versioned_result_error_evidence_shape(monkeypatch):
    captured = []

    class Gateway:
        catalog_release = "rel_test"

        async def invoke(self, envelope):
            captured.append(envelope)
            return CapabilityResultV2(
                ok=True,
                status=CapabilityStatus.COMPLETED,
                capability_id=envelope.capability_id,
                major_version=envelope.major_version,
                data={},
                correlation=CorrelationRef(
                    request_id=envelope.request_id,
                    trace_id=envelope.trace_id,
                ),
            )

    async def user():
        return {"gid": "u1", "team_id": "t1", "system_role": "engineer", "is_active": True}
    def principal():
        return AuthenticatedPrincipal(
            user_id="u1",
            authentication_method="test-jwt",
            authenticated_at=datetime.now(UTC),
        )
    app.dependency_overrides[get_current_user] = user
    app.dependency_overrides[get_authenticated_principal] = principal
    monkeypatch.setattr(
        "backend.services.user_service.get_by_gid",
        lambda _gid: {"gid": "u1", "system_role": "engineer", "is_active": True},
    )
    monkeypatch.setattr("backend.routers.capabilities.get_default_gateway", lambda: Gateway())
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/capabilities/test.web.read:invoke",
                json={"version": 1, "payload": {}},
                headers={
                    "X-AI00-Source": "worker",
                    "X-AI00-Plugin-ID": "forged.plugin",
                    "X-AI00-Agent-Run-ID": "forged-agent-run",
                    "X-Request-ID": "x" * 300,
                    "X-Trace-ID": "t" * 300,
                },
            )
        assert response.status_code == 200
        result = response.json()["data"]
        assert result["ok"] is True
        assert result["status"] == "completed"
        assert result["capability_id"] == "test.web.read"
        assert result["major_version"] == 1
        assert result["data"] == {}
        assert result["error"] is None
        assert result["correlation"]["request_id"].startswith("cap_")
        assert captured[0].identity.consumer.type.value == "web"
    finally:
        app.dependency_overrides.clear()


def test_confirmation_route_uses_gateway_and_server_constructed_web_identity(monkeypatch):
    captured = []

    class Gateway:
        catalog_release = "rel_test"
        async def request_approval(self, envelope):
            captured.append(envelope)
            return IssuedApproval(
                token="approval-secret-token",
                challenge=ApprovalChallenge(
                    approval_id="approval_1", token_hash="a" * 64,
                    capability_id=envelope.capability_id, major_version=envelope.major_version,
                    consumer_fingerprint="consumer:" + "b" * 64,
                    resource_refs=(), policy_version="policy-7",
                    confirmation_policy="user",
                    payload_hash="sha256:" + "c" * 64,
                    expires_at=datetime.now(UTC),
                ),
            )

    async def user():
        return {"gid": "u1", "team_id": "t1", "system_role": "engineer", "is_active": True}
    def principal():
        return AuthenticatedPrincipal(
            user_id="u1", authentication_method="test-jwt", authenticated_at=datetime.now(UTC)
        )

    app.dependency_overrides[get_current_user] = user
    app.dependency_overrides[get_authenticated_principal] = principal
    monkeypatch.setattr("backend.routers.capabilities.get_default_gateway", lambda: Gateway())
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/capabilities/craft.routing.update:confirm",
                json={"version": 1, "payload": {}},
                headers={"X-AI00-Source": "agent", "X-AI00-Agent-Run-ID": "forged"},
            )
        assert response.status_code == 200
        assert response.json()["data"]["approval_id"] == "approval_1"
        assert captured[0].identity.consumer.type.value == "web"
        assert captured[0].identity.consumer.agent_run_id is None
    finally:
        app.dependency_overrides.clear()

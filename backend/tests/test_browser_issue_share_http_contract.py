from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.capability_v2.contracts import CapabilityResultV2, CapabilityStatus, CorrelationRef
from backend.capability_v2.identity import AuthenticatedPrincipal
from backend.routers import capabilities
from backend.routers.deps import get_authenticated_principal, get_current_user


def test_issue_search_http_preserves_project_provider_envelope(monkeypatch):
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
                data={"data": {"success": True, "data": [
                    {"gid": "issue-1", "list_gid": "list-1", "title": "Issue"},
                ]}},
                correlation=CorrelationRef(
                    request_id=envelope.request_id, trace_id=envelope.trace_id,
                ),
            )

    async def user():
        return {"gid": "u1", "team_id": "t1", "system_role": "engineer", "is_active": True}

    def principal():
        return AuthenticatedPrincipal(
            user_id="u1", authentication_method="test-jwt", authenticated_at=datetime.now(UTC),
        )

    app = FastAPI()
    app.include_router(capabilities._build_router("/api/v1/capabilities"))
    app.dependency_overrides[get_current_user] = user
    app.dependency_overrides[get_authenticated_principal] = principal
    monkeypatch.setattr(capabilities, "get_default_gateway", lambda: Gateway())
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/capabilities/project.issue.read.atomic.issues_search:invoke",
            json={"version": 1, "payload": {"arguments": {"list_gid": "list-1", "page_size": 500}}},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["ok"] is True
    assert body["data"]["data"]["data"] == {"success": True, "data": [
        {"gid": "issue-1", "list_gid": "list-1", "title": "Issue"},
    ]}
    assert captured[0].payload == {"arguments": {"list_gid": "list-1", "page_size": 500}}

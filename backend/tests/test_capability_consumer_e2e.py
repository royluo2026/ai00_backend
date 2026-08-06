from fastapi.testclient import TestClient

from backend.main import app
from backend.routers.deps import get_current_user


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


def test_public_rest_returns_same_versioned_result_error_evidence_shape():
    async def user():
        return {"gid": "u1", "team_id": "t1", "system_role": "engineer", "is_active": True}
    app.dependency_overrides[get_current_user] = user
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/capabilities/system.echo:invoke",
                json={"version": 1, "payload": {"value": 7}},
                headers={"X-AI00-Source": "api"},
            )
        assert response.status_code == 200
        result = response.json()["data"]
        assert set(result) == {"ok", "capability_id", "version", "data", "error", "evidence", "audit"}
        assert result["capability_id"] == "system.echo" and result["version"] == 1
    finally:
        app.dependency_overrides.clear()

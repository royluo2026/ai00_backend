"""Production HTTP composition proof for the Agent orchestration Provider."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from backend.capabilities.registry_next import CapabilityRegistry
from backend.capability_v2.authorization import AuthorizationDecision
from backend.capability_v2.catalog import CatalogResolver, load_catalog_release
from backend.capability_v2.catalog_store import InMemoryCatalogStore
from backend.capability_v2.gateway import CapabilityGatewayService
from backend.capability_v2.identity import AuthenticatedPrincipal
from backend.routers.deps import get_authenticated_principal, get_current_user
from backend.routers.capabilities import get_default_gateway


class _Repository:
    def __init__(self):
        self.calls: list[tuple[str, str, str, int]] = []

    def list_panoramas_for_user(self, actor_gid, *, tenant_gid, project_gid, limit=50):
        self.calls.append((actor_gid, tenant_gid, project_gid, limit))
        return []


class _AllowPolicy:
    def authorize(self, descriptor, envelope, provider):
        return AuthorizationDecision(allowed=True, code="allowed", policy_version="test-policy")

    def approve(self, descriptor, envelope, provider, authorization=None):
        return None

    def project(self, descriptor, identity, data):
        return data

    def issue_approval(self, descriptor, envelope, provider, authorization):
        raise AssertionError("read capability must not request approval")


def test_backend_main_gateway_provider_repository_for_orchestration(monkeypatch):
    """The real backend.main route dispatches to the registered Agent Provider."""
    from backend.capability_v2.catalog import load_catalog_release
    from backend.capability_v2.bootstrap import build_capability_registry
    from plugins.agent.agent_backend.capabilities import register_capabilities

    repository = _Repository()
    registry = CapabilityRegistry()
    register_capabilities(
        registry,
        canvas_runtime=None,
        orchestration_repository_factory=lambda: repository,
    )
    release = load_catalog_release(
        (  # repository-root relative to this test module
            __import__("pathlib").Path(__file__).resolve().parents[2]
            / "docs/governance/capability-catalog-release.json"
        ).read_text(encoding="utf-8")
    )
    artifact = next(item for item in release.provider_artifacts if item.plugin_id == "official.agent")
    registry.bind_provider_artifact("agent", artifact)
    store = InMemoryCatalogStore()
    store.publish(release)
    gateway = CapabilityGatewayService(
        CatalogResolver(store, registry), _AllowPolicy()
    ).bind_release(release.release_id)

    from backend.main import app

    async def user():
        return {"gid": "u-orch", "team_id": "tenant-orch", "is_active": True}

    def principal():
        return AuthenticatedPrincipal(
            user_id="u-orch", authentication_method="test-jwt",
            authenticated_at=datetime.now(UTC),
        )

    app.dependency_overrides[get_current_user] = user
    app.dependency_overrides[get_authenticated_principal] = principal
    monkeypatch.setattr("backend.routers.capabilities.get_default_gateway", lambda: gateway)
    try:
        response = TestClient(app).post(
            "/api/v1/capabilities/agent.orchestration.panorama.read:invoke",
            json={"version": 1, "payload": {
                "tenant_gid": "tenant-orch", "project_gid": "project-orch", "limit": 10,
            }},
        )
        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["data"]["data"] == {"items": []}
        assert repository.calls == [("u-orch", "tenant-orch", "project-orch", 10)]
    finally:
        app.dependency_overrides.clear()

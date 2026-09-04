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
from plugins.agent.agent_backend.orchestration.models import GraphDraft, BusinessNode


class _Repository:
    def __init__(self):
        self.calls: list[tuple[str, str, str, int]] = []

    def list_panoramas_for_user(self, actor_gid, *, tenant_gid, project_gid, limit=50):
        self.calls.append((actor_gid, tenant_gid, project_gid, limit))
        return []

    def get_graph(self, version_gid, *, actor_gid, tenant_gid, project_gid):
        return GraphDraft(nodes=[BusinessNode(
            gid="node-1", node_key="node-1", title="受治理节点",
            x_item_key="TG0", y_item_key="项目管理",
            objective="verify", owner_ref="owner", inputs=[{"name": "in"}],
            outputs=[{"name": "out"}], acceptance_criteria=["ok"],
        )], edges=[])

    def save_graph(self, version_gid, graph, *, expected_revision, actor_gid, tenant_gid, project_gid):
        return expected_revision + 1

    def publish_version(self, version_gid, *, expected_revision, actor_gid, resolved_bindings, tenant_gid, project_gid):
        return {"version_gid": version_gid, "revision": expected_revision + 1, "status": "published"}

    def delete_binding(self, binding_gid, *, actor_gid, tenant_gid, project_gid):
        return None

    def create_run_with_started_event(self, *, panorama_gid, version_gid, frozen_context, actor_gid, tenant_gid, project_gid):
        return "run-1"

    def transition_run_with_event(self, run_gid, *, target_status, authorized_principal_gid, actor_type, event_actor_gid, payload, tenant_gid, project_gid, **kwargs):
        return {"run_gid": run_gid, "status": target_status, "sequence_no": 2, "event_gid": "event-1"}

    def get_metric_for_user(self, panorama_gid, period_key, actor_gid, *, tenant_gid, project_gid):
        return {
            "panorama_gid": panorama_gid, "version_gid": "ver-1", "period_key": period_key,
            "total_workload_hours": 0, "effective_agent_workload_hours": 0,
            "effective_intelligent_work_rate": 0, "automated_workflow_count": 0,
            "total_workflow_count": 0, "automation_ratio": 0, "calculated_at": "2026-01-01T00:00:00+00:00",
        }

    def list_workload_measurements_for_user(self, panorama_gid, period_key, actor_gid, *, tenant_gid, project_gid):
        return []


class _AllowPolicy:
    def authorize(self, descriptor, envelope, provider):
        project_gid = envelope.payload.get("project_gid")
        refs = (f"project:{project_gid}",) if project_gid else ()
        return AuthorizationDecision(allowed=True, code="allowed", policy_version="test-policy", resource_refs=refs)

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

        common = {"tenant_gid": "tenant-orch", "project_gid": "project-orch"}
        requests = {
            "agent.orchestration.graph.read": {**common, "version_gid": "ver-1"},
            "agent.orchestration.metric.read": {**common, "panorama_gid": "pan-1", "period_key": "2026"},
        }
        for capability_id, payload in requests.items():
            result = TestClient(app).post(
                f"/api/v1/capabilities/{capability_id}:invoke",
                json={"version": 1, "payload": payload},
            )
            assert result.status_code == 200, (capability_id, result.text)
            assert result.json()["success"] is True, (capability_id, result.json())
    finally:
        app.dependency_overrides.clear()


def test_orchestration_write_surface_is_deferred_and_not_exposed():
    from backend.capability_v2.catalog import load_catalog_release
    release = load_catalog_release(
        (__import__("pathlib").Path(__file__).resolve().parents[2]
         / "docs/governance/capability-catalog-release.json").read_text(encoding="utf-8")
    )
    deferred = {
        "agent.orchestration.graph.save", "agent.orchestration.version.publish",
        "agent.orchestration.binding.delete", "agent.orchestration.run.start",
        "agent.orchestration.run.transition",
    }
    for descriptor in release.descriptors:
        if descriptor.id in deferred:
            assert descriptor.lifecycle_status.value == "experimental"
            assert not any(descriptor.exposure.model_dump().values())
            assert descriptor.no_consumer_reason

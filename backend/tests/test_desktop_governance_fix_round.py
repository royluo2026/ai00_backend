"""Regressions for authenticated sibling transports and immutable impact evidence."""
import hashlib
import importlib
import json
import subprocess
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.tests.test_desktop_app_capability_governance import ROOT, DESKTOP, signed_claim, test_jwt_key, assert_fixed_git_artifacts
from backend.routers import deps, admin, capability_artifacts

USER = dict(gid="user-1", team_id="tenant-1", is_active=True, system_role="super_admin")


def assert_desktop(identity):
    assert identity.consumer.consumer_id == DESKTOP
    assert identity.consumer.installation_id == "installation-1"
    assert identity.consumer.consumer_version == "1.0.0"


@pytest.fixture
def principal(monkeypatch):
    monkeypatch.setattr(deps.user_service, "get_by_gid", lambda _: USER.copy())
    return deps.get_authenticated_principal(signed_claim())


@pytest.mark.parametrize("module", [
    "backend.routers.capability_operations", "backend.routers.capability_artifacts",
    "plugins.simulation.simulation_backend.routers.environments",
    "plugins.craft.craft_backend.routers.ontology",
])
def test_signed_desktop_sibling_identity(module, principal):
    assert_desktop(importlib.import_module(module)._identity(USER, principal))


def test_signed_desktop_pm_compatibility(principal):
    from plugins.project_management.project_management_backend.api.compatibility import build_web_compatibility_envelope
    envelope = build_web_compatibility_envelope(SimpleNamespace(catalog_release="rel_test"),
        capability_id="project.list.get", payload={}, current_user=USER, principal=principal,
        request_id="req-1", trace_id="trace-1")
    assert_desktop(envelope.identity)


@pytest.mark.parametrize("module,path", [
    ("plugins.simulation.simulation_backend.routers.environments", "/api/simulation/environments"),
    ("plugins.craft.craft_backend.routers.ontology", "/api/ontology/classes"),
    ("backend.routers.workbenches", "/api/workbenches"),
])
def test_signed_desktop_compatibility_http(module, path, principal, monkeypatch):
    from backend.capability_v2.contracts import CapabilityResultV2, CapabilityStatus
    module = importlib.import_module(module)
    captured = []
    class Gateway:
        catalog_release = "rel_test"
        async def invoke(self, envelope):
            captured.append(envelope)
            return CapabilityResultV2(ok=True, status=CapabilityStatus.COMPLETED,
                capability_id=envelope.capability_id, major_version=envelope.major_version,
                data={"data": []}, correlation={"request_id": envelope.request_id})
    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[deps.get_current_user] = lambda: USER.copy()
    app.dependency_overrides[module.get_default_gateway] = Gateway
    monkeypatch.setattr(module, "get_default_gateway", Gateway)
    with TestClient(app) as client:
        response = client.get(path, headers={"X-AI00-Token": signed_claim()})
    assert response.status_code == 200, response.text
    assert_desktop(captured[0].identity)


def test_signed_desktop_admin_http_real_gateway_confirmation(principal, monkeypatch, tmp_path):
    from backend.base import runtime_database_config
    from backend.capabilities.registry_next import CapabilityRegistry
    from backend.capability_v2.catalog import CatalogResolver, build_release
    from backend.capability_v2.catalog_store import InMemoryCatalogStore
    from backend.capability_v2.gateway import CapabilityGatewayService
    from backend.capability_v2.policies import LegacyServerGatewayPolicy
    from backend.capability_v2.reliability import ApprovalService, InMemoryApprovalStore, InMemoryRateLimiter, ReliabilityCoordinator
    from backend.capability_v2.outcomes import InMemoryOutcomeStore
    from backend.capability_v2.authorization import AuthorizationGrants
    registry = CapabilityRegistry()
    runtime_database_config.register_runtime_database_capabilities(registry)
    release = build_release([item.descriptor for item in registry.snapshot()])
    store = InMemoryCatalogStore()
    store.publish(release)
    approvals = ApprovalService(InMemoryApprovalStore())
    policy = LegacyServerGatewayPolicy(user_loader=lambda _: USER.copy(),
        grants_resolver=lambda *_: AuthorizationGrants(permissions=("system.tech_config",), resource_scopes=("*",), data_scopes=("restricted",), policy_version="test"),
        approval_service=approvals)
    gateway = CapabilityGatewayService(CatalogResolver(store, registry), policy,
        reliability=ReliabilityCoordinator(InMemoryOutcomeStore(), InMemoryRateLimiter(limit=100))).bind_release(release.release_id)
    calls = []
    invoke, request_approval = gateway.invoke, gateway.request_approval
    async def record_invoke(envelope):
        result = await invoke(envelope)
        calls.append(("invoke", envelope, result))
        return result
    async def record_approval(envelope):
        issued = await request_approval(envelope)
        calls.append(("approval", envelope, issued))
        return issued
    monkeypatch.setattr(gateway, "invoke", record_invoke)
    monkeypatch.setattr(gateway, "request_approval", record_approval)
    config = tmp_path / "system.json"
    monkeypatch.setattr(runtime_database_config, "system_json_path", lambda: config)
    app = FastAPI()
    app.include_router(admin.router)
    app.dependency_overrides[admin._require_super_claims] = lambda: USER.copy()
    app.dependency_overrides[admin.get_default_gateway] = lambda: gateway
    with TestClient(app) as client:
        response = client.post("/admin/cloud-db-config", headers={"X-AI00-Token": signed_claim()},
            json=dict(host="localhost", port=3306, user="u", password="test", collab_db="c", public_db="p"))
    assert response.status_code == 200, response.text
    assert [row[0] for row in calls] == ["invoke", "approval", "invoke"]
    assert calls[0][2].error.code == "confirmation_required"
    for _, envelope, _ in calls:
        assert_desktop(envelope.identity)
    assert calls[-1][1].approval_reference == calls[1][2].token
    assert json.loads(config.read_text(encoding="utf-8"))["cloud_db_config"]["host"] == "localhost"


@pytest.fixture
def sibling_client(principal):
    app = FastAPI()
    app.include_router(admin.router)
    app.include_router(capability_artifacts.router)
    app.dependency_overrides[deps.get_current_user] = lambda: USER.copy()
    app.dependency_overrides[admin._require_super_claims] = lambda: USER.copy()
    # Gateway must never execute when an override is rejected.
    app.dependency_overrides[admin.get_default_gateway] = lambda: SimpleNamespace(catalog_release="rel_test")
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.mark.parametrize("route,body", [
    ("/admin/cloud-db-config", dict(host="localhost", port=3306, user="u", collab_db="c", public_db="p")),
    ("/api/v2/capability-artifacts/uploads", dict(media_type="application/json", sha256="a"*64, byte_size=2)),
])
@pytest.mark.parametrize("location", ["body", "payload", "header"])
def test_shared_routes_reject_identity_override_before_adapter(sibling_client, route, body, location):
    body = dict(body)
    headers = {"X-AI00-Token": signed_claim()}
    if location == "header":
        headers["X-Consumer-ID"] = "forged"
    elif location == "payload":
        body["payload"] = {"consumer_id": "forged"}
    else:
        body["consumer_id"] = "forged"
    response = sibling_client.post(route, json=body, headers=headers)
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "consumer_identity_override_forbidden"


def test_shared_route_rejects_json_override_without_content_type(sibling_client):
    response = sibling_client.post("/admin/cloud-db-config", headers={"X-AI00-Token": signed_claim()},
        content=json.dumps(dict(host="localhost", port=3306, user="u", collab_db="c", public_db="p", consumer_id="forged")))
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "consumer_identity_override_forbidden"


def test_signed_desktop_artifact_http_keeps_business_json_stream(principal, monkeypatch):
    from backend.capability_v2.artifacts import ArtifactService, InMemoryArtifactStore, InMemoryObjectStorage
    identities = []
    class RecordingArtifacts(ArtifactService):
        def create_upload(self, identity, **kwargs):
            identities.append(identity)
            return super().create_upload(identity, **kwargs)
        def upload_stream(self, upload_id, identity, stream):
            identities.append(identity)
            return super().upload_stream(upload_id, identity, stream)
        def finalize(self, upload_id, identity, **kwargs):
            identities.append(identity)
            return super().finalize(upload_id, identity, **kwargs)
    service = RecordingArtifacts(InMemoryArtifactStore(), InMemoryObjectStorage())
    monkeypatch.setattr(capability_artifacts, "_service", lambda: service)
    monkeypatch.setattr(capability_artifacts, "_granted_resources", lambda *_: ())
    app = FastAPI()
    app.include_router(capability_artifacts.router)
    app.dependency_overrides[deps.get_current_user] = lambda: USER.copy()
    # This is artifact business content, not a consumer identity override.
    data = b'{"consumer_id":"business-record","installation_id":"device-record"}'
    digest = hashlib.sha256(data).hexdigest()
    with TestClient(app) as client:
        headers = {"X-AI00-Token": signed_claim()}
        created = client.post("/api/v2/capability-artifacts/uploads", headers=headers,
            json=dict(media_type="application/json", sha256=digest, byte_size=len(data)))
        assert created.status_code == 201, created.text
        uploaded = client.put(created.json()["upload_url"], content=data,
            headers={**headers, "Content-Type": "application/json"})
        assert uploaded.status_code == 204, uploaded.text
        finalized = client.post(f"/api/v2/capability-artifacts/uploads/{created.json()['upload_id']}:finalize",
            headers=headers, json={"sha256": digest})
        assert finalized.status_code == 200, finalized.text
    assert len(identities) == 3
    for identity in identities:
        assert_desktop(identity)


def test_signed_desktop_operations_http(principal, monkeypatch):
    from backend.routers import capability_operations
    from backend.capability_v2.operations import OperationService, InMemoryOperationStore
    from backend.capability_v2.identity import authenticated_user_identity
    store = InMemoryOperationStore()
    operation = OperationService(store).create(kind="simulation.run",
        requested_by=authenticated_user_identity(USER, principal), resource_refs=())
    captured = []
    class RecordingOperations(OperationService):
        def get_authorized(self, operation_id, identity, **kwargs):
            captured.append(identity)
            return super().get_authorized(operation_id, identity, **kwargs)
    monkeypatch.setattr(capability_operations, "SqlOperationStore", lambda *_: store)
    monkeypatch.setattr(capability_operations, "OperationService", RecordingOperations)
    monkeypatch.setattr(capability_operations, "build_capability_authorization_grants", lambda *_: SimpleNamespace(resource_scopes=()))
    app = FastAPI()
    app.include_router(capability_operations.router)
    app.dependency_overrides[deps.get_current_user] = lambda: USER.copy()
    with TestClient(app) as client:
        response = client.get(f"/api/v2/capability-operations/{operation.operation_id}",
            headers={"X-AI00-Token": signed_claim()})
    assert response.status_code == 200, response.text
    assert_desktop(captured[0])


def test_desktop_principal_does_not_replace_verified_plugin_mount(principal, monkeypatch):
    from datetime import UTC, datetime
    from backend.plugin_platform.mounts import InMemoryMountSessionStore, MountSessionService
    from backend.routers.plugin_marketplace import _plugin_identity
    from backend.capability_v2.contracts import ConsumerType
    monkeypatch.setenv("AI00_PLUGIN_MOUNT_SECRET", "test-secret-value-with-at-least-thirty-two-bytes")
    service = MountSessionService(InMemoryMountSessionStore())
    issued = service.issue(user_id="user-1", tenant_id="tenant-1", installation_id="plugin-install-1",
        plugin_id="acme.ai00.example", plugin_version="2.0.0", artifact_sha256="a"*64,
        catalog_release="rel_"+"b"*32, capability_grants=("craft.routing.get@1",),
        resource_scopes=("project:p1",), data_scopes=("internal",), revocation_version=1,
        authenticated_at=datetime.now(UTC))
    session = service.resolve_for_user(issued.session.mount_session_id,
        current_user_id="user-1", current_tenant_id="tenant-1")
    identity = _plugin_identity(session, USER, principal)
    assert identity.consumer.type is ConsumerType.PLUGIN
    assert identity.consumer.consumer_id == "acme.ai00.example"
    assert identity.consumer.installation_id == "plugin-install-1"
    assert identity.consumer.mount_session_id == session.mount_session_id


def test_static_impact_closure_follows_shared_runtime_imports():
    from backend.scripts.build_desktop_app_governance import build_impact_closure
    document = build_impact_closure()
    paths = {row["path"] for row in document["artifacts"]}
    for name in ("contracts", "operations", "artifacts", "reliability"):
        assert f"backend/capability_v2/{name}.py" in paths
    assert "local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupAdapter.cs" in paths
    assert "local-runtime/src/Ai00.Connector.Contracts/ExecutionPlan.cs" in paths
    assert document["static_dependency_edges"]


def test_impact_generation_uses_fixed_git_tree_ignoring_untracked_and_dirty_sources(monkeypatch, tmp_path):
    from backend.scripts.build_desktop_app_governance import build_impact_closure
    baseline = build_impact_closure()
    path = ROOT / "plugins/simulation/simulation_backend/untracked_desktop_regression.py"
    assert not path.exists()
    tracked = ROOT / "backend/capability_v2/contracts.py"
    original = tracked.read_bytes()
    generator = ROOT / "backend/scripts/build_desktop_app_governance.py"
    generator_original = generator.read_bytes()
    try:
        path.write_text('CAPABILITY = "simulation.vismockup.status.get"\n', encoding="utf-8")
        tracked.write_bytes(original + b"\n# uncommitted identity evidence must not be read\n")
        generator.write_text('raise RuntimeError("mutable generator executed")\n', encoding="utf-8")
        # A fresh interpreter must not load local PYTHONPATH/sitecustomize code.
        (tmp_path / "sitecustomize.py").write_text('print("untracked Python input")\n', encoding="utf-8")
        monkeypatch.setenv("PYTHONPATH", str(tmp_path))
        assert build_impact_closure() == baseline
    finally:
        path.unlink(missing_ok=True)
        tracked.write_bytes(original)
        generator.write_bytes(generator_original)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    assert baseline["source_commit"] == commit
    assert_fixed_git_artifacts(baseline)

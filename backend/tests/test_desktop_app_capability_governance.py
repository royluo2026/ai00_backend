"""Desktop identity must originate in cloud authentication, never Renderer input."""
from datetime import UTC, datetime, timedelta
from pathlib import Path
import json
import hashlib
from types import SimpleNamespace

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.capability_v2.identity import AuthenticatedPrincipal
from backend.routers import capabilities, deps
from backend.services import jwt_service

ROOT = Path(__file__).resolve().parents[2]
DESKTOP = "ai00.desktop.windows-x64"


@pytest.fixture(autouse=True)
def test_jwt_key(monkeypatch):
    monkeypatch.setattr(jwt_service, "get_settings", lambda: SimpleNamespace(jwt_secret="test-only-desktop-secret-32-bytes-long", jwt_expire_hours=1))


@pytest.fixture
def client(monkeypatch):
    user = {"gid": "user-1", "team_id": "tenant-1", "is_active": True, "system_role": "member"}
    monkeypatch.setattr(deps.user_service, "get_by_gid", lambda _: user)
    app = FastAPI()
    app.include_router(capabilities.router)
    app.dependency_overrides[deps.get_current_user] = lambda: user
    with TestClient(app) as client:
        yield client


def unexpected_gateway():
    raise AssertionError("untrusted identity reached Gateway")


def signed_claim(**changes):
    now = datetime.now(UTC)
    payload = dict(sub="user-1", iat=now, exp=now + timedelta(minutes=5),
        desktop_consumer=dict(consumer_id=DESKTOP, tenant_id="tenant-1",
            installation_id="installation-1", consumer_version="1.0.0"))
    payload.update(changes)
    payload = {key: value for key, value in payload.items() if value is not None}
    return jwt.encode(payload, jwt_service.get_settings().jwt_secret, algorithm=jwt_service.ALGORITHM)


@pytest.mark.parametrize("operation", ["invoke", "confirm"])
@pytest.mark.parametrize("field", ["consumer_id", "consumer", "identity", "consumer_type", "desktop_consumer"])
@pytest.mark.parametrize("location", ["body", "payload"])
def test_renderer_identity_override_is_rejected(client, monkeypatch, operation, field, location):
    # No catalog/database/provider should be touched for an identity override.
    monkeypatch.setattr(capabilities, "get_default_gateway", unexpected_gateway)
    body = {"version": 1, "payload": {}}
    (body if location == "body" else body["payload"])[field] = "forged-browser"
    response = client.post(f"/api/v1/capabilities/simulation.vismockup.status.get:{operation}",
        json=body, headers={"X-AI00-Token": signed_claim()})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "consumer_identity_override_forbidden"


def test_server_signed_desktop_claim_survives_authentication_and_router():
    assert hasattr(jwt_service, "sign_desktop_session"), "server desktop session issuer missing"
    now = datetime.now(UTC)
    principal = AuthenticatedPrincipal(user_id="user-1", authentication_method="oauth2_pkce", authenticated_at=now)
    token = jwt_service.sign_desktop_session(principal, tenant_id="tenant-1", installation_id="installation-1", consumer_version="1.0.0")
    claim = jwt_service.verify(token)["desktop_consumer"]
    assert claim["consumer_id"] == DESKTOP
    assert claim["tenant_id"] == "tenant-1"


def test_verified_claim_becomes_trusted_identity(client, monkeypatch):
    captured = []
    class Gateway:
        catalog_release = "rel_" + "a" * 32
        async def invoke(self, envelope):
            from backend.capability_v2.contracts import CapabilityResultV2, CapabilityStatus
            captured.append(envelope)
            return CapabilityResultV2(ok=True, status=CapabilityStatus.COMPLETED,
                capability_id=envelope.capability_id, major_version=1, data={}, correlation={"request_id": envelope.request_id})
    monkeypatch.setattr(capabilities, "get_default_gateway", Gateway)
    response = client.post("/api/v1/capabilities/simulation.connector.binding.get:invoke",
        json={"version": 1, "payload": {}}, headers={"X-AI00-Token": signed_claim(), "X-Consumer-ID": "forged"})
    assert response.status_code == 200
    identity = captured[0].identity
    assert identity.consumer.consumer_id == DESKTOP
    assert identity.consumer.installation_id == "installation-1"
    assert identity.actor.user_id == "user-1"
    assert identity.tenant.tenant_id == "tenant-1"


@pytest.mark.parametrize("claim", [
    {"consumer_id": "forged"},
    {"consumer_id": DESKTOP, "tenant_id": "other", "installation_id": "installation-1", "consumer_version": "1.0.0"},
    {"consumer_id": DESKTOP, "tenant_id": "tenant-1", "installation_id": "installation-1", "consumer_version": "1.0.0", "permissions": ["*"]},
])
def test_invalid_or_wrong_tenant_signed_claim_fails_closed(client, monkeypatch, claim):
    monkeypatch.setattr(capabilities, "get_default_gateway", unexpected_gateway)
    response = client.post("/api/v1/capabilities/simulation.connector.binding.get:invoke",
        json={"version": 1}, headers={"X-AI00-Token": signed_claim(desktop_consumer=claim)})
    assert response.status_code == 401


def test_desktop_consumer_registration_and_simulation_provider_bindings():
    from backend.scripts.build_capability_catalog import _verified_consumer_refs
    refs = _verified_consumer_refs("simulation.connector.pairing.approve", 2)
    assert {"consumer_id": DESKTOP, "consumer_type": "web", "version_constraint": "==2"} in refs
    from plugins.simulation.simulation_backend.capabilities import connector_pairing, connector_runtime
    assert hasattr(connector_pairing, "DESKTOP_CAPABILITY_BINDINGS")
    assert hasattr(connector_runtime, "DESKTOP_CAPABILITY_BINDINGS")
    assert hasattr(connector_runtime, "DESKTOP_TRANSPORT_BINDINGS")
    from backend.capabilities.registry_next import CapabilityRegistry
    from plugins.simulation.simulation_backend.capabilities import register_capabilities
    registry = CapabilityRegistry()
    register_capabilities(registry)
    for key in (*connector_pairing.DESKTOP_CAPABILITY_BINDINGS, *connector_runtime.DESKTOP_CAPABILITY_BINDINGS):
        item = registry.get(*key)
        assert item.spec.owner == item.descriptor.owner_domain == "simulation"
        assert item.descriptor.exposure.web
    for row in connector_runtime.DESKTOP_TRANSPORT_BINDINGS:
        assert row["owner"] == "simulation"
        assert row["consumer_id"] == "ai00.connector"
        from backend.routers.simulation_connector import router
        route = next(r for r in router.routes if r.path == row["route"])
        assert route.endpoint.__name__ == row["handler"]
        if row["method"] != "WEBSOCKET": assert row["method"] in route.methods


def test_native_registry_generator_preserves_exact_desktop_bindings():
    from backend.scripts.build_user_function_registry import discover_user_functions, _defaults
    rows = {r["function_id"]: _defaults(r) for r in discover_user_functions()}
    row = rows.get("desktop_capability:simulation.connector.pairing.approve@2")
    assert row is not None, "native Registry generator omits desktop consumer"
    assert row["target_capability"] == "simulation.connector.pairing.approve"
    assert row["target_major_version"] == 2
    assert row["owner"] == "Simulation"
    assert row["current_consumers"] == [DESKTOP]


def test_desktop_impact_closure_is_generated_and_truthful():
    path = ROOT / "docs/governance/desktop-app-impact-closure.json"
    assert path.is_file(), "computed App impact closure missing"
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["consumer_id"] == DESKTOP
    assert document["human_approved"] is False
    assert document["runtime_verified"] is False
    assert document["technical_release_approved"] is False
    assert document["unverified_artifacts"]
    assert document["capabilities"]
    assert document["artifacts"]


def test_impact_source_hashes_survive_git_line_ending_conversion():
    document = json.loads((ROOT / "docs/governance/desktop-app-impact-closure.json").read_text(encoding="utf-8"))
    for artifact in document["artifacts"]:
        content = (ROOT / artifact["path"]).read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        assert artifact["sha256"] == "sha256:" + hashlib.sha256(content).hexdigest(), artifact["path"]


def test_native_registry_includes_device_transport_consumer_and_owner():
    from backend.scripts.build_user_function_registry import discover_user_functions
    rows = {r["function_id"]: r for r in discover_user_functions()}
    for key in ("rest:POST:/api/v1/simulation/connectors/v2/plans/{plan_id}/outcome",
                "rest:WEBSOCKET:/api/v1/simulation/connectors/v2/plans/wake"):
        assert key in rows
        assert "ai00.connector" in rows[key]["current_consumers"]
        assert rows[key]["domain"] == "Simulation"


@pytest.mark.parametrize("version", [0, True, "2"])
def test_registry_schema_rejects_invalid_desktop_major_pins(version):
    from backend.scripts.build_user_function_registry import validate_registry_document
    document = json.loads((ROOT / "docs/governance/user-function-registry.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "docs/governance/user-function-registry.schema.json").read_text(encoding="utf-8"))
    document["functions"]["desktop_capability:simulation.connector.pairing.approve@2"]["target_major_version"] = version
    assert "record has invalid target_major_version" in validate_registry_document(document, schema)


@pytest.mark.parametrize("changes", [{"exp": None}, {"iat": None}])
def test_desktop_authentication_requires_signed_session_time_bounds(client, monkeypatch, changes):
    monkeypatch.setattr(capabilities, "get_default_gateway", unexpected_gateway)
    response = client.post("/api/v1/capabilities/simulation.connector.binding.get:invoke",
        json={"version": 1}, headers={"X-AI00-Token": signed_claim(**changes)})
    assert response.status_code == 401


def test_compatibility_adapter_preserves_authenticated_desktop_claim(client):
    from backend.capability_v2.web_compatibility import build_trusted_web_envelope
    principal = deps.get_authenticated_principal(signed_claim())
    envelope = build_trusted_web_envelope(SimpleNamespace(catalog_release="rel_" + "a"*32),
        capability_id="simulation.connector.binding.get", payload={},
        current_user={"gid": "user-1", "team_id": "tenant-1"}, principal=principal,
        consumer_id="ai00.web.simulation", request_id="req-1", trace_id="trace-1")
    assert envelope.identity.consumer.consumer_id == DESKTOP


def test_gateway_rejects_payload_identity_before_catalog_resolution():
    import asyncio
    from backend.capability_v2.gateway import CapabilityGatewayService
    from backend.capability_v2.contracts import InvocationEnvelope
    gateway = CapabilityGatewayService(None)
    envelope = InvocationEnvelope(capability_id="simulation.vismockup.status.get", major_version=1,
        catalog_release="rel_" + "a" * 32, payload={"consumer_id": "forged"},
        identity=capabilities._web_identity({"gid": "user-1", "team_id": "tenant-1"},
            AuthenticatedPrincipal(user_id="user-1", authentication_method="jwt", authenticated_at=datetime.now(UTC))),
        request_id="req-1", trace_id="trace-1")
    result = asyncio.run(gateway.invoke(envelope))
    assert result.error.code == "consumer_identity_override_forbidden"


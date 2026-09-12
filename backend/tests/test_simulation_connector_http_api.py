from __future__ import annotations

from pathlib import Path
import asyncio
import hashlib
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.routers import simulation_connector


def test_pairing_http_surface_is_canonical_simulation_owned():
    paths = {route.path for route in simulation_connector.router.routes}
    assert paths == {
        "/api/v1/simulation/connectors/pairings",
        "/api/v1/simulation/connectors/pairings/{user_code}",
        "/api/v1/simulation/connectors/pairings/{user_code}/approve",
        "/api/v1/simulation/connectors/pairings/{pairing_id}/complete",
        "/api/v1/simulation/connectors/pairings/{pairing_id}/activate",
        "/api/v1/simulation/connectors/binding",
        "/api/v1/simulation/connectors/heartbeat",
        "/api/v1/simulation/connectors/plans/lease",
        "/api/v1/simulation/connectors/plans/wake",
        "/api/v1/simulation/connectors/plans/{plan_id}/artifacts/{artifact_id}/content",
        "/api/v1/simulation/connectors/v2/pairings",
        "/api/v1/simulation/connectors/v2/pairings/{pairing_id}/activate",
        "/api/v1/simulation/connectors/v2/runtime/challenge",
        "/api/v1/simulation/connectors/v2/runtime/register",
        "/api/v1/simulation/connectors/v2/runtime/reconciliation/register",
        "/api/v1/simulation/connectors/v2/heartbeat",
        "/api/v1/simulation/connectors/v2/runtime/renew",
        "/api/v1/simulation/connectors/v2/runtime/restart",
        "/api/v1/simulation/connectors/v2/plans/lease",
        "/api/v1/simulation/connectors/v2/plans/{plan_id}/artifacts/{artifact_id}",
        "/api/v1/simulation/connectors/v2/plans/{plan_id}/artifacts/{artifact_id}/content",
        "/api/v1/simulation/connectors/v2/plans/{plan_id}/steps/{step_id}/result-artifact",
        "/api/v1/simulation/connectors/v2/plans/wake",
        "/api/v1/simulation/connectors/v2/plans/{plan_id}/outcome",
        "/api/v1/simulation/connectors/v2/plans/{plan_id}/acknowledge",
        "/api/v1/simulation/connectors/v2/plans/{plan_id}/probe",
        "/api/v1/simulation/connectors/v2/plans/{plan_id}/reconcile",
        "/api/v1/simulation/connectors/plans/{plan_id}/complete",
        "/api/v1/simulation/connectors/plans/{plan_id}/artifacts/{artifact_id}",
        "/api/v1/simulation/connectors/plans/{plan_id}/steps/{step_id}/result-artifact",
    }


def test_pairing_http_adapters_invoke_capabilities_instead_of_domain_service_directly():
    source = Path(simulation_connector.__file__).read_text(encoding="utf-8")

    assert "default_service" not in source
    assert "get_default_gateway" in source
    assert '"simulation.connector.pairing.request"' in source
    assert '"simulation.connector.pairing.complete"' in source
    assert '"simulation.connector.pairing.activate"' in source


def test_pairing_approval_requires_existing_feishu_identity():
    with pytest.raises(HTTPException) as missing:
        simulation_connector._feishu_user({"gid": "user-1", "feishu_open_id": ""})
    assert missing.value.status_code == 403
    assert missing.value.detail == {"code": "feishu_login_required"}

    user = {"gid": "user-1", "feishu_open_id": "ou_123"}
    assert simulation_connector._feishu_user(user) is user


def test_v2_rejects_browser_identity_without_device_session():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(simulation_connector.router)
    with TestClient(app) as client:
        for path in ('heartbeat', 'runtime/renew', 'plans/lease'):
            response = client.post('/api/v1/simulation/connectors/v2/' + path, json={}, headers={'Authorization': 'Bearer web-token'})
            assert response.status_code in (401, 422)


def test_runtime_restart_uses_authenticated_old_instance_and_body_new_instance(monkeypatch):
    from datetime import UTC, datetime
    from plugins.simulation.simulation_backend.data.connector_repository import RuntimeSession

    calls = []

    class FakeRuntimeSessions:
        def authenticate(self, **pins):
            return pins

        def restart(self, new_runtime_instance_id, token, **pins):
            calls.append((new_runtime_instance_id, token, pins))
            return RuntimeSession("device-1", 7, new_runtime_instance_id, datetime.now(UTC), "new-token")

    monkeypatch.setattr(simulation_connector, "runtime_session_service", FakeRuntimeSessions())
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(simulation_connector.router)
    headers = {
        "X-AI00-Device-ID": "device-1",
        "X-AI00-Runtime-Generation": "7",
        "X-AI00-Runtime-Instance-ID": "old-app",
        "X-AI00-Runtime-Type": "electron",
        "X-AI00-Runtime-Session": "session-token",
    }
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/simulation/connectors/v2/runtime/restart",
            headers=headers,
            json={"runtime_instance_id": "new-app"},
        )

    assert response.status_code == 200
    assert calls == [("new-app", "session-token", {
        "device_id": "device-1",
        "generation": 7,
        "runtime_instance_id": "old-app",
        "runtime_type": "electron",
    })]


def test_v2_capture_upload_requires_the_leased_capture_step(monkeypatch):
    from starlette.requests import Request
    from backend.contracts.connector_execution_plan_v2 import canonicalize_v2, compute_plan_hash
    plan = json.loads((Path(__file__).parent / "fixtures" / "connector_execution_plan_v2.json").read_text())["plan"]
    plan["actor_id"], plan["tenant_id"] = "user-1", "team-1"
    step = plan["steps"][0]
    step["step_id"] = "step-1"
    step["operation_id"] = "vismockup.view.capture@1"
    step["payload"] = {"artifact_resource_refs": ["craft-bop-version:bop-1"]}
    step["payload_hash"] = "sha256:" + hashlib.sha256(canonicalize_v2(step["payload"])).hexdigest()
    plan["plan_hash"] = compute_plan_hash(plan)
    payload = b"capture bytes representing png"
    digest = hashlib.sha256(payload).hexdigest()
    calls = []

    class Sessions:
        def leased_plan(self, **pins):
            calls.append(pins)
            return plan

    class Artifacts:
        def __init__(self, *_args): pass
        def create_upload(self, identity, **kwargs):
            calls.append((identity.actor.user_id, kwargs["resource_refs"], kwargs["expected_sha256"]))
            return SimpleNamespace(upload_id="upload-1")
        def upload_stream(self, upload_id, _identity, stream):
            calls.append((upload_id, stream.read()))
        def finalize(self, upload_id, _identity, **kwargs):
            calls.append((upload_id, kwargs["reported_sha256"]))
            return SimpleNamespace(model_dump=lambda **_kwargs: {"artifact_id": "artifact-1"})

    monkeypatch.setattr(simulation_connector, "runtime_session_service", Sessions())
    import backend.capability_v2.artifacts as artifacts
    monkeypatch.setattr(artifacts, "ArtifactService", Artifacts)
    monkeypatch.setattr(artifacts, "SqlArtifactStore", lambda *_args: object())
    monkeypatch.setattr(artifacts, "configured_object_storage", lambda: object())

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    result = asyncio.run(simulation_connector.runtime_capture_artifact(
        "plan-1", "step-1", Request({"type": "http"}, receive),
        lease_id="lease-1", content_sha256=digest, content_length=len(payload),
        pins={"device_id": "device-1"},
    ))
    assert result["data"]["artifact_ref"]["artifact_id"] == "artifact-1"
    assert ("user-1", ("craft-bop-version:bop-1",), digest) in calls
    assert ("upload-1", payload) in calls

    with pytest.raises(HTTPException) as rejected:
        asyncio.run(simulation_connector.runtime_capture_artifact(
            "plan-1", "other-step", Request({"type": "http"}, receive),
            lease_id="lease-1", content_sha256=digest, content_length=len(payload),
            pins={"device_id": "device-1"},
        ))
    assert rejected.value.status_code == 409


def test_app_heartbeat_forwards_a_bounded_adapter_probe_with_runtime_pins(monkeypatch):
    calls = []

    class Sessions:
        def heartbeat(self, **kwargs):
            calls.append(kwargs)
            return {"accepted": True}

    monkeypatch.setattr(simulation_connector, "runtime_session_service", Sessions())
    body = simulation_connector.RuntimeHeartbeatBody.model_validate({
        "adapter": {
            "adapter_id": "ai00.vismockup", "adapter_major": 1,
            "product_id": "siemens.vismockup", "product_version": "14.0.0",
            "operations": [{"operation_id": "vismockup.view.capture@1",
                            "contract_hash": "sha256:" + "a" * 64}],
        },
        "health": {"ready": True, "status": "ready", "process_ready": True,
                   "document_ready": True, "product_version": "14.3.0"},
    })

    result = simulation_connector.runtime_heartbeat(
        body, pins={"device_id": "device-1", "token": "session-1"},
    )

    assert result["data"] == {"accepted": True}
    assert calls[0]["device_id"] == "device-1"
    assert calls[0]["advertisement"]["health"]["product_version"] == "14.3.0"

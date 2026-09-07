from __future__ import annotations

from pathlib import Path

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
        "/api/v1/simulation/connectors/v2/plans/lease",
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

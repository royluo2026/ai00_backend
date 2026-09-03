from __future__ import annotations

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
        "/api/v1/simulation/connectors/binding",
        "/api/v1/simulation/connectors/heartbeat",
        "/api/v1/simulation/connectors/plans/lease",
        "/api/v1/simulation/connectors/plans/{plan_id}/complete",
        "/api/v1/simulation/connectors/plans/{plan_id}/artifacts/{artifact_id}",
        "/api/v1/simulation/connectors/plans/{plan_id}/steps/{step_id}/result-artifact",
    }


def test_pairing_approval_requires_existing_feishu_identity():
    with pytest.raises(HTTPException) as missing:
        simulation_connector._feishu_user({"gid": "user-1", "feishu_open_id": ""})
    assert missing.value.status_code == 403
    assert missing.value.detail == {"code": "feishu_login_required"}

    user = {"gid": "user-1", "feishu_open_id": "ou_123"}
    assert simulation_connector._feishu_user(user) is user

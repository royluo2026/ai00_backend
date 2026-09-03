from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.capability_v2.contracts import OperationStatus
from backend.capability_v2.provider_contracts import CapabilityContext
from backend.contracts.connector_execution_plan_v1 import ConnectorExecutionPlanV1
from plugins.device.device_backend.capabilities.connector_runtime import (
    ConnectorControlPlane,
    ConnectorError,
    ConnectorHealth,
    require_compatible,
    register_connector_runtime_capabilities,
)


NOW = datetime(2026, 9, 3, 8, 0, tzinfo=UTC)
VECTOR = json.loads(
    (Path(__file__).with_name("fixtures") / "connector_execution_plan_v1.json").read_text(
        encoding="utf-8"
    )
)


def healthy(session_id="session-1"):
    return ConnectorHealth.model_validate({
        "connector_version": "1.0.0",
        "protocol_versions": ["ai00.connector.execution-plan.v1"],
        "bound_user_id": "user-001",
        "session_id": session_id,
        "user_session_present": True,
        "session_host_ready": True,
        "system_awake": True,
        "adapters": [{
            "adapter_id": "ai00.vismockup",
            "adapter_major": 1,
            "product_id": "siemens.vismockup",
            "product_version": "14.2.0",
            "operations": [{
                "operation_id": "vismockup.application.probe@1",
                "contract_hash": "sha256:" + "1" * 64,
            }],
        }],
        "reported_at": NOW.isoformat().replace("+00:00", "Z"),
    })


def plan():
    return ConnectorExecutionPlanV1.model_validate(VECTOR["plan"])


class MemoryRepository:
    def __init__(self):
        self.health = {}
        self.plans = {}

    def get_health(self, device_id):
        return self.health.get(device_id)

    def save_health(self, device_id, health):
        self.health[device_id] = health

    def insert_plan(self, value):
        self.plans[value.plan_id] = value

    def lease_plan(self, device_id, lease_seconds):
        self.leased = (device_id, lease_seconds)
        return {"lease_id": "lease-1", "plan": VECTOR["plan"]}


def test_heartbeat_is_closed_and_records_adapter_contract_hashes():
    health = healthy()

    assert health.adapters[0].operations[0].contract_hash.startswith("sha256:")
    with pytest.raises(ValueError):
        ConnectorHealth.model_validate({**health.model_dump(mode="json"), "secret": "no"})

    duplicate = health.model_dump(mode="json")
    duplicate["adapters"][0]["operations"].append(
        duplicate["adapters"][0]["operations"][0]
    )
    with pytest.raises(ValueError, match="duplicate_adapter_operation"):
        ConnectorHealth.model_validate(duplicate)

    duplicate_adapter = health.model_dump(mode="json")
    duplicate_adapter["adapters"].append(duplicate_adapter["adapters"][0])
    with pytest.raises(ValueError, match="duplicate_adapter"):
        ConnectorHealth.model_validate(duplicate_adapter)

    naive = health.model_dump(mode="json")
    naive["reported_at"] = "2026-09-03T08:00:00"
    with pytest.raises(ValueError, match="timezone-aware"):
        ConnectorHealth.model_validate(naive)


def test_heartbeat_rejects_another_fresh_session_or_user():
    repository = MemoryRepository()
    control_plane = ConnectorControlPlane(repository, clock=lambda: NOW)
    control_plane.record_heartbeat("device-001", "user-001", healthy("session-1"))

    with pytest.raises(ConnectorError, match="interactive_session_conflict"):
        control_plane.record_heartbeat("device-001", "user-001", healthy("session-2"))
    with pytest.raises(ConnectorError, match="bound_user_mismatch"):
        control_plane.record_heartbeat("device-001", "other-user", healthy("session-1"))


def test_stale_session_can_be_replaced_for_the_same_bound_user():
    repository = MemoryRepository()
    old = healthy("session-1").model_copy(update={"reported_at": NOW - timedelta(minutes=3)})
    repository.save_health("device-001", old)
    control_plane = ConnectorControlPlane(repository, clock=lambda: NOW)

    control_plane.record_heartbeat("device-001", "user-001", healthy("session-2"))

    assert repository.health["device-001"].session_id == "session-2"


def test_queue_checks_protocol_adapter_operation_and_contract_hash():
    health = healthy()
    require_compatible(plan(), health)

    wrong_hash = health.model_copy(update={
        "adapters": (health.adapters[0].model_copy(update={
            "operations": (health.adapters[0].operations[0].model_copy(update={
                "contract_hash": "sha256:" + "9" * 64
            }),)
        }),)
    })
    with pytest.raises(ConnectorError, match="adapter_contract_mismatch"):
        require_compatible(plan(), wrong_hash)


def test_queue_checks_the_target_product_version_range():
    current = plan()
    assert current.target_product.product_id == "siemens.vismockup"

    old_product = healthy().model_copy(update={
        "adapters": (healthy().adapters[0].model_copy(update={"product_version": "13.9.0"}),)
    })
    with pytest.raises(ConnectorError, match="connector_version_incompatible"):
        require_compatible(current, old_product)

    equivalent_minimum = healthy().model_copy(update={
        "adapters": (healthy().adapters[0].model_copy(update={"product_version": "14.0"}),)
    })
    require_compatible(current, equivalent_minimum)


def test_queue_persists_only_a_compatible_plan_and_returns_operation_ref():
    repository = MemoryRepository()
    repository.save_health("device-001", healthy())
    control_plane = ConnectorControlPlane(repository, clock=lambda: NOW)

    result = control_plane.queue_plan(
        plan(), CapabilityContext(user_gid="user-001", team_gid="tenant-001")
    )

    assert result.status is OperationStatus.ACCEPTED
    assert repository.plans["plan-001"].plan_hash == plan().plan_hash


def test_lease_requires_a_fresh_ready_bound_session():
    repository = MemoryRepository()
    control_plane = ConnectorControlPlane(repository, clock=lambda: NOW)

    with pytest.raises(ConnectorError, match="connector_offline"):
        control_plane.lease_plan("device-001", 60)

    repository.save_health("device-001", healthy().model_copy(update={"session_host_ready": False}))
    with pytest.raises(ConnectorError, match="interactive_session_missing"):
        control_plane.lease_plan("device-001", 60)

    repository.save_health("device-001", healthy())
    assert control_plane.lease_plan("device-001", 60)["lease_id"] == "lease-1"


def test_connector_capabilities_are_registered_with_closed_contracts():
    class Registry:
        def __init__(self):
            self.items = []

        def register(self, spec, handler, *, descriptor):
            self.items.append((spec, descriptor))

    registry = Registry()
    register_connector_runtime_capabilities(registry, ConnectorControlPlane(MemoryRepository()))

    by_id = {spec.id: (spec, descriptor) for spec, descriptor in registry.items}
    assert set(by_id) == {"device.connector.health.get", "device.connector.plan.queue"}
    for spec, descriptor in by_id.values():
        assert spec.input_schema["additionalProperties"] is False
        assert spec.output_schema["additionalProperties"] is False
        assert descriptor.evidence_policy == "required"


def test_connector_heartbeat_route_passes_authenticated_device_identity(monkeypatch):
    from backend.routers import device_runtime

    calls = []
    monkeypatch.setattr(
        device_runtime,
        "record_connector_heartbeat",
        lambda device_id, owner_user_id, health: calls.append(
            (device_id, owner_user_id, health.session_id)
        ),
    )
    body = device_runtime.ConnectorHeartbeatBody.model_validate(
        healthy().model_dump(mode="json")
    )

    response = device_runtime.connector_heartbeat(
        body, {"gid": "device-001", "owner_user_gid": "user-001"}
    )

    assert response == {"success": True}
    assert calls == [("device-001", "user-001", "session-1")]


def test_connector_v1_transport_routes_are_separate_from_legacy_runtime_routes():
    from backend.routers.device_runtime import router

    paths = {route.path for route in router.routes}
    assert {
        "/api/v1/connector/activate",
        "/api/v1/connector/heartbeat",
        "/api/v1/connector/plans/lease",
        "/api/v1/connector/plans/{plan_id}/complete",
        "/api/v1/connector/plans/{plan_id}/artifacts/{artifact_id}",
        "/api/v1/connector/plans/{plan_id}/steps/{step_id}/result-artifact",
    } <= paths
    assert "/api/v1/device-runtime/commands/lease" in paths

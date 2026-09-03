from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.capability_v2.contracts import OperationStatus
from backend.capability_v2.provider_contracts import CapabilityContext
from backend.contracts.connector_execution_plan_v1 import (
    ConnectorExecutionPlanV1,
    ConnectorPlanOutcomeV1,
    ConnectorStepResultV1,
    canonical_hash,
)
from plugins.simulation.simulation_backend.capabilities.connector_runtime import (
    ConnectorControlPlane,
    ConnectorError,
    ConnectorHealth,
    require_compatible,
    register_connector_runtime_capabilities,
    sign_connector_plan_lease,
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


def completed_outcome():
    current = plan()
    value = {"product_version": "14.2.0"}
    step = ConnectorStepResultV1(
        step_id=current.steps[0].step_id,
        status="completed",
        result=value,
        result_hash=canonical_hash(value),
        started_at=NOW,
        completed_at=NOW,
    )
    return ConnectorPlanOutcomeV1(
        protocol=current.protocol,
        plan_id=current.plan_id,
        status="completed",
        steps=(step,),
        reported_at=NOW,
    )


def test_completion_persists_durable_intent_without_inline_projection():
    class Repository(MemoryRepository):
        def __init__(self):
            super().__init__()
            self.saved_outcome = None
            self.intents = []

        def get_plan(self, plan_id, *, connector_id, lease_id):
            return plan()

        def complete_with_projection_intent(
            self, connector_id, plan_id, lease_id, outcome, target,
        ):
            self.saved_outcome = outcome
            self.intents.append((plan_id, target, canonical_hash(outcome.model_dump(mode="json"))))

    class Projection:
        def __init__(self):
            self.calls = 0

        def target(self, _plan):
            return "simulation.connector_materialization_outcome.apply"

        async def apply(self, *_args, **_kwargs):
            raise AssertionError("durable worker must own projection")

    repository, projection = Repository(), Projection()
    control_plane = ConnectorControlPlane(repository, outcome_port=projection, clock=lambda: NOW)

    asyncio.run(control_plane.complete_plan("device-001", "plan-001", "lease-1", completed_outcome()))

    assert repository.saved_outcome == completed_outcome()
    assert repository.intents == [(
        "plan-001", "simulation.connector_materialization_outcome.apply",
        canonical_hash(completed_outcome().model_dump(mode="json")),
    )]


def test_failed_plan_outcome_requires_a_failed_step():
    class Repository(MemoryRepository):
        def get_plan(self, plan_id, *, connector_id, lease_id):
            return plan()

        def complete_with_projection_intent(
            self, connector_id, plan_id, lease_id, outcome, target,
        ):
            raise AssertionError("invalid outcome must not be persisted")

    completed = completed_outcome()
    inconsistent = completed.model_copy(update={"status": "failed"})
    control_plane = ConnectorControlPlane(Repository(), clock=lambda: NOW)

    with pytest.raises(ConnectorError, match="plan_outcome_invalid"):
        asyncio.run(control_plane.complete_plan("device-001", "plan-001", "lease-1", inconsistent))


def test_reconciliation_can_report_unknown_outcome_without_fabricating_step_results():
    class Repository(MemoryRepository):
        def __init__(self):
            super().__init__()
            self.saved = None

        def get_plan(self, plan_id, *, connector_id, lease_id):
            return plan()

        def complete_with_projection_intent(
            self, connector_id, plan_id, lease_id, outcome, target,
        ):
            self.saved = outcome

    outcome = ConnectorPlanOutcomeV1(
        protocol=plan().protocol,
        plan_id=plan().plan_id,
        status="outcome_unknown",
        steps=(),
        reported_at=NOW,
    )
    repository = Repository()

    asyncio.run(ConnectorControlPlane(repository, clock=lambda: NOW).complete_plan(
        "device-001", "plan-001", "lease-1", outcome,
    ))

    assert repository.saved == outcome


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


def test_lease_requires_a_fresh_ready_bound_session_and_returns_signed_plan(monkeypatch):
    monkeypatch.setenv("AI00_CONNECTOR_PLAN_SIGNING_KEY_ID", "connector-plan-key-1")
    monkeypatch.setenv(
        "AI00_CONNECTOR_PLAN_SIGNING_SECRET",
        "0123456789abcdef0123456789abcdef",
    )
    repository = MemoryRepository()
    control_plane = ConnectorControlPlane(repository, clock=lambda: NOW)

    with pytest.raises(ConnectorError, match="connector_offline"):
        control_plane.lease_plan("device-001", 60)

    repository.save_health("device-001", healthy().model_copy(update={"session_host_ready": False}))
    with pytest.raises(ConnectorError, match="interactive_session_missing"):
        control_plane.lease_plan("device-001", 60)

    repository.save_health("device-001", healthy())
    lease = control_plane.lease_plan("device-001", 60)
    assert lease["lease_id"] == "lease-1"
    assert lease["key_id"].startswith("connector-plan-key-1.device.")
    assert lease["signature"].startswith("hmac-sha256:")
    assert lease["signature"] == sign_connector_plan_lease(plan(), lease["key_id"])["signature"]


def test_connector_capabilities_are_registered_with_closed_contracts():
    from backend.capability_v2.business_definition import substantive_business_definition_errors

    class Registry:
        def __init__(self):
            self.items = []

        def register(self, spec, handler, *, descriptor):
            self.items.append((spec, descriptor))

    registry = Registry()
    register_connector_runtime_capabilities(registry, ConnectorControlPlane(MemoryRepository()))

    by_id = {(spec.id, spec.version): (spec, descriptor) for spec, descriptor in registry.items}
    assert set(by_id) == {
        ("simulation.connector.health.get", 1),
        ("simulation.connector.plan.queue", 1),
        ("simulation.vismockup.status.get", 1),
        ("simulation.vismockup.application.launch", 1),
        ("simulation.vismockup.model.open", 1),
        ("simulation.vismockup.tree.get", 1),
        ("simulation.vismockup.selection.highlight", 1),
        ("simulation.vismockup.visibility.change.apply", 1),
        ("simulation.vismockup.capture.create", 1),
    }
    for spec, descriptor in by_id.values():
        assert spec.input_schema["additionalProperties"] is False
        assert spec.output_schema["additionalProperties"] is False
        assert descriptor.evidence_policy == "required"
        assert substantive_business_definition_errors(descriptor) == ()
    assert by_id[("simulation.connector.plan.queue", 1)][1].consistency_policy == "external"
    assert by_id[("simulation.connector.plan.queue", 1)][1].lifecycle_status == "experimental"
    for capability_id, (_spec, descriptor) in by_id.items():
        if capability_id[0].startswith("simulation.vismockup."):
            assert descriptor.exposure.local_runtime
            assert not descriptor.exposure.web


def test_connector_heartbeat_route_passes_authenticated_connector_identity(monkeypatch):
    from backend.routers import simulation_connector

    calls = []
    monkeypatch.setattr(
        simulation_connector,
        "record_connector_heartbeat",
        lambda device_id, owner_user_id, health: calls.append(
            (device_id, owner_user_id, health.session_id)
        ),
    )
    body = simulation_connector.ConnectorHeartbeatBody.model_validate(
        healthy().model_dump(mode="json")
    )

    response = simulation_connector.connector_heartbeat(
        body, {"gid": "connector-001", "owner_user_gid": "user-001"}
    )

    assert response == {"success": True}
    assert calls == [("connector-001", "user-001", "session-1")]


def test_connector_transport_is_owned_only_by_simulation_router():
    from backend.routers.device_runtime import router as device_router
    from backend.routers.simulation_connector import router as simulation_router

    simulation_paths = {route.path for route in simulation_router.routes}
    assert {
        "/api/v1/simulation/connectors/heartbeat",
        "/api/v1/simulation/connectors/plans/lease",
        "/api/v1/simulation/connectors/plans/{plan_id}/complete",
        "/api/v1/simulation/connectors/plans/{plan_id}/artifacts/{artifact_id}",
        "/api/v1/simulation/connectors/plans/{plan_id}/steps/{step_id}/result-artifact",
    } <= simulation_paths
    device_paths = {route.path for route in device_router.routes}
    assert not any(path.startswith("/api/v1/simulation/connectors/") for path in device_paths)
    assert not any(path.startswith("/api/v1/connector/plans/") for path in device_paths)
    assert "/api/v1/connector/activate" in device_paths
    assert "/api/v1/device-runtime/commands/lease" in device_paths


def test_legacy_connector_activation_is_closed_in_favour_of_browser_pairing(monkeypatch):
    from backend.routers import device_runtime

    body = device_runtime.ActivateBody(enrollment_token="x" * 32, runtime_version="1.0.0")
    with pytest.raises(Exception) as missing:
        device_runtime.connector_activate(body)
    assert getattr(missing.value, "status_code", None) == 410
    assert missing.value.detail == {
        "code": "connector_browser_pairing_required",
        "replacement": "/api/v1/simulation/connectors/pairings",
    }

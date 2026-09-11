from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.capability_v2.contracts import OperationRef, OperationStatus
from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext
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
    _direct_vismockup_plan,
    _direct_vismockup_plan_v2,
    require_compatible,
    register_connector_runtime_capabilities,
    sign_connector_plan_lease,
)
from plugins.simulation.simulation_backend.application.connector_wakeup import (
    ConnectorWakeBroker,
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


def test_direct_plan_uses_cross_language_timestamp_precision():
    value = _direct_vismockup_plan(
        action="launch", connector_id="device-001", payload={},
        context=CapabilityContext(
            user_gid="user-001", team_gid="tenant-001",
            capability_version_gid="cv2_1234567890abcdef12345678",
            business_definition_hash="sha256:" + "2" * 64,
        ),
        now=NOW.replace(microsecond=123456),
    )

    assert value.issued_at.microsecond == 0
    assert value.expires_at.microsecond == 0


def test_wake_broker_notifies_only_the_target_connector():
    async def exercise():
        broker = ConnectorWakeBroker()
        async with broker.subscribe("device-001") as subscription:
            broker.notify("device-002")
            assert await subscription.wait(0.01) is False
            broker.notify("device-001")
            assert await subscription.wait(0.1) is True

    asyncio.run(exercise())


def test_queue_plan_wakes_the_target_connector_after_persistence():
    class WakeRecorder:
        def __init__(self): self.connector_ids = []
        def notify(self, connector_id): self.connector_ids.append(connector_id)

    repository = MemoryRepository()
    wake = WakeRecorder()
    context = CapabilityContext(
        user_gid="user-001", team_gid="tenant-001",
        capability_version_gid="cv2_1234567890abcdef12345678",
        business_definition_hash="sha256:" + "2" * 64,
    )
    value = _direct_vismockup_plan(
        action="attach", connector_id="device-001", payload={}, context=context, now=NOW,
    )
    health_data = healthy().model_dump(mode="json")
    health_data["adapters"][0]["operations"] = [{
        "operation_id": value.steps[0].operation_id,
        "contract_hash": value.steps[0].contract_hash,
    }]
    health = ConnectorHealth.model_validate(health_data)
    repository.save_health("device-001", health)

    operation = ConnectorControlPlane(
        repository, clock=lambda: NOW, wake_notifier=wake,
    ).queue_plan(value, context)

    assert operation.operation_id == value.plan_id
    assert wake.connector_ids == ["device-001"]


def test_attach_plan_never_launches_vismockup():
    value = _direct_vismockup_plan(
        action="attach", connector_id="device-001", payload={},
        context=CapabilityContext(
            user_gid="user-001", team_gid="tenant-001",
            capability_version_gid="cv2_1234567890abcdef12345678",
            business_definition_hash="sha256:" + "2" * 64,
        ),
        now=NOW,
    )

    assert value.steps[0].operation_id == "vismockup.application.probe@1"
    assert value.steps[0].payload == {"allow_launch": False}
    assert value.compute_hash() == value.plan_hash


def test_direct_app_plan_uses_v2_and_keeps_attach_read_only():
    value = _direct_vismockup_plan_v2(
        action="attach", connector_id="device-001", payload={},
        context=CapabilityContext(
            user_gid="user-001", team_gid="tenant-001", request_id="request-001",
            catalog_release="rel_1234567890abcdef1234567890abcdef",
            normalized_input_hash=canonical_hash({}),
            capability_version_gid="cv2_1234567890abcdef12345678",
            business_definition_hash="sha256:" + "2" * 64,
        ),
        now=NOW,
    )

    assert value["protocol"] == "ai00.connector.execution-plan.v2"
    assert value["capability_id"] == "simulation.vismockup.application.attach.request"
    assert value["catalog_release"] == "rel_1234567890abcdef1234567890abcdef"
    assert value["idempotency_key"] == "request-001"
    assert value["normalized_input_hash"] == canonical_hash({})
    assert value["steps"] == [{
        "step_id": "step-00001",
        "operation_id": "vismockup.application.probe@1",
        "contract_hash": "sha256:197cfad8bc3453030fdc288ea78c3abc21699274dd48d4482444af4f62380a37",
        "depends_on": [],
        "payload": {"allow_launch": False},
        "payload_hash": canonical_hash({"allow_launch": False}),
        "timeout_seconds": 120,
        "side_effect_classification": "read",
        "post_condition_probe_id": None,
    }]


def test_complete_tree_read_gets_a_long_timeout_without_slowing_other_commands():
    context = CapabilityContext(
        user_gid="user-001", team_gid="tenant-001", request_id="request-001",
        catalog_release="rel_1234567890abcdef1234567890abcdef",
        normalized_input_hash=canonical_hash({"max_depth": 8}),
        capability_version_gid="cv2_1234567890abcdef12345678",
        business_definition_hash="sha256:" + "2" * 64,
    )

    tree = _direct_vismockup_plan_v2(
        action="tree", connector_id="device-001",
        payload={"max_depth": 8, "force_refresh": True},
        context=context, now=NOW,
    )
    attach = _direct_vismockup_plan_v2(
        action="attach", connector_id="device-001", payload={},
        context=context, now=NOW,
    )

    assert tree["steps"][0]["timeout_seconds"] == 600
    assert tree["steps"][0]["payload"] == {"max_depth": 8, "force_refresh": True}
    assert attach["steps"][0]["timeout_seconds"] == 120


def test_direct_node_actions_use_separate_v2_adapter_contracts():
    context = CapabilityContext(
        user_gid="user-001", team_gid="tenant-001", request_id="request-001",
        catalog_release="rel_1234567890abcdef1234567890abcdef",
        normalized_input_hash=canonical_hash({"node_key": "42", "action": "hide"}),
        capability_version_gid="cv2_1234567890abcdef12345678",
        business_definition_hash="sha256:" + "2" * 64,
    )

    visibility = _direct_vismockup_plan_v2(
        action="node_visibility", connector_id="device-001",
        payload={"node_key": "42", "action": "hide"}, context=context, now=NOW,
    )
    selection = _direct_vismockup_plan_v2(
        action="node_selection", connector_id="device-001",
        payload={"node_key": "42", "action": "highlight"}, context=context, now=NOW,
    )

    assert visibility["capability_id"] == "simulation.vismockup.node.visibility.change.request"
    assert visibility["steps"][0]["operation_id"] == "vismockup.node.visibility.change@1"
    assert visibility["steps"][0]["side_effect_classification"] == "write"
    assert selection["capability_id"] == "simulation.vismockup.node.selection.change.request"
    assert selection["steps"][0]["operation_id"] == "vismockup.node.selection.change@1"


def test_only_explicit_set_style_vismockup_commands_are_safe_to_repeat():
    context = CapabilityContext(
        user_gid="user-001", team_gid="tenant-001", request_id="request-001",
        catalog_release="rel_1234567890abcdef1234567890abcdef",
        normalized_input_hash=canonical_hash({"action": "all_off"}),
        capability_version_gid="cv2_1234567890abcdef12345678",
        business_definition_hash="sha256:" + "2" * 64,
    )
    all_off = _direct_vismockup_plan_v2(
        action="visibility", connector_id="device-001", payload={"action": "all_off"},
        context=context, now=NOW,
    )
    toggle = _direct_vismockup_plan_v2(
        action="node_visibility", connector_id="device-001",
        payload={"node_key": "42", "action": "toggle_visible"}, context=context, now=NOW,
    )
    launch = _direct_vismockup_plan_v2(
        action="launch", connector_id="device-001", payload={}, context=context, now=NOW,
    )

    from plugins.simulation.simulation_backend.data.connector_repository import SimulationConnectorRepository
    assert SimulationConnectorRepository._repeat_is_intrinsically_safe(all_off)
    assert SimulationConnectorRepository._repeat_is_intrinsically_safe(launch)
    assert not SimulationConnectorRepository._repeat_is_intrinsically_safe(toggle)


def test_direct_app_request_queues_v2_instead_of_fenced_legacy_plan():
    class Repository:
        def bound_runtime_for_user(self, user_id, tenant_id):
            return {"device_id": "device-001", "runtime_type": "electron"}

    class Control:
        def __init__(self):
            self.repository = Repository()
            self.queued = None

        def clock(self):
            return NOW

        def queue_v2(self, value, context, *, runtime_row=None):
            self.queued = value
            self.runtime_row = runtime_row
            return OperationRef(operation_id=value["plan_id"], status=OperationStatus.ACCEPTED)

    class Registry:
        def __init__(self): self.handlers = {}
        def register(self, spec, handler, *, descriptor): self.handlers[(spec.id, spec.version)] = handler

    registry, control = Registry(), Control()
    register_connector_runtime_capabilities(registry, control)
    result = registry.handlers[("simulation.vismockup.application.attach.request", 1)](
        {}, CapabilityContext(
            user_gid="user-001", team_gid="tenant-001", request_id="request-001",
            catalog_release="rel_1234567890abcdef1234567890abcdef",
            normalized_input_hash=canonical_hash({}),
        ),
    )

    assert control.queued["protocol"] == "ai00.connector.execution-plan.v2"
    assert control.runtime_row == {"device_id": "device-001", "runtime_type": "electron"}
    assert result.data["operation_id"] == control.queued["plan_id"]


def test_direct_app_request_preserves_actionable_connector_error_code():
    class Repository:
        def bound_runtime_for_user(self, user_id, tenant_id):
            return {"device_id": "device-001", "runtime_type": "electron"}

    class Control:
        repository = Repository()
        clock = staticmethod(lambda: NOW)

        def queue_v2(self, value, context, *, runtime_row=None):
            raise ConnectorError("reconciliation_required")

    class Registry:
        def __init__(self): self.handlers = {}
        def register(self, spec, handler, *, descriptor): self.handlers[(spec.id, spec.version)] = handler

    registry = Registry()
    register_connector_runtime_capabilities(registry, Control())
    with pytest.raises(CapabilityBusinessError, match="reconciliation_required") as error:
        registry.handlers[("simulation.vismockup.application.launch.request", 1)](
            {}, CapabilityContext(
                user_gid="user-001", team_gid="tenant-001", request_id="request-001",
                catalog_release="rel_1234567890abcdef1234567890abcdef",
                normalized_input_hash=canonical_hash({}),
                capability_version_gid="cv2_1234567890abcdef12345678",
                business_definition_hash="sha256:" + "2" * 64,
            ),
        )
    assert error.value.code == "reconciliation_required"


def test_frozen_runtime_plan_opens_one_root_then_reads_back_the_tree():
    plan = _direct_vismockup_plan_v2(
        action="open", connector_id="device-001",
        payload={"artifact_ref": {"artifact_id": "root"}, "package_dependencies": []},
        context=CapabilityContext(
            user_gid="user-001", team_gid="tenant-001", request_id="request-001",
            catalog_release="rel_1234567890abcdef1234567890abcdef",
            normalized_input_hash=canonical_hash({"workspace_gid": "10"}),
            capability_version_gid="cv2_simulation_runtime_package_open_v1",
            business_definition_hash="sha256:" + "1" * 64,
            idempotency_key="runtime-open-10",
        ), now=NOW, capability_id="simulation.environment.runtime_package.open.request",
        readback=True,
    )

    assert [step["operation_id"] for step in plan["steps"]] == [
        "vismockup.model.open@1", "vismockup.tree.read@1",
    ]
    assert plan["steps"][1]["depends_on"] == ["step-00001"]
    assert plan["steps"][1]["payload"] == {"max_depth": 8, "force_refresh": True}


def test_frozen_runtime_plan_has_dedicated_outcome_projection():
    from types import SimpleNamespace
    from backend.domain_ports.simulation_runtime import GovernedSimulationRuntimeClient
    plan = SimpleNamespace(
        plan_id="runtime-plan-1",
        capability_id="simulation.environment.runtime_package.open.request",
        steps=[SimpleNamespace(operation_id="vismockup.model.open@1"), SimpleNamespace(operation_id="vismockup.tree.read@1")],
    )
    assert GovernedSimulationRuntimeClient.connector_outcome_target(plan) == (
        "simulation.connector_environment_runtime_outcome.apply",
        {"connector_plan_id": "runtime-plan-1"},
    )


def test_v2_plan_identity_is_stable_for_the_same_idempotent_request():
    context = CapabilityContext(
        user_gid="user-001", team_gid="tenant-001", request_id="request-001",
        catalog_release="rel_1234567890abcdef1234567890abcdef",
        normalized_input_hash=canonical_hash({"workspace_gid": "10"}),
        capability_version_gid="cv2_simulation_runtime_package_open_v1",
        business_definition_hash="sha256:" + "1" * 64,
        idempotency_key="runtime-open-10",
    )
    first = _direct_vismockup_plan_v2(action="open", connector_id="device-001", payload={"artifact_ref": {"artifact_id": "root"}}, context=context, now=NOW)
    second = _direct_vismockup_plan_v2(action="open", connector_id="device-001", payload={"artifact_ref": {"artifact_id": "root"}}, context=context, now=NOW)
    assert first["plan_id"] == second["plan_id"]


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


def test_missing_session_heartbeat_can_transition_to_ready_immediately():
    repository = MemoryRepository()
    repository.save_health("device-001", healthy("missing").model_copy(update={
        "user_session_present": False,
        "session_host_ready": False,
        "adapters": (),
    }))
    control_plane = ConnectorControlPlane(repository, clock=lambda: NOW)

    control_plane.record_heartbeat("device-001", "user-001", healthy("session-1"))

    assert repository.health["device-001"].session_host_ready is True


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
        ("simulation.connector.runtime.takeover", 1),
        ("simulation.connector.health.get", 1),
        ("simulation.connector.plan.queue", 1),
        ("simulation.connector.plan.queue", 2),
        ("simulation.vismockup.application.attach.request", 1),
        ("simulation.vismockup.application.launch.request", 1),
        ("simulation.vismockup.model.open.request", 1),
        ("simulation.environment.runtime_package.open.request", 1),
        ("simulation.vismockup.model.insert.request", 1),
        ("simulation.vismockup.model.close.request", 1),
        ("simulation.vismockup.visibility.change.request", 1),
        ("simulation.vismockup.node.visibility.change.request", 1),
        ("simulation.vismockup.node.selection.change.request", 1),
        ("simulation.vismockup.tree.read.request", 1),
        ("simulation.vismockup.command.get", 1),
        ("simulation.vismockup.status.get", 1),
        ("simulation.vismockup.application.launch", 1),
        ("simulation.vismockup.model.open", 1),
        ("simulation.vismockup.model.insert", 1),
        ("simulation.vismockup.tree.get", 1),
        ("simulation.vismockup.selection.highlight", 1),
        ("simulation.vismockup.visibility.change.apply", 1),
        ("simulation.vismockup.node.visibility.change.apply", 1),
        ("simulation.vismockup.node.selection.change.apply", 1),
        ("simulation.vismockup.capture.create", 1),
    }
    for spec, descriptor in by_id.values():
        assert spec.input_schema["additionalProperties"] is False
        assert spec.output_schema["additionalProperties"] is False
        assert descriptor.evidence_policy == "required"
        assert substantive_business_definition_errors(descriptor) == ()
    assert by_id[("simulation.connector.plan.queue", 1)][1].consistency_policy == "external"
    assert by_id[("simulation.connector.plan.queue", 1)][1].lifecycle_status == "experimental"
    assert by_id[("simulation.connector.plan.queue", 1)][0].permissions == ("agent.run",)
    assert by_id[("simulation.connector.plan.queue", 2)][0].permissions == ("simulation.use",)
    snapshot_payload_schema = (
        by_id[("simulation.connector.plan.queue", 2)][0]
        .input_schema["properties"]["plan"]["properties"]["steps"]["items"]
        ["properties"]["payload"]
    )
    assert set(snapshot_payload_schema["properties"]) == {"max_nodes", "max_depth"}
    for capability_id in (
        "simulation.vismockup.application.attach.request",
        "simulation.vismockup.application.launch.request",
        "simulation.vismockup.model.open.request",
        "simulation.environment.runtime_package.open.request",
        "simulation.vismockup.model.insert.request",
        "simulation.vismockup.model.close.request",
        "simulation.vismockup.visibility.change.request",
        "simulation.vismockup.node.visibility.change.request",
        "simulation.vismockup.node.selection.change.request",
        "simulation.vismockup.tree.read.request",
        "simulation.vismockup.command.get",
    ):
        spec, descriptor = by_id[(capability_id, 1)]
        assert spec.permissions == ("simulation.use",)
        assert descriptor.execution_mode.value == "cloud_sync"
        assert descriptor.operation_policy == ("optional" if spec.risk.value == "write" else "none")
    assert by_id[("simulation.vismockup.application.attach.request", 1)][0].confirmation == "none"
    assert by_id[("simulation.vismockup.visibility.change.request", 1)][0].confirmation == "none"
    assert by_id[("simulation.vismockup.node.visibility.change.request", 1)][0].confirmation == "none"
    assert by_id[("simulation.vismockup.node.selection.change.request", 1)][0].confirmation == "none"
    assert by_id[("simulation.vismockup.tree.read.request", 1)][0].confirmation == "none"
    assert set(by_id[("simulation.vismockup.tree.read.request", 1)][0].input_schema["properties"]) == {
        "max_depth", "force_refresh",
    }
    for capability_id, (_spec, descriptor) in by_id.items():
        if capability_id[0].startswith("simulation.vismockup.") and not capability_id[0].endswith(".request") and capability_id[0] != "simulation.vismockup.command.get":
            assert descriptor.exposure.local_runtime
            assert not descriptor.exposure.web
        elif capability_id[0].startswith("simulation.vismockup."):
            assert descriptor.exposure.web
            assert not descriptor.exposure.local_runtime


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

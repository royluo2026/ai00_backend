from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import pytest

from backend.capability_v2.provider_contracts import CapabilityContext
from backend.contracts.connector_execution_plan_v1 import (
    ConnectorPlanOutcomeV1,
    ConnectorStepResultV1,
    canonical_hash,
)
from backend.capabilities.registry_next import CapabilityRegistry
from backend.capabilities.confirmation_next import confirmation_manager
from backend.capability_v2.business_definition import business_definition_hash
from plugins.simulation.simulation_backend.capabilities import register_capabilities
from plugins.simulation.simulation_backend.capabilities.capture_runs import CaptureRunProvider
from plugins.simulation.simulation_backend.application.capture_worker import (
    CaptureWorkflow,
    SimulationWorkflowError,
)
from plugins.simulation.simulation_backend.domain.environment_manifest import compose_manifest


ARTIFACT = {
    "artifact_id": "artifact-30", "media_type": "image/png",
    "sha256": "f" * 64, "byte_size": 4096, "version": 1,
}


def _manifest():
    operations = []
    nodes = [{"node_key": "root", "parent_key": None, "product_ref": "ROOT", "child_order": 0}]
    resolved = []
    for sequence in (10, 20, 30):
        operations.append({
            "operation_id": f"op-{sequence}", "sequence": sequence,
            "predecessor_ids": [] if sequence == 10 else [f"op-{sequence - 10}"],
            "products": [{"product_ref": f"P-{sequence}", "action": "install"}],
            "resources": [{"resource_type": "tool", "code": f"T-{sequence}"}],
        })
        nodes.append({
            "node_key": f"bom-node-{sequence}", "parent_key": "root",
            "product_ref": f"P-{sequence}", "child_order": sequence // 10,
        })
        resolved.append({
            "resource_type": "tool", "code": f"T-{sequence}",
            "normalized_code": f"t-{sequence}",
            "model_ref": {
                "model_id": f"model-{sequence}", "version_id": "v1",
                "snapshot_hash": "sha256:" + str(sequence // 10) * 64,
                "artifact_ref": {
                    "artifact_id": f"model-artifact-{sequence}", "media_type": "model/step",
                    "sha256": str(sequence // 10) * 64, "byte_size": 100, "version": 1,
                },
            },
        })
    result = compose_manifest(
        execution_plan={
            "source": {"bop_version_gid": "bop-v1", "revision": 1, "project_gid": "project-1"},
            "content_hash": "sha256:" + "a" * 64, "operations": operations,
        },
        document_snapshot={
            "document_id": "BOM-1", "root_node_key": "root",
            "source_identity": "tc://BOM-1/A", "snapshot_hash": "sha256:" + "b" * 64,
            "nodes": nodes,
        },
        model_mappings={
            "resolved": resolved, "unresolved": [], "ambiguous": [],
            "mapping_snapshot_hash": "sha256:" + "c" * 64,
        },
        capture_profile={"format": "png", "width": 1920, "height": 1080, "background": "current"},
    )
    return result.manifest


class Repository:
    def __init__(self):
        self.manifest = _manifest()
        self.runs = {}

    def get_manifest(self, environment_id, environment_version, context): return self.manifest
    def create_capture_run(self, row): self.runs[row["capture_run_id"]] = row
    def get_capture_run(self, run_id, context): return self.runs.get(run_id)
    def update_capture_run(self, run_id, **changes): self.runs[run_id].update(changes)
    def update_materialization_run(self, run_id, **changes): self.runs[run_id].update(changes)
    def get_materialization_run(self, run_id, context): return self.runs.get(run_id)
    def update_capture_step(self, run_id, operation_id, **changes):
        step = next(item for item in self.runs[run_id]["steps"] if item["operation_id"] == operation_id)
        step.update(changes)
    def create_materialization_run(self, row): self.runs[row["run_id"]] = row


class Connector:
    def __init__(self): self.plans = []
    async def queue_plan(self, plan, context, approval_reference=None):
        self.plans.append((plan, approval_reference))
        return {"operation_id": plan.plan_id, "status": "accepted"}
    @property
    def last_plan(self): return self.plans[-1][0]


class OfflineConnector(Connector):
    async def queue_plan(self, plan, context, approval_reference=None):
        raise SimulationWorkflowError("connector_offline")


class Craft:
    def __init__(self): self.calls = []
    async def attach_screenshot(self, *, bop_version_gid, operation_id, artifact_ref, capture_run_id, context, approval_reference=None):
        self.calls.append((bop_version_gid, operation_id, artifact_ref["artifact_id"], capture_run_id, approval_reference))


def _workflow():
    repository, connector, craft = Repository(), Connector(), Craft()
    ids = iter(("run-1", "materialize-1", "retry-1"))
    workflow = CaptureWorkflow(
        repository=repository, connector_port=connector, craft_port=craft,
        id_factory=lambda prefix: next(ids), clock=lambda: datetime(2026, 9, 3, tzinfo=UTC),
    )
    return workflow, repository, connector, craft


def _context():
    return CapabilityContext(
        user_gid="user-1", team_gid="team-1", source="agent",
        capability_version_gid="cv2_test", business_definition_hash="sha256:" + "d" * 64,
    )


def test_capture_prepares_then_dispatches_only_the_first_reverse_order_operation():
    workflow, _, connector, _ = _workflow()

    asyncio.run(workflow.start_capture("env-1", 1, "device-1", _context()))
    assert connector.plans == []
    action = workflow.next_action("run-1", _context())
    assert action["capability_id"] == "device.connector.plan.queue"
    assert action["major_version"] == 2
    asyncio.run(workflow.dispatch_next("run-1", "approval-device-1", _context()))

    captures = [step.payload["operation_id"] for plan, _approval in connector.plans for step in plan.steps
                if step.operation_id == "vismockup.view.capture@1"]
    assert captures == ["op-30"]
    assert connector.plans[0][1] == "approval-device-1"
    assert all(len(plan.steps) == 3 for plan, _approval in connector.plans)
    assert all(
        step.payload["artifact_resource_refs"] == ["craft-bop-version:bop-v1"]
        for plan, _approval in connector.plans for step in plan.steps
        if step.operation_id == "vismockup.view.capture@1"
    )


def test_materialization_plan_attaches_models_before_scene_verification():
    workflow, _, connector, _ = _workflow()

    asyncio.run(workflow.start_materialization("env-1", 1, "device-1", _context()))
    assert connector.plans == []
    action = workflow.next_materialization_action("run-1", _context())
    assert action["capability_id"] == "device.connector.plan.queue"
    assert action["major_version"] == 2
    asyncio.run(workflow.dispatch_materialization("run-1", "approval-materialize", _context()))

    operation_ids = [step.operation_id for step in connector.last_plan.steps]
    assert operation_ids[0] == "vismockup.application.probe@1"
    assert operation_ids[1:4] == ["vismockup.model.attach@1"] * 3
    assert operation_ids[-2:] == ["vismockup.scene.apply@1", "vismockup.scene.verify@1"]
    assert connector.last_plan.steps[-1].depends_on == (connector.last_plan.steps[-2].step_id,)


def test_materialization_outcome_projects_terminal_status_to_domain_run():
    workflow, repository, connector, _ = _workflow()
    asyncio.run(workflow.start_materialization("env-1", 1, "device-1", _context()))
    asyncio.run(workflow.dispatch_materialization("run-1", "approval-materialize", _context()))
    plan = connector.last_plan
    now = datetime(2026, 9, 3, tzinfo=UTC)
    results = tuple(
        ConnectorStepResultV1(
            step_id=step.step_id, status="completed", result={},
            result_hash=canonical_hash({}), started_at=now, completed_at=now,
        )
        for step in plan.steps
    )
    outcome = ConnectorPlanOutcomeV1(
        protocol=plan.protocol, plan_id=plan.plan_id, status="completed",
        steps=results, reported_at=now,
    )

    workflow.apply_materialization_outcome(plan, outcome)

    assert repository.runs["run-1"]["status"] == "completed"


def test_completed_artifact_is_attached_once_before_later_completed_step():
    workflow, _, connector, craft = _workflow()
    asyncio.run(workflow.start_capture("env-1", 1, "device-1", _context()))
    asyncio.run(workflow.dispatch_next("run-1", "approval-device-1", _context()))
    workflow.record_step_result("run-1", "op-30", status="completed", artifact_ref=ARTIFACT)

    action = workflow.next_action("run-1", _context())
    assert action["capability_id"] == "craft.process_screenshot.attach"
    asyncio.run(workflow.dispatch_next("run-1", "approval-craft-1", _context()))
    assert workflow.next_action("run-1", _context())["payload"]["plan"]["plan_id"].endswith("00002")
    assert len(connector.plans) == 1

    assert craft.calls == [("bop-v1", "op-30", "artifact-30", "run-1", "approval-craft-1")]


def test_outcome_unknown_requires_reconciliation_before_retry():
    workflow, _, _, _ = _workflow()
    asyncio.run(workflow.start_capture("env-1", 1, "device-1", _context()))
    workflow.record_step_result("run-1", "op-30", status="outcome_unknown")

    with pytest.raises(SimulationWorkflowError, match="local_execution_outcome_unknown"):
        asyncio.run(workflow.retry_step("run-1", "op-30", _context()))


def test_cancel_stops_only_unstarted_steps():
    workflow, repository, _, _ = _workflow()
    asyncio.run(workflow.start_capture("env-1", 1, "device-1", _context()))
    workflow.record_step_result("run-1", "op-30", status="running")

    workflow.cancel("run-1", _context())

    assert [item["status"] for item in repository.runs["run-1"]["steps"]] == [
        "running", "cancelled", "cancelled",
    ]


def test_capture_enqueue_returns_domain_run_identity_without_gateway_shadow_operation():
    workflow, _, _, _ = _workflow()
    registry = CapabilityRegistry()
    register_capabilities(registry, capture_provider=CaptureRunProvider(workflow))

    expected = {
        "simulation.environment.materialize",
        "simulation.materialization_run.action.get",
        "simulation.materialization_run.dispatch",
        "simulation.capture_run.start",
        "simulation.capture_run.get",
        "simulation.capture_run.action.get",
        "simulation.capture_run.dispatch",
        "simulation.capture_run.cancel",
        "simulation.capture_step.retry",
    }
    registrations = {item.spec.id: item for item in registry.snapshot() if item.spec.id in expected}
    assert set(registrations) == expected
    for item in registrations.values():
        assert item.spec.input_schema["additionalProperties"] is False
        assert item.spec.output_schema["additionalProperties"] is False
    assert registrations["simulation.capture_run.start"].descriptor.execution_mode == "cloud_sync"
    assert registrations["simulation.capture_run.start"].descriptor.operation_policy == "optional"
    assert registrations["simulation.environment.materialize"].descriptor.operation_policy == "optional"
    assert registrations["simulation.materialization_run.action.get"].spec.confirmation == "none"
    assert registrations["simulation.materialization_run.dispatch"].spec.confirmation == "none"
    assert registrations["simulation.capture_run.action.get"].spec.confirmation == "none"
    assert registrations["simulation.capture_run.dispatch"].spec.confirmation == "none"


def test_capture_dispatch_consumes_the_user_approved_exact_downstream_action():
    workflow, _, connector, _ = _workflow()
    provider = CaptureRunProvider(workflow)
    asyncio.run(workflow.start_capture("env-1", 1, "device-1", _context()))

    action = provider.action({"capture_run_id": "run-1"}, _context()).data["action"]
    assert action["capability_id"] == "device.connector.plan.queue"
    assert action["major_version"] == 2
    assert action["payload_hash"] == canonical_hash(json.loads(action["payload_json"]))

    approved_context = _context().model_copy(update={"confirmation_token": "approved-exact-action"})
    result = asyncio.run(provider.dispatch({"capture_run_id": "run-1"}, approved_context))

    assert result.data["steps"][0]["status"] == "running"
    assert connector.plans[0][1] == "approved-exact-action"


def test_queue_failure_is_persisted_as_failed_before_error_returns():
    repository = Repository()
    workflow = CaptureWorkflow(
        repository=repository, connector_port=OfflineConnector(), craft_port=Craft(),
        id_factory=lambda prefix: "run-offline", clock=lambda: datetime(2026, 9, 3, tzinfo=UTC),
    )

    asyncio.run(workflow.start_capture("env-1", 1, "device-1", _context()))
    with pytest.raises(SimulationWorkflowError, match="connector_offline"):
        asyncio.run(workflow.dispatch_next("run-offline", "approval-device-1", _context()))

    assert repository.runs["run-offline"]["steps"][0]["status"] == "queued"


def test_gateway_bound_capture_plan_uses_exact_descriptor_provenance():
    workflow, repository, _, _ = _workflow()
    registry = CapabilityRegistry()
    register_capabilities(registry, capture_provider=CaptureRunProvider(workflow))
    payload = {"environment_id": "env-1", "environment_version": 1, "device_id": "device-1"}
    token = confirmation_manager.issue("simulation.capture_run.start", 1, "user-1", payload)
    context = CapabilityContext(
        user_gid="user-1", team_gid="team-1", permissions=("simulation.use",),
        confirmation_token=token,
    )

    asyncio.run(registry.invoke("simulation.capture_run.start", payload, context, version=1))

    descriptor = registry.get("simulation.capture_run.start", 1).descriptor
    prepared = repository.runs["run-1"]["steps"][0]["plan"]
    assert prepared["capability_version_gid"] == descriptor.capability_version_gid
    assert prepared["business_definition_hash"] == business_definition_hash(descriptor)


def test_signed_connector_outcome_advances_capture_and_attaches_artifact_once():
    workflow, _, connector, craft = _workflow()
    asyncio.run(workflow.start_capture("env-1", 1, "device-1", _context()))
    now = datetime(2026, 9, 3, tzinfo=UTC)
    for index, operation_id in enumerate(("op-30", "op-20", "op-10"), start=1):
        asyncio.run(workflow.dispatch_next("run-1", f"approval-device-{index}", _context()))
        plan = connector.plans[-1][0]
        results = []
        for step in plan.steps:
            value = {"artifact": ARTIFACT} if step.operation_id == "vismockup.view.capture@1" else {}
            results.append(ConnectorStepResultV1(
                step_id=step.step_id, status="completed", result=value,
                result_hash=canonical_hash(value), started_at=now, completed_at=now,
            ))
        outcome = ConnectorPlanOutcomeV1(
            protocol=plan.protocol, plan_id=plan.plan_id, status="completed",
            steps=tuple(results), reported_at=now,
        )
        asyncio.run(workflow.apply_connector_outcome(plan, outcome, _context()))
        asyncio.run(workflow.apply_connector_outcome(plan, outcome, _context()))
        assert len(craft.calls) == index - 1
        asyncio.run(workflow.dispatch_next("run-1", f"approval-craft-{index}", _context()))

    assert [call[1] for call in craft.calls] == ["op-30", "op-20", "op-10"]

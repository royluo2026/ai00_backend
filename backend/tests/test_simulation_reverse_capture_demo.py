from datetime import UTC, datetime
import asyncio
import pytest

from backend.tests.test_simulation_capture_workflow import (
    ARTIFACT, _context, _manifest, _workflow,
)
from backend.contracts.connector_execution_plan_v1 import (
    ConnectorPlanOutcomeV1, ConnectorStepResultV1, canonical_hash,
)
from plugins.simulation.simulation_backend.application.connector_plans import (
    build_capture_plan, build_materialization_plan,
)
from plugins.simulation.simulation_backend.domain.environment_manifest import (
    REQUIRED_CONNECTOR_OPERATIONS,
)


def _outcome(plan):
    now = datetime(2026, 9, 30, tzinfo=UTC)
    results = []
    for step in plan.steps:
        value = {"artifact": ARTIFACT} if step.operation_id == "vismockup.view.capture@1" else {}
        results.append(ConnectorStepResultV1(step_id=step.step_id, status="completed", result=value,
            result_hash=canonical_hash(value), started_at=now, completed_at=now))
    return ConnectorPlanOutcomeV1(protocol=plan.protocol, plan_id=plan.plan_id,
        status="completed", steps=tuple(results), reported_at=now)


def _arguments():
    return dict(plan_id="demo", device_id="device", tenant_id="team", user_id="user",
                issued_at=datetime(2026, 9, 30, tzinfo=UTC),
                capability_version_gid="cv2_test", business_definition_hash="sha256:" + "a" * 64)


def test_real_execution_hierarchy_keeps_repeated_local_orders_and_process_card_identity():
    from plugins.craft.craft_backend.services.execution_structure import BopAggregate, _normalize
    from plugins.simulation.simulation_backend.domain.environment_manifest import compose_manifest
    from backend.tests.test_simulation_environment_manifest import _fixture

    entries = [{"gid": "line", "node_type": "line_process", "sort_order": 1}]
    links = []
    for station, order in (("a", 1), ("b", 2)):
        entries.append({"gid": f"station-{station}", "parent_gid": "line", "node_type": "station_process", "sort_order": order})
        for number in (1, 2):
            process = f"process-{station}-{number}"
            operation = f"work-{station}-{number}"
            entries.extend([
                {"gid": process, "parent_gid": f"station-{station}", "node_type": "process", "sort_order": number},
                {"gid": operation, "parent_gid": process, "node_type": "operation", "sort_order": 1},
            ])
            links.append({"entry_gid": operation, "link_type": "pbom_part", "entity_gid": operation,
                          "entity_data": {"part_no": f"P-{number * 10}"}})
    fixture = _fixture()
    fixture["execution_plan"] = _normalize(BopAggregate(
        version={"gid": "bop-1", "project_gid": "project-1", "revision": 7},
        entries=tuple(reversed(entries)), links=tuple(links),
    ))
    fixture["execution_plan"]["content_hash"] = canonical_hash(fixture["execution_plan"])
    fixture["model_mappings"]["resolved"] = []
    manifest = compose_manifest(**fixture).manifest
    workflow, repository, _, _ = _workflow()
    repository.manifest = manifest
    run = asyncio.run(workflow.start_capture("env", 1, "device", _context()))
    captures = [step for operation in run["steps"] for step in operation["plan"]["steps"]
                if step["operation_id"] == "vismockup.view.capture@1"]
    assert [step["payload"]["operation_id"] for step in captures] == [
        "process-b-2", "process-b-1", "process-a-2", "process-a-1",
    ]
    for step in captures:
        assert step["payload"]["operation_id"].startswith("process-")


def test_materialization_renders_the_complete_line_gray_and_fits_only_once():
    plan = build_materialization_plan(_manifest(), **_arguments())
    render = plan.steps[-2]
    assert render.operation_id == "vismockup.scene.render@1"
    assert render.payload["highlight_products"] == []
    assert render.payload["fit_all"] is True
    assert set(render.payload["scene"]["visible_products"]) == {
        "bom-node-10", "bom-node-20", "bom-node-30",
    }
    assert render.contract_hash == REQUIRED_CONNECTOR_OPERATIONS[render.operation_id]


def test_blue_capture_precedes_gray_hide_and_final_visibility_verification():
    plan = build_capture_plan(_manifest(), operations=["op-30"], **_arguments())
    assert [step.operation_id for step in plan.steps] == [
        "vismockup.scene.render@1", "vismockup.scene.verify@1", "vismockup.view.capture@1",
        "vismockup.scene.render@1", "vismockup.scene.verify@1",
    ]
    assert plan.steps[0].payload["highlight_products"] == ["bom-node-30"]
    assert plan.steps[0].payload["fit_all"] is False
    assert plan.steps[3].payload["highlight_products"] == []
    assert plan.steps[3].payload["scene"]["visible_products"] == ["bom-node-10", "bom-node-20"]
    assert plan.steps[3].depends_on == (plan.steps[2].step_id,)
    assert plan.steps[4].payload["expected_scene_hash"] == plan.steps[3].payload["scene"]["scene_hash"]


def test_shared_product_is_retained_until_earliest_referencing_process():
    manifest = _manifest()
    last = manifest.operations[-1].model_copy(update={
        "product_node_keys": ("bom-node-10", "bom-node-30"),
    })
    manifest = manifest.model_copy(update={"operations": (*manifest.operations[:-1], last)})
    plan = build_capture_plan(manifest, operations=["op-30"], **_arguments())
    assert set(plan.steps[0].payload["highlight_products"]) == {"bom-node-10", "bom-node-30"}
    assert "bom-node-10" in plan.steps[3].payload["scene"]["visible_products"]
    first = build_capture_plan(manifest, operations=["op-10"], **_arguments())
    assert first.steps[3].payload["scene"]["visible_products"] == []


def test_hide_failure_after_uploaded_capture_never_advances_or_attaches():
    workflow, repository, connector, _ = _workflow()
    asyncio.run(workflow.start_capture("env", 1, "device", _context()))
    asyncio.run(workflow.dispatch_next("run-1", "approved", _context()))
    plan = connector.last_plan
    now = datetime(2026, 9, 30, tzinfo=UTC)
    results = []
    for step in plan.steps:
        status = "failed" if step == plan.steps[-1] else "completed"
        value = {"artifact": ARTIFACT} if step.operation_id == "vismockup.view.capture@1" else {}
        results.append(ConnectorStepResultV1(step_id=step.step_id, status=status, result=value,
            error_code="scene_verification_failed" if status == "failed" else "",
            result_hash=canonical_hash(value), started_at=now, completed_at=now))
    outcome = ConnectorPlanOutcomeV1(protocol=plan.protocol, plan_id=plan.plan_id,
        status="failed", steps=tuple(results), reported_at=now)
    result = asyncio.run(workflow.apply_connector_outcome(plan, outcome, _context()))
    assert result["steps"][0]["status"] == "failed"
    assert workflow.next_action("run-1", _context()) is None
    assert not repository.runs["run-1"]["steps"][0]["artifact_attached"]


def test_empty_process_is_skipped_without_blocking_completion():
    workflow, repository, connector, _ = _workflow()
    operations = repository.manifest.operations
    repository.manifest = repository.manifest.model_copy(update={"operations": (
        operations[0], operations[1].model_copy(update={"product_node_keys": ()}), operations[2],
    )})
    run = asyncio.run(workflow.start_capture("env", 1, "device", _context()))
    assert [step["status"] for step in run["steps"]] == ["queued", "skipped", "queued"]
    for operation in ("op-30", "op-10"):
        asyncio.run(workflow.dispatch_next("run-1", "approved", _context()))
        assert connector.last_plan.steps[2].payload["operation_id"] == operation
        asyncio.run(workflow.apply_connector_outcome(connector.last_plan, _outcome(connector.last_plan), _context()))
        asyncio.run(workflow.dispatch_next("run-1", "approved", _context()))
    assert repository.runs["run-1"]["status"] == "completed"


def test_cancelled_run_drains_current_step_without_restarting_or_attaching():
    workflow, repository, connector, craft = _workflow()
    asyncio.run(workflow.start_capture("env", 1, "device", _context()))
    asyncio.run(workflow.dispatch_next("run-1", "approved", _context()))
    workflow.cancel("run-1", _context())
    asyncio.run(workflow.apply_connector_outcome(connector.last_plan, _outcome(connector.last_plan), _context()))
    assert repository.runs["run-1"]["status"] == "cancelled"
    assert workflow.next_action("run-1", _context()) is None
    assert craft.calls == []


def test_retry_of_failed_step_reopens_dispatch_without_replaying_completed_steps():
    workflow, repository, _, _ = _workflow()
    asyncio.run(workflow.start_capture("env", 1, "device", _context()))
    repository.update_capture_step("run-1", "op-30", status="failed")
    repository.update_capture_run("run-1", status="failed")
    asyncio.run(workflow.retry_step("run-1", "op-30", _context()))
    assert repository.runs["run-1"]["status"] == "queued"
    assert workflow.next_action("run-1", _context())["capability_id"] == "simulation.connector.plan.queue"


def test_old_environment_requires_recomposition_instead_of_silent_legacy_capture():
    workflow, repository, _, _ = _workflow()
    requirement = repository.manifest.connector_requirement
    repository.manifest = repository.manifest.model_copy(update={"connector_requirement":
        requirement.model_copy(update={"operations": tuple(item for item in requirement.operations
            if item.operation_id != "vismockup.scene.render@1")})})
    with pytest.raises(RuntimeError, match="simulation_capture_environment_upgrade_required"):
        asyncio.run(workflow.start_capture("env", 1, "device", _context()))
    assert repository.runs == {}

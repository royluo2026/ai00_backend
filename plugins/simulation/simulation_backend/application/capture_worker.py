"""Server-authoritative state machine for materialization and reverse capture."""
from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any, Callable, Mapping

from backend.capability_v2.contracts import ArtifactRef
from backend.capability_v2.provider_contracts import CapabilityContext
from backend.contracts.connector_execution_plan_v1 import (
    ConnectorExecutionPlanV1,
    ConnectorPlanOutcomeV1,
)

from .connector_plans import build_capture_plan, build_materialization_plan


class SimulationWorkflowError(RuntimeError):
    pass


class CaptureWorkflow:
    def __init__(
        self,
        *, repository, connector_port, craft_port,
        id_factory: Callable[[str], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.connector_port = connector_port
        self.craft_port = craft_port
        self.id_factory = id_factory or (lambda prefix: f"{prefix}-{secrets.token_hex(16)}")
        self.clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def _identity(context: CapabilityContext) -> tuple[str, str]:
        if not context.team_gid:
            raise SimulationWorkflowError("tenant_context_required")
        return context.team_gid, context.user_gid

    @staticmethod
    def _provenance(context: CapabilityContext) -> tuple[str, str]:
        version_gid = str(getattr(context, "capability_version_gid", "") or "")
        definition_hash = str(getattr(context, "business_definition_hash", "") or "")
        if not version_gid.startswith("cv2_") or not definition_hash.startswith("sha256:"):
            raise SimulationWorkflowError("capability_provenance_required")
        return version_gid, definition_hash

    async def start_materialization(
        self, environment_id: str, environment_version: int, device_id: str,
        context: CapabilityContext,
    ) -> dict[str, Any]:
        tenant_id, user_id = self._identity(context)
        version_gid, definition_hash = self._provenance(context)
        manifest = self.repository.get_manifest(environment_id, environment_version, context)
        if manifest is None:
            raise SimulationWorkflowError("simulation_environment_not_found")
        run_id = self.id_factory("materialize")
        plan = build_materialization_plan(
            manifest, plan_id=run_id, device_id=device_id, tenant_id=tenant_id,
            user_id=user_id, issued_at=self.clock(),
            capability_version_gid=version_gid, business_definition_hash=definition_hash,
        )
        row = {
            "run_id": run_id, "environment_id": environment_id,
            "environment_version": environment_version, "manifest_hash": manifest.manifest_hash,
            "device_id": device_id, "plan_id": plan.plan_id, "status": "queued",
            "owner_gid": user_id, "team_gid": tenant_id,
            "operation_ref": {"operation_id": plan.plan_id, "status": "accepted", "version": 1},
        }
        self.repository.create_materialization_run(row)
        try:
            await self.connector_port.queue_plan(plan, context)
        except Exception as exc:
            self.repository.update_materialization_run(run_id, status="failed")
            if isinstance(exc, SimulationWorkflowError):
                raise
            raise SimulationWorkflowError(str(exc)) from exc
        return dict(row)

    async def start_capture(
        self, environment_id: str, environment_version: int, device_id: str,
        context: CapabilityContext,
    ) -> dict[str, Any]:
        tenant_id, user_id = self._identity(context)
        version_gid, definition_hash = self._provenance(context)
        manifest = self.repository.get_manifest(environment_id, environment_version, context)
        if manifest is None:
            raise SimulationWorkflowError("simulation_environment_not_found")
        capture_run_id = self.id_factory("capture")
        ordered = sorted(
            manifest.operations, key=lambda item: (item.sequence, item.operation_id), reverse=True,
        )
        plans = tuple(build_capture_plan(
            manifest,
            plan_id=capture_run_id if index == 1 else f"{capture_run_id}-op-{index:05d}",
            capture_run_id=capture_run_id, device_id=device_id, tenant_id=tenant_id,
            user_id=user_id, issued_at=self.clock(), operations=(item.operation_id,),
            capability_version_gid=version_gid, business_definition_hash=definition_hash,
        ) for index, item in enumerate(ordered, start=1))
        row = {
            "capture_run_id": capture_run_id, "environment_id": environment_id,
            "environment_version": environment_version, "manifest_hash": manifest.manifest_hash,
            "device_id": device_id, "plan_id": plans[0].plan_id, "status": "queued",
            "owner_gid": user_id, "team_gid": tenant_id,
            "operation_ref": {"operation_id": plans[0].plan_id, "status": "accepted", "version": 1},
            "steps": [{
                "operation_id": item.operation_id, "sequence": item.sequence,
                "status": "queued", "attempt": 1, "artifact_ref": None,
                "artifact_attached": False, "expected_scene_hash": item.scene.scene_hash,
            } for item in ordered],
        }
        self.repository.create_capture_run(row)
        try:
            for plan in plans:
                await self.connector_port.queue_plan(plan, context)
        except Exception as exc:
            self.repository.update_capture_run(capture_run_id, status="failed")
            if isinstance(exc, SimulationWorkflowError):
                raise
            raise SimulationWorkflowError(str(exc)) from exc
        return dict(row)

    def get(self, capture_run_id: str, context: CapabilityContext) -> dict[str, Any]:
        run = self.repository.get_capture_run(capture_run_id, context)
        if run is None:
            raise SimulationWorkflowError("capture_run_not_found")
        return run

    def record_step_result(
        self, capture_run_id: str, operation_id: str, *, status: str,
        artifact_ref: dict[str, Any] | None = None,
    ) -> None:
        if status not in {"running", "completed", "failed", "outcome_unknown"}:
            raise SimulationWorkflowError("capture_step_status_invalid")
        changes: dict[str, Any] = {"status": status}
        if status == "completed":
            if artifact_ref is None:
                raise SimulationWorkflowError("artifact_upload_unconfirmed")
            artifact = ArtifactRef.model_validate(artifact_ref)
            if not artifact.media_type.startswith("image/"):
                raise SimulationWorkflowError("capture_artifact_invalid")
            changes["artifact_ref"] = artifact.model_dump(mode="json")
        elif artifact_ref is not None:
            raise SimulationWorkflowError("capture_artifact_unexpected")
        self.repository.update_capture_step(capture_run_id, operation_id, **changes)
        self.repository.update_capture_run(capture_run_id, status="running")

    def apply_materialization_outcome(
        self, plan: ConnectorExecutionPlanV1, outcome: ConnectorPlanOutcomeV1,
    ) -> None:
        if outcome.plan_id != plan.plan_id or outcome.protocol != plan.protocol:
            raise SimulationWorkflowError("plan_outcome_invalid")
        materialization_operations = {
            "vismockup.application.probe@1", "vismockup.model.attach@1",
            "vismockup.scene.apply@1", "vismockup.scene.verify@1",
        }
        if not plan.steps or any(
            step.operation_id not in materialization_operations for step in plan.steps
        ):
            raise SimulationWorkflowError("plan_outcome_invalid")
        status = {
            "completed": "completed", "failed": "failed",
            "outcome_unknown": "outcome_unknown", "cancelled": "failed",
        }.get(outcome.status)
        if status is None:
            raise SimulationWorkflowError("plan_outcome_invalid")
        self.repository.update_materialization_run(plan.plan_id, status=status)

    async def advance(self, capture_run_id: str, context: CapabilityContext) -> dict[str, Any]:
        run = self.repository.get_capture_run(capture_run_id, context)
        if run is None:
            raise SimulationWorkflowError("capture_run_not_found")
        for step in run["steps"]:
            if step["status"] == "completed" and not step.get("artifact_attached"):
                artifact_ref = step.get("artifact_ref")
                if artifact_ref is None:
                    raise SimulationWorkflowError("artifact_upload_unconfirmed")
                try:
                    await self.craft_port.attach_screenshot(
                        bop_version_gid=run.get("bop_version_gid") or self.repository.get_manifest(
                            run["environment_id"], run["environment_version"], context,
                        ).execution_source.bop_version_gid,
                        operation_id=step["operation_id"], artifact_ref=artifact_ref,
                        capture_run_id=capture_run_id, context=context,
                    )
                except Exception as exc:
                    if isinstance(exc, SimulationWorkflowError):
                        raise
                    raise SimulationWorkflowError("craft_screenshot_attach_failed") from exc
                self.repository.update_capture_step(
                    capture_run_id, step["operation_id"], artifact_attached=True,
                )
                break
        refreshed = self.repository.get_capture_run(capture_run_id, context)
        if all(
            item["status"] == "cancelled"
            or (item["status"] == "completed" and item.get("artifact_attached"))
            for item in refreshed["steps"]
        ):
            self.repository.update_capture_run(capture_run_id, status="completed")
            refreshed = self.repository.get_capture_run(capture_run_id, context)
        return refreshed

    async def apply_connector_outcome(
        self,
        plan: ConnectorExecutionPlanV1,
        outcome: ConnectorPlanOutcomeV1,
        context: CapabilityContext,
    ) -> dict[str, Any]:
        """Project a verified Device-domain outcome into the capture aggregate."""
        if outcome.plan_id != plan.plan_id or outcome.protocol != plan.protocol:
            raise SimulationWorkflowError("plan_outcome_invalid")
        capture_steps = [step for step in plan.steps if step.operation_id == "vismockup.view.capture@1"]
        if len(capture_steps) != 1:
            raise SimulationWorkflowError("plan_outcome_invalid")
        capture_run_id = str(capture_steps[0].payload.get("capture_run_id") or "")
        run = self.repository.get_capture_run(capture_run_id, context)
        if run is None:
            raise SimulationWorkflowError("capture_run_not_found")

        results = {item.step_id: item for item in outcome.steps}
        known_steps = {item.step_id for item in plan.steps}
        if len(results) != len(outcome.steps) or any(item not in known_steps for item in results):
            raise SimulationWorkflowError("plan_outcome_invalid")

        current = {item["operation_id"]: item for item in run["steps"]}
        projected = 0
        for step in plan.steps:
            if step.operation_id != "vismockup.view.capture@1":
                continue
            operation_id = str(step.payload.get("operation_id") or "")
            if operation_id not in current:
                raise SimulationWorkflowError("capture_step_not_found")
            result = results.get(step.step_id)
            if result is None:
                continue
            existing = current[operation_id]
            if existing["status"] == "completed" and existing.get("artifact_attached"):
                continue
            if result.status == "completed":
                value = result.result
                artifact = value.get("artifact") if isinstance(value, Mapping) else None
                if not isinstance(artifact, Mapping):
                    raise SimulationWorkflowError("artifact_upload_unconfirmed")
                self.record_step_result(
                    capture_run_id, operation_id, status="completed", artifact_ref=dict(artifact),
                )
            else:
                self.record_step_result(capture_run_id, operation_id, status=result.status)
            projected += 1

        refreshed = run
        for _ in range(projected):
            refreshed = await self.advance(capture_run_id, context)
        statuses = {item["status"] for item in refreshed["steps"]}
        if "outcome_unknown" in statuses:
            self.repository.update_capture_run(capture_run_id, status="outcome_unknown")
        elif "failed" in statuses:
            terminal = statuses <= {"completed", "failed", "cancelled"}
            self.repository.update_capture_run(
                capture_run_id,
                status="partial" if terminal and "completed" in statuses else "failed",
            )
        return self.repository.get_capture_run(capture_run_id, context)

    async def retry_step(
        self, capture_run_id: str, operation_id: str, context: CapabilityContext,
    ) -> dict[str, Any]:
        run = self.repository.get_capture_run(capture_run_id, context)
        if run is None:
            raise SimulationWorkflowError("capture_run_not_found")
        step = next((item for item in run["steps"] if item["operation_id"] == operation_id), None)
        if step is None:
            raise SimulationWorkflowError("capture_step_not_found")
        if step["status"] == "outcome_unknown":
            raise SimulationWorkflowError("local_execution_outcome_unknown")
        if step["status"] != "failed":
            raise SimulationWorkflowError("capture_step_not_retryable")
        manifest = self.repository.get_manifest(run["environment_id"], run["environment_version"], context)
        if manifest is None or manifest.manifest_hash != run["manifest_hash"]:
            raise SimulationWorkflowError("environment_source_changed")
        tenant_id, user_id = self._identity(context)
        version_gid, definition_hash = self._provenance(context)
        retry_plan_id = self.id_factory("retry")
        attempt = int(step.get("attempt") or 1) + 1
        plan = build_capture_plan(
            manifest, plan_id=retry_plan_id, device_id=run["device_id"], tenant_id=tenant_id,
            user_id=user_id, issued_at=self.clock(), operations=(operation_id,), attempt=attempt,
            capture_run_id=capture_run_id,
            capability_version_gid=version_gid, business_definition_hash=definition_hash,
        )
        self.repository.update_capture_step(
            capture_run_id, operation_id, status="queued", attempt=attempt,
            artifact_ref=None, artifact_attached=False,
        )
        await self.connector_port.queue_plan(plan, context)
        return {"capture_run_id": capture_run_id, "operation_id": operation_id, "attempt": attempt, "plan_id": retry_plan_id, "status": "queued"}

    def cancel(self, capture_run_id: str, context: CapabilityContext) -> dict[str, Any]:
        run = self.repository.get_capture_run(capture_run_id, context)
        if run is None:
            raise SimulationWorkflowError("capture_run_not_found")
        has_active = False
        for step in run["steps"]:
            if step["status"] == "queued":
                self.repository.update_capture_step(capture_run_id, step["operation_id"], status="cancelled")
            elif step["status"] in {"running", "outcome_unknown"}:
                has_active = True
        status = "cancelling" if has_active else "cancelled"
        self.repository.update_capture_run(capture_run_id, status=status)
        return {"capture_run_id": capture_run_id, "status": status}


class ConnectorOutcomeProjection:
    def __init__(self, workflow: CaptureWorkflow, snapshot_workflow=None) -> None:
        self.workflow = workflow
        self.snapshot_workflow = snapshot_workflow

    async def apply(
        self, plan: ConnectorExecutionPlanV1, outcome: ConnectorPlanOutcomeV1,
    ) -> dict[str, Any] | None:
        operations = {step.operation_id for step in plan.steps}
        if operations == {"vismockup.document.snapshot@1"}:
            if self.snapshot_workflow is None:
                raise SimulationWorkflowError("document_snapshot_projection_unavailable")
            self.snapshot_workflow.apply_connector_outcome(plan, outcome)
            return None
        materialization_operations = {
            "vismockup.application.probe@1", "vismockup.model.attach@1",
            "vismockup.scene.apply@1", "vismockup.scene.verify@1",
        }
        if operations and operations <= materialization_operations:
            self.workflow.apply_materialization_outcome(plan, outcome)
            return None
        if "vismockup.view.capture@1" not in operations: return None
        context = CapabilityContext(
            user_gid=plan.user_id, team_gid=plan.tenant_id, source="connector",
        )
        return await self.workflow.apply_connector_outcome(plan, outcome, context)


__all__ = ["CaptureWorkflow", "ConnectorOutcomeProjection", "SimulationWorkflowError"]

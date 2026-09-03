"""Server-authoritative state machine for materialization and reverse capture."""
from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any, Callable

from backend.capability_v2.contracts import ArtifactRef
from backend.capability_v2.provider_contracts import CapabilityContext

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

    def start_materialization(
        self, environment_id: str, environment_version: int, device_id: str,
        context: CapabilityContext,
    ) -> dict[str, Any]:
        tenant_id, user_id = self._identity(context)
        manifest = self.repository.get_manifest(environment_id, environment_version, context)
        if manifest is None:
            raise SimulationWorkflowError("simulation_environment_not_found")
        run_id = self.id_factory("materialize")
        plan = build_materialization_plan(
            manifest, plan_id=run_id, device_id=device_id, tenant_id=tenant_id,
            user_id=user_id, issued_at=self.clock(),
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
            self.connector_port.queue_plan(plan, context)
        except Exception as exc:
            self.repository.update_materialization_run(run_id, status="failed")
            if isinstance(exc, SimulationWorkflowError):
                raise
            raise SimulationWorkflowError(str(exc)) from exc
        return dict(row)

    def start_capture(
        self, environment_id: str, environment_version: int, device_id: str,
        context: CapabilityContext,
    ) -> dict[str, Any]:
        tenant_id, user_id = self._identity(context)
        manifest = self.repository.get_manifest(environment_id, environment_version, context)
        if manifest is None:
            raise SimulationWorkflowError("simulation_environment_not_found")
        capture_run_id = self.id_factory("capture")
        ordered = sorted(
            manifest.operations, key=lambda item: (item.sequence, item.operation_id), reverse=True,
        )
        plan = build_capture_plan(
            manifest, plan_id=capture_run_id, device_id=device_id, tenant_id=tenant_id,
            user_id=user_id, issued_at=self.clock(),
        )
        row = {
            "capture_run_id": capture_run_id, "environment_id": environment_id,
            "environment_version": environment_version, "manifest_hash": manifest.manifest_hash,
            "device_id": device_id, "plan_id": plan.plan_id, "status": "queued",
            "owner_gid": user_id, "team_gid": tenant_id,
            "operation_ref": {"operation_id": plan.plan_id, "status": "accepted", "version": 1},
            "steps": [{
                "operation_id": item.operation_id, "sequence": item.sequence,
                "status": "queued", "attempt": 1, "artifact_ref": None,
                "artifact_attached": False, "expected_scene_hash": item.scene.scene_hash,
            } for item in ordered],
        }
        self.repository.create_capture_run(row)
        try:
            self.connector_port.queue_plan(plan, context)
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

    def advance(self, capture_run_id: str, context: CapabilityContext) -> dict[str, Any]:
        run = self.repository.get_capture_run(capture_run_id, context)
        if run is None:
            raise SimulationWorkflowError("capture_run_not_found")
        for step in run["steps"]:
            if step["status"] == "completed" and not step.get("artifact_attached"):
                artifact_ref = step.get("artifact_ref")
                if artifact_ref is None:
                    raise SimulationWorkflowError("artifact_upload_unconfirmed")
                try:
                    self.craft_port.attach_screenshot(
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

    def retry_step(
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
        retry_plan_id = self.id_factory("retry")
        attempt = int(step.get("attempt") or 1) + 1
        plan = build_capture_plan(
            manifest, plan_id=retry_plan_id, device_id=run["device_id"], tenant_id=tenant_id,
            user_id=user_id, issued_at=self.clock(), operations=(operation_id,), attempt=attempt,
        )
        self.repository.update_capture_step(
            capture_run_id, operation_id, status="queued", attempt=attempt,
            artifact_ref=None, artifact_attached=False,
        )
        self.connector_port.queue_plan(plan, context)
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


__all__ = ["CaptureWorkflow", "SimulationWorkflowError"]

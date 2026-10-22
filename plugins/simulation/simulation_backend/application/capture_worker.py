"""Server-authoritative state machine for materialization and reverse capture."""
from __future__ import annotations

from .connector_protocol_v2 import parse_plan, projection_status

import secrets
from datetime import UTC, datetime
from typing import Any, Callable, Mapping

from backend.capability_v2.contracts import ArtifactRef
from backend.capability_v2.provider_contracts import CapabilityContext
from backend.contracts.connector_execution_plan_v1 import (
    ConnectorExecutionPlanV1,
    ConnectorPlanOutcomeV1,
)

from .connector_plans import build_capture_plan, build_capture_batch_plan, build_materialization_plan
from .connector_workflow_v2 import matches_prepared_plan
from ..domain.environment_manifest import REQUIRED_CONNECTOR_OPERATIONS


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

    @staticmethod
    def _require_render_contract(manifest) -> None:
        contracts = {item.operation_id: item.contract_hash for item in manifest.connector_requirement.operations}
        if contracts.get("vismockup.scene.render@1") != REQUIRED_CONNECTOR_OPERATIONS["vismockup.scene.render@1"]:
            raise SimulationWorkflowError("simulation_capture_environment_upgrade_required")
        if not manifest.operations:
            raise SimulationWorkflowError("simulation_capture_operations_required")

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
        self._require_render_contract(manifest)
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
            "plan": plan.model_dump(mode="json"),
        }
        self.repository.create_materialization_run(row)
        return dict(row)

    def next_materialization_action(
        self, run_id: str, context: CapabilityContext,
    ) -> dict[str, Any] | None:
        run = self.repository.get_materialization_run(run_id, context)
        if run is None:
            raise SimulationWorkflowError("materialization_run_not_found")
        if run["status"] != "queued":
            return None
        plan = ConnectorExecutionPlanV1.model_validate(run["plan"])
        return {
            "capability_id": "simulation.connector.plan.queue", "major_version": 3,
            "payload": {"plan": plan.model_dump(mode="json")},
            "idempotency_key": plan.plan_id,
        }

    async def dispatch_materialization(
        self, run_id: str, approval_reference: str, context: CapabilityContext,
    ) -> dict[str, Any]:
        if not approval_reference:
            raise SimulationWorkflowError("downstream_confirmation_required")
        action = self.next_materialization_action(run_id, context)
        if action is None:
            raise SimulationWorkflowError("materialization_action_not_ready")
        plan = ConnectorExecutionPlanV1.model_validate(action["payload"]["plan"])
        await self.connector_port.queue_plan(
            plan, context, approval_reference=approval_reference,
            major_version=action["major_version"],
        )
        self.repository.update_materialization_run(run_id, status="running")
        return self.repository.get_materialization_run(run_id, context)

    async def start_capture(
        self, environment_id: str, environment_version: int, device_id: str,
        context: CapabilityContext, *, continuous: bool = False,
    ) -> dict[str, Any]:
        tenant_id, user_id = self._identity(context)
        version_gid, definition_hash = self._provenance(context)
        manifest = self.repository.get_manifest(environment_id, environment_version, context)
        if manifest is None:
            raise SimulationWorkflowError("simulation_environment_not_found")
        if not self.repository.has_completed_materialization(
            environment_id, environment_version, device_id, context,
        ):
            raise SimulationWorkflowError("simulation_result_not_ready")
        capture_run_id = self.id_factory("capture")
        self._require_render_contract(manifest)
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
        if continuous and any(item.product_node_keys for item in ordered):
            batch = build_capture_batch_plan(
                manifest, plan_id=capture_run_id, capture_run_id=capture_run_id,
                device_id=device_id, tenant_id=tenant_id, user_id=user_id, issued_at=self.clock(),
                operations=tuple(item.operation_id for item in ordered if item.product_node_keys),
                capability_version_gid=version_gid, business_definition_hash=definition_hash,
            )
            plans = tuple(batch if item.product_node_keys else plan for item, plan in zip(ordered, plans, strict=True))
        row = {
            "capture_run_id": capture_run_id, "environment_id": environment_id,
            "environment_version": environment_version, "manifest_hash": manifest.manifest_hash,
            "device_id": device_id, "plan_id": plans[0].plan_id,
            "status": "queued" if any(item.product_node_keys for item in ordered) else "completed",
            "owner_gid": user_id, "team_gid": tenant_id,
            "operation_ref": {"operation_id": plans[0].plan_id,
                              "status": "accepted" if any(item.product_node_keys for item in ordered) else "completed", "version": 1},
            "steps": [{
                "operation_id": item.operation_id, "sequence": item.sequence,
                "status": "queued" if item.product_node_keys else "skipped", "attempt": 1, "artifact_ref": None,
                "artifact_attached": False, "expected_scene_hash": item.scene.scene_hash,
                "plan": plan.model_dump(mode="json"),
            } for item, plan in zip(ordered, plans, strict=True)],
        }
        self.repository.create_capture_run(row)
        return dict(row)

    def next_action(self, capture_run_id: str, context: CapabilityContext) -> dict[str, Any] | None:
        run = self.repository.get_capture_run(capture_run_id, context)
        if run is None:
            raise SimulationWorkflowError("capture_run_not_found")
        if run["status"] in {
            "cancelling", "cancelled", "failed", "partial", "outcome_unknown",
        }:
            return None
        manifest = self.repository.get_manifest(
            run["environment_id"], run["environment_version"], context,
        )
        if manifest is None or manifest.manifest_hash != run["manifest_hash"]:
            raise SimulationWorkflowError("environment_source_changed")
        completed=[step for step in run['steps'] if step['status']=='completed' and not step.get('artifact_attached')]
        if completed and len([s for s in parse_plan(completed[0]['plan']).steps if s.operation_id=='vismockup.view.capture@1'])>1:
            if any(step['status']=='running' for step in run['steps']):return None
            if any(not step.get('artifact_ref') for step in completed):raise SimulationWorkflowError('artifact_upload_unconfirmed')
            return {'capability_id':'craft.process_screenshot.attach','major_version':2,
                'payload':{'bop_version_gid':manifest.execution_source.bop_version_gid,'expected_revision':manifest.execution_source.revision,
                    'capture_run_id':capture_run_id,'items':[{'operation_id':s['operation_id'],'artifact_ref':s['artifact_ref']} for s in completed]},
                'idempotency_key':f'{capture_run_id}:attach-batch'}
        for step in run["steps"]:
            if step["status"] == "completed" and not step.get("artifact_attached"):
                artifact_ref = step.get("artifact_ref")
                if artifact_ref is None:
                    raise SimulationWorkflowError("artifact_upload_unconfirmed")
                payload = {
                    "bop_version_gid": manifest.execution_source.bop_version_gid,
                    "operation_id": step["operation_id"], "artifact_ref": artifact_ref,
                    "capture_run_id": capture_run_id,
                }
                return {
                    "capability_id": "craft.process_screenshot.attach", "major_version": 1,
                    "payload": payload,
                    "idempotency_key": f"{capture_run_id}:{step['operation_id']}",
                }
        if any(step["status"] == "running" for step in run["steps"]):
            return None
        step = next((item for item in run["steps"] if item["status"] == "queued"), None)
        if step is None:
            return None
        plan = ConnectorExecutionPlanV1.model_validate(step["plan"])
        return {
            "capability_id": "simulation.connector.plan.queue", "major_version": 3,
            "payload": {"plan": plan.model_dump(mode="json")},
            "idempotency_key": plan.plan_id,
        }

    async def dispatch_next(
        self, capture_run_id: str, approval_reference: str, context: CapabilityContext,
    ) -> dict[str, Any]:
        if not approval_reference:
            raise SimulationWorkflowError("downstream_confirmation_required")
        action = self.next_action(capture_run_id, context)
        if action is None:
            raise SimulationWorkflowError("capture_action_not_ready")
        payload = action["payload"]
        if action["capability_id"] == "simulation.connector.plan.queue":
            plan = ConnectorExecutionPlanV1.model_validate(payload["plan"])
            await self.connector_port.queue_plan(
                plan, context, approval_reference=approval_reference,
                major_version=action["major_version"],
            )
            operation_ids = [
                str(step.payload["operation_id"]) for step in plan.steps
                if step.operation_id == "vismockup.view.capture@1"
            ]
            for operation_id in operation_ids:
                self.repository.update_capture_step(capture_run_id, operation_id, status="running")
            self.repository.update_capture_run(capture_run_id, status="running")
        else:
            if action['major_version']==2:
                receipt=await self.craft_port.attach_screenshots(**payload,context=context,approval_reference=approval_reference)
                actual=receipt.get('items',[]) if isinstance(receipt,Mapping) else []
                expected={item['operation_id']:item['artifact_ref'] for item in payload['items']}
                if len(actual)!=len(expected) or {item.get('operation_id') for item in actual}!=set(expected) or any(
                    item.get('bop_version_gid')!=payload['bop_version_gid'] or item.get('capture_run_id')!=capture_run_id or item.get('artifact_ref')!=expected.get(item.get('operation_id')) for item in actual):
                    raise SimulationWorkflowError('artifact_attachment_unconfirmed')
                for operation_id in expected:self.repository.update_capture_step(capture_run_id,operation_id,artifact_attached=True)
                self.repository.update_capture_run(capture_run_id,status='completed')
                return self.repository.get_capture_run(capture_run_id,context)
            await self.craft_port.attach_screenshot(
                **payload, context=context, approval_reference=approval_reference,
            )
            self.repository.update_capture_step(
                capture_run_id, payload["operation_id"], artifact_attached=True,
            )
            refreshed = self.repository.get_capture_run(capture_run_id, context)
            if all(
                step["status"] == "skipped" or (step["status"] == "completed" and step.get("artifact_attached"))
                for step in refreshed["steps"]
            ):
                self.repository.update_capture_run(capture_run_id, status="completed")
        return self.repository.get_capture_run(capture_run_id, context)

    def get(self, capture_run_id: str, context: CapabilityContext) -> dict[str, Any]:
        run = self.repository.get_capture_run(capture_run_id, context, include_plans=False)
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
        context: CapabilityContext,
    ) -> None:
        if outcome.plan_id != plan.plan_id or outcome.protocol != plan.protocol:
            raise SimulationWorkflowError("plan_outcome_invalid")
        materialization_operations = {
            "vismockup.application.probe@1", "vismockup.model.attach@1",
            "vismockup.scene.apply@1", "vismockup.scene.render@1", "vismockup.scene.verify@1",
        }
        if not plan.steps or any(
            step.operation_id not in materialization_operations for step in plan.steps
        ):
            raise SimulationWorkflowError("plan_outcome_invalid")
        persisted = self.repository.get_materialization_run(plan.plan_id, context)
        if persisted is None:
            raise SimulationWorkflowError("materialization_run_not_found")
        expected_plan = parse_plan(persisted.get("plan"))
        if not matches_prepared_plan(expected_plan, plan):
            raise SimulationWorkflowError("plan_outcome_invalid")
        status = {
            "completed": "completed", "failed": "failed",
            "outcome_unknown": "outcome_unknown", "cancelled": "failed",
        }.get(projection_status(outcome))
        if status is None:
            raise SimulationWorkflowError("plan_outcome_invalid")
        self.repository.update_materialization_run(plan.plan_id, status=status)

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
        if len(capture_steps) > 1:
            return self._apply_batch_outcome(plan, outcome, context)
        if len(capture_steps) != 1:
            raise SimulationWorkflowError("plan_outcome_invalid")
        capture_run_id = str(capture_steps[0].payload.get("capture_run_id") or "")
        run = self.repository.get_capture_run(capture_run_id, context)
        if run is None:
            raise SimulationWorkflowError("capture_run_not_found")
        was_cancelling = run["status"] in {"cancelling", "cancelled"}

        results = {item.step_id: item for item in outcome.steps}
        known_steps = {item.step_id for item in plan.steps}
        if len(results) != len(outcome.steps) or any(item not in known_steps for item in results):
            raise SimulationWorkflowError("plan_outcome_invalid")

        current = {item["operation_id"]: item for item in run["steps"]}
        capture_operation_id = str(capture_steps[0].payload.get("operation_id") or "")
        persisted_step = current.get(capture_operation_id)
        if persisted_step is None:
            raise SimulationWorkflowError("capture_step_not_found")
        expected_plan = parse_plan(persisted_step.get("plan"))
        if not matches_prepared_plan(expected_plan, plan):
            raise SimulationWorkflowError("plan_outcome_invalid")
        terminal_status = projection_status(outcome)
        if any(step.operation_id == "vismockup.scene.render@1" for step in plan.steps):
            complete = terminal_status == "completed" and all(
                step.step_id in results and projection_status(results[step.step_id]) == "completed"
                for step in plan.steps
            )
            if not complete:
                status = "failed" if terminal_status == "failed" else "outcome_unknown"
                if not persisted_step.get("artifact_attached"):
                    self.record_step_result(capture_run_id, capture_operation_id, status=status)
                    self.repository.update_capture_run(capture_run_id, status=status)
                return self.repository.get_capture_run(capture_run_id, context)
        v2 = outcome.protocol == 'ai00.connector.execution-plan.v2'
        if (terminal_status == 'outcome_unknown' and (not outcome.steps or v2)) or (
            v2 and terminal_status == 'failed' and capture_steps[0].step_id not in results
        ):
            self.record_step_result(
                capture_run_id, capture_operation_id, status=terminal_status,
            )
            self.repository.update_capture_run(capture_run_id, status=terminal_status)
            return self.repository.get_capture_run(capture_run_id, context)
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
            if projection_status(result) == "completed":
                value = result.result
                artifact = value.get("artifact") if isinstance(value, Mapping) else None
                if not isinstance(artifact, Mapping):
                    raise SimulationWorkflowError("artifact_upload_unconfirmed")
                self.record_step_result(
                    capture_run_id, operation_id, status="completed", artifact_ref=dict(artifact),
                )
            else:
                self.record_step_result(capture_run_id, operation_id, status=projection_status(result))
            projected += 1

        refreshed = self.repository.get_capture_run(capture_run_id, context)
        statuses = {item["status"] for item in refreshed["steps"]}
        if "outcome_unknown" in statuses:
            self.repository.update_capture_run(capture_run_id, status="outcome_unknown")
        elif "failed" in statuses:
            terminal = statuses <= {"completed", "failed", "cancelled"}
            self.repository.update_capture_run(
                capture_run_id,
                status="partial" if terminal and "completed" in statuses else "failed",
            )
        elif was_cancelling and "running" not in statuses:
            self.repository.update_capture_run(capture_run_id, status="cancelled")
        return self.repository.get_capture_run(capture_run_id, context)

    def _apply_batch_outcome(self, plan, outcome, context):
        captures = [step for step in plan.steps if step.operation_id == 'vismockup.view.capture@1']
        run_ids = {str(step.payload.get('capture_run_id') or '') for step in captures}
        if len(run_ids) != 1 or not next(iter(run_ids)):
            raise SimulationWorkflowError('plan_outcome_invalid')
        run_id = next(iter(run_ids)); run = self.repository.get_capture_run(run_id, context)
        if run is None:
            raise SimulationWorkflowError('capture_run_not_found')
        current = {step['operation_id']:step for step in run['steps']}
        results = {item.step_id:item for item in outcome.steps}
        if len(results)!=len(outcome.steps) or set(results)-{step.step_id for step in plan.steps}:
            raise SimulationWorkflowError('plan_outcome_invalid')
        updates=[]
        for capture in captures:
            operation_id=str(capture.payload.get('operation_id') or '')
            existing=current.get(operation_id)
            if existing is None or not matches_prepared_plan(parse_plan(existing.get('plan')),plan):
                raise SimulationWorkflowError('plan_outcome_invalid')
            group=[s for s in plan.steps if str(s.payload.get('operation_id') or '')==operation_id]
            complete=all(s.step_id in results and projection_status(results[s.step_id])=='completed' for s in group)
            if complete:
                value=results[capture.step_id].result
                try:
                    artifact=ArtifactRef.model_validate(value.get('artifact') if isinstance(value,Mapping) else None)
                    if artifact.media_type!='image/png':raise ValueError()
                except (ValueError,TypeError) as exc:
                    raise SimulationWorkflowError('artifact_upload_unconfirmed') from exc
                changes={'status':'completed','artifact_ref':artifact.model_dump(mode='json')}
            else:
                started=any(s.step_id in results for s in group)
                uncertain=projection_status(outcome)=='outcome_unknown'
                changes={'status':'outcome_unknown' if uncertain else 'failed' if started else 'cancelled'}
            if not existing.get('artifact_attached'):updates.append((operation_id,changes))
        # Validate every identity and receipt before projecting any batch member.
        for operation_id,changes in updates:self.repository.update_capture_step(run_id,operation_id,**changes)
        refreshed=self.repository.get_capture_run(run_id,context)
        statuses={s['status'] for s in refreshed['steps']}
        status='outcome_unknown' if 'outcome_unknown' in statuses else 'partial' if statuses&{'failed','cancelled'} and 'completed' in statuses else 'failed' if statuses&{'failed','cancelled'} else 'running'
        if all(s['status']=='skipped' or s['status']=='completed' and s.get('artifact_attached') for s in refreshed['steps']):status='completed'
        if run['status'] in {'cancelling','cancelled'}:status='cancelled'
        self.repository.update_capture_run(run_id,status=status)
        return self.repository.get_capture_run(run_id,context)

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
        self._require_render_contract(manifest)
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
            plan=plan.model_dump(mode="json"), artifact_ref=None, artifact_attached=False,
        )
        self.repository.update_capture_run(capture_run_id, status="queued")
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

"""Governed projection of authenticated Device Connector outcomes into Simulation."""
from __future__ import annotations

import json

from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError,
    CapabilityOutput,
    CapabilityRisk,
    CapabilitySpec,
    EvidenceRef,
)
from backend.contracts.connector_execution_plan_v1 import (
    ConnectorExecutionPlanV1,
    ConnectorPlanOutcomeV1,
)

from ..application.capture_worker import CaptureWorkflow, SimulationWorkflowError
from ..application.document_snapshots import DocumentSnapshotWorkflow


class ConnectorOutcomeProvider:
    def __init__(
        self,
        workflow: CaptureWorkflow,
        snapshot_workflow: DocumentSnapshotWorkflow | None,
    ) -> None:
        self.workflow = workflow
        self.snapshot_workflow = snapshot_workflow

    @staticmethod
    def _contracts(payload):
        try:
            plan = ConnectorExecutionPlanV1.model_validate(json.loads(payload["plan_json"]))
            outcome = ConnectorPlanOutcomeV1.model_validate(json.loads(payload["outcome_json"]))
        except Exception as exc:
            raise CapabilityBusinessError("plan_outcome_invalid", "plan_outcome_invalid") from exc
        if outcome.plan_id != plan.plan_id or outcome.protocol != plan.protocol:
            raise CapabilityBusinessError("plan_outcome_invalid", "plan_outcome_invalid")
        return plan, outcome

    @staticmethod
    def _result(resource_id: str, kind: str) -> CapabilityOutput:
        return CapabilityOutput(
            data={"resource_id": resource_id, "status": "applied"},
            evidence=(EvidenceRef(kind=kind, reference=f"simulation://{kind}/{resource_id}"),),
        )

    async def apply_capture(self, payload, context):
        plan, outcome = self._contracts(payload)
        capture_steps = [
            step for step in plan.steps if step.operation_id == "vismockup.view.capture@1"
        ]
        actual_id = str(capture_steps[0].payload.get("capture_run_id") or "") if len(capture_steps) == 1 else ""
        if actual_id != payload["capture_run_id"]:
            raise CapabilityBusinessError("plan_outcome_invalid", "plan_outcome_invalid")
        try:
            await self.workflow.apply_connector_outcome(plan, outcome, context)
        except SimulationWorkflowError as exc:
            raise CapabilityBusinessError(str(exc), str(exc)) from exc
        return self._result(actual_id, "capture-outcome")

    async def apply_materialization(self, payload, context):
        plan, outcome = self._contracts(payload)
        if plan.plan_id != payload["run_id"]:
            raise CapabilityBusinessError("plan_outcome_invalid", "plan_outcome_invalid")
        try:
            self.workflow.apply_materialization_outcome(plan, outcome, context)
        except SimulationWorkflowError as exc:
            raise CapabilityBusinessError(str(exc), str(exc)) from exc
        return self._result(payload["run_id"], "materialization-outcome")

    async def apply_document_snapshot(self, payload, context):
        plan, outcome = self._contracts(payload)
        if self.snapshot_workflow is None or plan.plan_id != payload["snapshot_request_id"]:
            raise CapabilityBusinessError("plan_outcome_invalid", "plan_outcome_invalid")
        try:
            self.snapshot_workflow.apply_connector_outcome(plan, outcome, context)
        except SimulationWorkflowError as exc:
            raise CapabilityBusinessError(str(exc), str(exc)) from exc
        return self._result(payload["snapshot_request_id"], "document-snapshot-outcome")


def specs(provider: ConnectorOutcomeProvider):
    common = {
        "owner": "simulation", "version": 1, "permissions": ("simulation.use",),
        "plugin_callable": False, "tags": ("simulation", "connector_environment"),
        "risk": CapabilityRisk.WRITE, "confirmation": "none", "idempotent": True,
    }
    return (
        (CapabilitySpec(id="simulation.connector_capture_outcome.apply", description="Project one authenticated Connector capture outcome into its exact Simulation capture run.", **common), provider.apply_capture),
        (CapabilitySpec(id="simulation.connector_materialization_outcome.apply", description="Project one authenticated Connector materialization outcome into its exact Simulation run.", **common), provider.apply_materialization),
        (CapabilitySpec(id="simulation.connector_document_snapshot_outcome.apply", description="Project one authenticated Connector document snapshot outcome into its exact Simulation request.", **common), provider.apply_document_snapshot),
    )


__all__ = ["ConnectorOutcomeProvider", "specs"]

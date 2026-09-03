"""Asynchronous acquisition of the bound user's active VisMockup BOM."""
from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any, Callable, Mapping

from backend.capability_v2.provider_contracts import CapabilityContext
from backend.contracts.connector_execution_plan_v1 import (
    ConnectorExecutionPlanV1, ConnectorPlanOutcomeV1,
)

from .capture_worker import SimulationWorkflowError
from .connector_plans import build_document_snapshot_plan


def _validate_snapshot(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SimulationWorkflowError("bom_snapshot_invalid")
    required = {"document_id", "root_node_key", "source_identity", "snapshot_hash", "nodes"}
    if not required <= value.keys() or not isinstance(value["nodes"], list):
        raise SimulationWorkflowError("bom_snapshot_invalid")
    nodes = [dict(item) for item in value["nodes"] if isinstance(item, Mapping)]
    if len(nodes) != len(value["nodes"]) or not nodes or len(nodes) > 10_000:
        raise SimulationWorkflowError("bom_snapshot_invalid")
    keys = [str(item.get("node_key") or "") for item in nodes]
    if not all(keys) or len(keys) != len(set(keys)):
        raise SimulationWorkflowError("bom_snapshot_invalid")
    if str(value["root_node_key"]) not in keys:
        raise SimulationWorkflowError("bom_snapshot_invalid")
    if any("product_ref" not in item or "child_order" not in item for item in nodes):
        raise SimulationWorkflowError("bom_snapshot_invalid")
    return {**dict(value), "nodes": nodes}


class DocumentSnapshotWorkflow:
    def __init__(
        self, *, repository, connector_port,
        id_factory: Callable[[str], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.connector_port = connector_port
        self.id_factory = id_factory or (lambda prefix: f"{prefix}-{secrets.token_hex(16)}")
        self.clock = clock or (lambda: datetime.now(UTC))

    def request(
        self, device_id: str, request_key: str, context: CapabilityContext,
    ) -> dict[str, Any]:
        if not context.team_gid:
            raise SimulationWorkflowError("tenant_context_required")
        request_id = self.id_factory("snapshot")
        plan = build_document_snapshot_plan(
            plan_id=request_id, device_id=device_id, tenant_id=context.team_gid,
            user_id=context.user_gid, issued_at=self.clock(),
        )
        row = {
            "snapshot_request_id": request_id, "request_key": request_key,
            "device_id": device_id, "plan_id": plan.plan_id, "status": "queued",
            "snapshot": None, "failure_code": "", "owner_gid": context.user_gid,
            "team_gid": context.team_gid,
            "operation_ref": {"operation_id": plan.plan_id, "status": "accepted", "version": 1},
        }
        persisted = self.repository.create_request(row, context)
        if persisted["snapshot_request_id"] != request_id:
            return persisted
        try:
            self.connector_port.queue_plan(plan, context)
        except Exception:
            self.repository.complete_request(
                request_id, status="failed", failure_code="connector_offline",
            )
            raise
        return persisted

    def get(self, request_id: str, context: CapabilityContext) -> dict[str, Any]:
        row = self.repository.get_request(request_id, context)
        if row is None:
            raise SimulationWorkflowError("document_snapshot_not_found")
        return row

    def apply_connector_outcome(
        self, plan: ConnectorExecutionPlanV1, outcome: ConnectorPlanOutcomeV1,
    ) -> None:
        if outcome.plan_id != plan.plan_id or not outcome.steps:
            raise SimulationWorkflowError("plan_outcome_invalid")
        result = outcome.steps[0]
        if result.step_id != plan.steps[0].step_id:
            raise SimulationWorkflowError("plan_outcome_invalid")
        if result.status == "completed":
            self.repository.complete_request(
                plan.plan_id, snapshot=_validate_snapshot(result.result), status="completed",
            )
        else:
            self.repository.complete_request(
                plan.plan_id, status=result.status, failure_code=result.error_code,
            )


__all__ = ["DocumentSnapshotWorkflow"]

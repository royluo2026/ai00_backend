"""Governed asynchronous active-document snapshot capabilities."""
from __future__ import annotations

import json

from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError, CapabilityOutput, CapabilityRisk, CapabilitySpec, EvidenceRef,
)
from backend.contracts.connector_execution_plan_v1 import canonical_hash

from ..application.capture_worker import SimulationWorkflowError
from ..application.document_snapshots import DocumentSnapshotWorkflow
from ..application.runtime_ports import connector_port
from ..data.document_snapshot_repository import repository


class DocumentSnapshotProvider:
    def __init__(self, workflow: DocumentSnapshotWorkflow): self.workflow = workflow

    @staticmethod
    def _call(function, *args):
        try:
            return function(*args)
        except SimulationWorkflowError as exc:
            raise CapabilityBusinessError(str(exc), str(exc)) from exc

    async def request(self, payload, context):
        try:
            row = await self.workflow.request(
                payload["device_id"], payload["request_key"], context,
            )
        except SimulationWorkflowError as exc:
            raise CapabilityBusinessError(str(exc), str(exc)) from exc
        return CapabilityOutput(data=self._project(row), evidence=(EvidenceRef(
            kind="simulation.document_snapshot",
            reference=f"simulation://document-snapshot/{row['snapshot_request_id']}",
        ),))

    @staticmethod
    def migration_required(payload, context):
        raise CapabilityBusinessError(
            "capability_migration_required",
            "This immediate-dispatch version is closed; migrate to the @2 prepare/action/dispatch workflow.",
        )

    def get(self, payload, context):
        row = self._call(self.workflow.get, payload["snapshot_request_id"], context)
        digest = row["snapshot"].get("snapshot_hash") if row.get("snapshot") else None
        return CapabilityOutput(data=self._project(row), evidence=(EvidenceRef(
            kind="simulation.document_snapshot",
            reference=f"simulation://document-snapshot/{row['snapshot_request_id']}", digest=digest,
        ),))

    def action(self, payload, context):
        action = self._call(
            self.workflow.next_action, payload["snapshot_request_id"], context,
        )
        if action is not None:
            action = {
                "capability_id": action["capability_id"],
                "major_version": action["major_version"],
                "payload_json": json.dumps(action["payload"], sort_keys=True, separators=(",", ":")),
                "payload_hash": canonical_hash(action["payload"]),
                "idempotency_key": action["idempotency_key"],
            }
        return CapabilityOutput(data={"action": action})

    async def dispatch(self, payload, context):
        try:
            row = await self.workflow.dispatch(
                payload["snapshot_request_id"], context.confirmation_token, context,
            )
        except SimulationWorkflowError as exc:
            raise CapabilityBusinessError(str(exc), str(exc)) from exc
        return CapabilityOutput(data=self._project(row))

    @staticmethod
    def _project(row):
        return {key: row.get(key) for key in (
            "snapshot_request_id", "device_id", "plan_id", "status", "snapshot",
            "failure_code", "operation_ref",
        )}


default_workflow = DocumentSnapshotWorkflow(repository=repository, connector_port=connector_port)
default_provider = DocumentSnapshotProvider(default_workflow)


def specs(provider=default_provider):
    common = {"owner": "simulation", "permissions": ("simulation.use",),
              "plugin_callable": True, "tags": ("simulation", "connector_environment")}
    return (
        (CapabilitySpec(id="simulation.document_snapshot.request", version=1, description="Request and queue an immutable snapshot of the bound user's active VisMockup BOM.", risk=CapabilityRisk.WRITE, confirmation="user", **common), provider.migration_required),
        (CapabilitySpec(id="simulation.document_snapshot.request", version=2, description="Prepare an immutable active VisMockup BOM snapshot for separately confirmed dispatch.", risk=CapabilityRisk.WRITE, confirmation="user", **common), provider.request),
        (CapabilitySpec(id="simulation.document_snapshot.get", version=1, description="Read authoritative progress and the confirmed active VisMockup BOM snapshot.", risk=CapabilityRisk.READ, confirmation="none", **common), provider.get),
        (CapabilitySpec(id="simulation.document_snapshot.action.get", version=1, description="Read the exact snapshot action awaiting user confirmation.", risk=CapabilityRisk.READ, confirmation="none", **common), provider.action),
        (CapabilitySpec(id="simulation.document_snapshot.dispatch", version=1, description="Dispatch the prepared snapshot action using its separate user confirmation.", risk=CapabilityRisk.WRITE, confirmation="none", **common), provider.dispatch),
    )


__all__ = ["DocumentSnapshotProvider", "default_provider", "default_workflow", "specs"]

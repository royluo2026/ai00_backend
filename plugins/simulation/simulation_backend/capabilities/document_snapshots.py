"""Governed asynchronous active-document snapshot capabilities."""
from __future__ import annotations

from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError, CapabilityOutput, CapabilityRisk, CapabilitySpec, EvidenceRef,
)

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

    def request(self, payload, context):
        row = self._call(
            self.workflow.request, payload["device_id"], payload["request_key"], context,
        )
        return CapabilityOutput(data=self._project(row), evidence=(EvidenceRef(
            kind="simulation.document_snapshot",
            reference=f"simulation://document-snapshot/{row['snapshot_request_id']}",
        ),))

    def get(self, payload, context):
        row = self._call(self.workflow.get, payload["snapshot_request_id"], context)
        digest = row["snapshot"].get("snapshot_hash") if row.get("snapshot") else None
        return CapabilityOutput(data=self._project(row), evidence=(EvidenceRef(
            kind="simulation.document_snapshot",
            reference=f"simulation://document-snapshot/{row['snapshot_request_id']}", digest=digest,
        ),))

    @staticmethod
    def _project(row):
        return {key: row.get(key) for key in (
            "snapshot_request_id", "device_id", "plan_id", "status", "snapshot",
            "failure_code", "operation_ref",
        )}


default_workflow = DocumentSnapshotWorkflow(repository=repository, connector_port=connector_port)
default_provider = DocumentSnapshotProvider(default_workflow)


def specs(provider=default_provider):
    common = {"owner": "simulation", "version": 1, "permissions": ("simulation.use",),
              "plugin_callable": True, "tags": ("simulation", "connector_environment")}
    return (
        (CapabilitySpec(id="simulation.document_snapshot.request", description="Request an immutable snapshot of the bound user's active VisMockup BOM.", risk=CapabilityRisk.WRITE, confirmation="user", **common), provider.request),
        (CapabilitySpec(id="simulation.document_snapshot.get", description="Read authoritative progress and the confirmed active VisMockup BOM snapshot.", risk=CapabilityRisk.READ, confirmation="none", **common), provider.get),
    )


__all__ = ["DocumentSnapshotProvider", "default_provider", "default_workflow", "specs"]

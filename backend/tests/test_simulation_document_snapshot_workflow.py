from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.capability_v2.provider_contracts import CapabilityContext
from backend.contracts.connector_execution_plan_v1 import (
    ConnectorPlanOutcomeV1, ConnectorStepResultV1, canonical_hash,
)
from plugins.simulation.simulation_backend.application.document_snapshots import (
    DocumentSnapshotWorkflow,
)
from plugins.simulation.simulation_backend.application.capture_worker import SimulationWorkflowError


NOW = datetime(2026, 9, 3, tzinfo=UTC)
SNAPSHOT = {
    "document_id": "BOM-1", "root_node_key": "root",
    "source_identity": "tc://BOM-1/A", "snapshot_hash": "sha256:" + "a" * 64,
    "nodes": [
        {"node_key": "root", "parent_key": None, "product_ref": "ROOT", "child_order": 0},
        {"node_key": "n-1", "parent_key": "root", "product_ref": "P-1", "child_order": 0},
    ],
}


class Repository:
    def __init__(self): self.rows = {}
    def create_request(self, row, context):
        existing = next((item for item in self.rows.values() if item["request_key"] == row["request_key"]), None)
        if existing: return existing
        self.rows[row["snapshot_request_id"]] = dict(row)
        return dict(row)
    def get_request(self, request_id, context): return self.rows.get(request_id)
    def complete_request(self, request_id, *, snapshot=None, status="completed", failure_code=""):
        self.rows[request_id].update(status=status, snapshot=snapshot, failure_code=failure_code)


class Connector:
    def __init__(self): self.plans = []
    def queue_plan(self, plan, context): self.plans.append(plan)


def context(user="user-1", team="team-1"):
    return CapabilityContext(user_gid=user, team_gid=team)


def test_snapshot_request_is_idempotent_and_completes_only_from_connector_outcome():
    repository, connector = Repository(), Connector()
    ids = iter(("snapshot-1", "snapshot-2"))
    workflow = DocumentSnapshotWorkflow(
        repository=repository, connector_port=connector,
        id_factory=lambda _prefix: next(ids), clock=lambda: NOW,
    )

    first = workflow.request("device-1", "web-request-1", context())
    second = workflow.request("device-1", "web-request-1", context())
    assert first["status"] == second["status"] == "queued"
    assert len(connector.plans) == 1

    plan = connector.plans[0]
    result = ConnectorStepResultV1(
        step_id=plan.steps[0].step_id, status="completed", result=SNAPSHOT,
        result_hash=canonical_hash(SNAPSHOT), started_at=NOW, completed_at=NOW,
    )
    outcome = ConnectorPlanOutcomeV1(
        protocol=plan.protocol, plan_id=plan.plan_id, status="completed",
        steps=(result,), reported_at=NOW,
    )
    workflow.apply_connector_outcome(plan, outcome)

    completed = workflow.get("snapshot-1", context())
    assert completed["snapshot"] == SNAPSHOT
    assert completed["status"] == "completed"


def test_snapshot_visibility_is_owner_or_team_scoped():
    class ScopedRepository(Repository):
        def get_request(self, request_id, ctx):
            row = self.rows.get(request_id)
            return row if row and (row["owner_gid"] == ctx.user_gid or row["team_gid"] == ctx.team_gid) else None

    workflow = DocumentSnapshotWorkflow(
        repository=ScopedRepository(), connector_port=Connector(),
        id_factory=lambda _prefix: "snapshot-1", clock=lambda: NOW,
    )
    workflow.request("device-1", "web-request-1", context())
    assert workflow.get("snapshot-1", context("user-2"))["snapshot_request_id"] == "snapshot-1"
    with pytest.raises(SimulationWorkflowError, match="document_snapshot_not_found"):
        workflow.get("snapshot-1", context("user-3", "team-2"))

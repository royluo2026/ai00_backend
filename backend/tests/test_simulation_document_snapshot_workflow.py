from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.capability_v2.provider_contracts import CapabilityContext
from backend.contracts.connector_execution_plan_v1 import (
    ConnectorPlanOutcomeV1, ConnectorStepResultV1, canonical_hash,
)
from plugins.simulation.simulation_backend.application.document_snapshots import (
    DocumentSnapshotWorkflow,
)
from plugins.simulation.simulation_backend.application.capture_worker import SimulationWorkflowError
from plugins.simulation.simulation_backend.capabilities import (
    _authorize_document_snapshot,
    _authorize_materialization_run,
    _authorize_parameter_set,
    _authorize_profile,
    _authorize_run,
)
from plugins.simulation.simulation_backend.capabilities import default_capture_provider
from plugins.simulation.simulation_backend.capabilities import legacy_repository
from plugins.simulation.simulation_backend.capabilities import default_snapshot_workflow


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
    def mark_dispatched(self, request_id): self.rows[request_id]["dispatched"] = True


class Connector:
    def __init__(self): self.plans = []
    async def queue_plan(self, plan, context, *, approval_reference):
        self.plans.append((plan, approval_reference))


def context(user="user-1", team="team-1"):
    return CapabilityContext(
        user_gid=user, team_gid=team, capability_version_gid="cv2_test",
        business_definition_hash="sha256:" + "d" * 64,
    )


def test_snapshot_request_is_idempotent_and_completes_only_from_connector_outcome():
    repository, connector = Repository(), Connector()
    ids = iter(("snapshot-1", "snapshot-2"))
    workflow = DocumentSnapshotWorkflow(
        repository=repository, connector_port=connector,
        id_factory=lambda _prefix: next(ids), clock=lambda: NOW,
    )

    first = asyncio.run(workflow.request("device-1", "web-request-1", context()))
    second = asyncio.run(workflow.request("device-1", "web-request-1", context()))
    assert first["status"] == second["status"] == "queued"
    assert connector.plans == []
    action = workflow.next_action("snapshot-1", context())
    assert action["capability_id"] == "device.connector.plan.queue"
    assert action["major_version"] == 2
    asyncio.run(workflow.dispatch("snapshot-1", "approval-snapshot", context()))
    assert len(connector.plans) == 1
    assert connector.plans[0][1] == "approval-snapshot"

    plan = connector.plans[0][0]
    result = ConnectorStepResultV1(
        step_id=plan.steps[0].step_id, status="completed", result=SNAPSHOT,
        result_hash=canonical_hash(SNAPSHOT), started_at=NOW, completed_at=NOW,
    )
    outcome = ConnectorPlanOutcomeV1(
        protocol=plan.protocol, plan_id=plan.plan_id, status="completed",
        steps=(result,), reported_at=NOW,
    )
    workflow.apply_connector_outcome(plan, outcome, context())

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
    asyncio.run(workflow.request("device-1", "web-request-1", context()))
    assert workflow.get("snapshot-1", context("user-2"))["snapshot_request_id"] == "snapshot-1"
    with pytest.raises(SimulationWorkflowError, match="document_snapshot_not_found"):
        workflow.get("snapshot-1", context("user-3", "team-2"))


def test_snapshot_resource_authorizer_delegates_visibility_to_simulation_repository(monkeypatch):
    calls = []
    monkeypatch.setattr(
        default_snapshot_workflow.repository,
        "can_read_request",
        lambda request_id, **identity: calls.append((request_id, identity)) or True,
    )
    identity = SimpleNamespace(
        actor=SimpleNamespace(user_id="user-1"),
        tenant=SimpleNamespace(tenant_id="team-1"),
    )

    assert _authorize_document_snapshot("snapshot-1", identity) is True
    assert calls == [("snapshot-1", {"user_gid": "user-1", "team_gid": "team-1"})]


def test_simulation_owned_resource_authorizers_delegate_exact_identity_scope(monkeypatch):
    calls = []
    scope = {"user_gid": "user-1", "team_gid": "team-1"}
    monkeypatch.setattr(legacy_repository, "can_read_parameter_set", lambda rid, **kw: calls.append(("parameter", rid, kw)) or True)
    monkeypatch.setattr(legacy_repository, "can_read_profile", lambda rid, **kw: calls.append(("profile", rid, kw)) or True)
    monkeypatch.setattr(legacy_repository, "can_read_run", lambda rid, **kw: calls.append(("run", rid, kw)) or True)
    monkeypatch.setattr(default_capture_provider.workflow.repository, "can_read_materialization_run", lambda rid, **kw: calls.append(("materialization", rid, kw)) or True)
    identity = SimpleNamespace(
        actor=SimpleNamespace(user_id="user-1"),
        tenant=SimpleNamespace(tenant_id="team-1"),
    )

    assert _authorize_parameter_set("parameters-1", identity)
    assert _authorize_profile("profile-1", identity)
    assert _authorize_run("run-1", identity)
    assert _authorize_materialization_run("materialize-1", identity)
    assert calls == [
        ("parameter", "parameters-1", scope),
        ("profile", "profile-1", scope),
        ("run", "run-1", scope),
        ("materialization", "materialize-1", scope),
    ]

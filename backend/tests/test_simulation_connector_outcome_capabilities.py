from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from backend.capability_v2.provider_contracts import CapabilityContext
from backend.contracts.connector_execution_plan_v1 import (
    ConnectorPlanOutcomeV1,
    ConnectorStepResultV1,
    canonical_hash,
)
from backend.tests.test_simulation_capture_workflow import ARTIFACT, _context, _workflow
from plugins.simulation.simulation_backend.capabilities.connector_outcomes import (
    ConnectorOutcomeProvider,
)


def test_capture_outcome_is_projected_only_through_its_exact_simulation_resource():
    workflow, repository, connector, _ = _workflow()
    asyncio.run(workflow.start_capture("env-1", 1, "device-1", _context()))
    asyncio.run(workflow.dispatch_next("run-1", "approval-device", _context()))
    plan = connector.plans[0][0]
    now = datetime(2026, 9, 3, tzinfo=UTC)
    results = []
    for step in plan.steps:
        value = {"artifact": ARTIFACT} if step.operation_id == "vismockup.view.capture@1" else {}
        results.append(ConnectorStepResultV1(
            step_id=step.step_id, status="completed", result=value,
            result_hash=canonical_hash(value), started_at=now, completed_at=now,
        ))
    outcome = ConnectorPlanOutcomeV1(
        protocol=plan.protocol, plan_id=plan.plan_id, status="completed",
        steps=tuple(results), reported_at=now,
    )
    provider = ConnectorOutcomeProvider(workflow, snapshot_workflow=None)
    payload = {
        "capture_run_id": "run-1",
        "plan_json": json.dumps(plan.model_dump(mode="json")),
        "outcome_json": json.dumps(outcome.model_dump(mode="json")),
    }

    result = asyncio.run(provider.apply_capture(payload, CapabilityContext(
        user_gid="user-1", team_gid="team-1", source="connector",
    )))

    assert result.data == {"resource_id": "run-1", "status": "applied"}
    assert repository.runs["run-1"]["steps"][0]["status"] == "completed"

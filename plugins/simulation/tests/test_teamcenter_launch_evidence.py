from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path

import pytest

from backend.contracts.connector_execution_plan_v2 import canonicalize_v2, compute_plan_hash
from backend.tests.test_simulation_connector_runtime_v2_sql import sign_outcome
from plugins.simulation.simulation_backend.application.teamcenter_launch_evidence import (
    verify_teamcenter_launch_evidence,
)

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 9, 17, 1, 26, 21, tzinfo=UTC)
CONTRACT_HASH = "sha256:d74338b54d5abd84dad3435768aa56756ef4fbb560f1d605b2b1bb9cc18519a8"
SOURCE_HASH = "sha256:ced5e4711a616c7597e52f61b7b495cb12c0fc5e5ed78e3ec0efbe87cd935f92"
LAUNCH_ID = "tclaunch:" + "b" * 64


def evidence():
    vector = json.loads((ROOT / "backend/tests/fixtures/connector_execution_plan_v2.json").read_text())
    plan, outcome = deepcopy(vector["plan"]), deepcopy(vector["outcome"])
    payload = {
        "source_selector": {
            "endpoint_id": "tc-production",
            "object_uid": "object-uid",
            "item_revision_uid": "revision-uid",
            "bom_view_uid": "",
            "revision_rule": "Latest Working",
            "configuration_date": "2026-09-17T01:20:00.000Z",
        },
        "expected_visdoc_uid": "",
    }
    plan.update(
        capability_id="simulation.teamcenter.visualization.launch.request",
        major_version=1,
        issued_at="2026-09-17T01:20:00Z",
        expires_at="2026-09-17T01:30:00Z",
    )
    plan["steps"][0].update(
        operation_id="teamcenter.visualization.launch@1",
        contract_hash=CONTRACT_HASH,
        payload=payload,
        payload_hash="sha256:" + hashlib.sha256(canonicalize_v2(payload)).hexdigest(),
        side_effect_classification="write",
        post_condition_probe_id="vismockup.application.probe@1",
    )
    plan["plan_hash"] = compute_plan_hash(plan)
    result = {
        "launch_id": LAUNCH_ID,
        "runner_started": True,
        "expected_visdoc_uid": "",
        "source_identity_hash": SOURCE_HASH,
    }
    outcome.update(plan_hash=plan["plan_hash"], reported_at="2026-09-17T01:26:20Z")
    outcome["steps"][0].update(
        result=result,
        result_hash="sha256:" + hashlib.sha256(canonicalize_v2(result)).hexdigest(),
        started_at="2026-09-17T01:26:18Z",
        completed_at="2026-09-17T01:26:19Z",
    )
    outcome["signature"] = sign_outcome(outcome)
    row = {
        "plan_id": plan["plan_id"],
        "device_id": plan["device_id"],
        "tenant_gid": plan["tenant_id"],
        "actor_gid": plan["actor_id"],
        "protocol": plan["protocol"],
        "runtime_generation": plan["runtime_generation"],
        "runtime_instance_id": plan["runtime_instance_id"],
        "session_token_hash": "session-hash",
        "lease_id": outcome["lease_id"],
        "plan_hash": plan["plan_hash"],
        "plan_json": plan,
        "outcome_json": outcome,
        "status": "succeeded",
        "outcome_hash": hashlib.sha256(canonicalize_v2(outcome)).hexdigest(),
        "updated_at": NOW,
        "lease_until": NOW + timedelta(seconds=60),
    }
    runtime = {
        "device_id": plan["device_id"],
        "owner_user_gid": plan["actor_id"],
        "tenant_gid": plan["tenant_id"],
        "protocol": plan["protocol"],
        "runtime_type": "electron",
        "status": "active",
        "runtime_generation": plan["runtime_generation"],
        "current_runtime_instance_id": plan["runtime_instance_id"],
        "session_token_hash": "session-hash",
        "session_expires_at": NOW + timedelta(minutes=5),
        "heartbeat_at": NOW,
        "device_key_id": outcome["device_key_id"],
        "device_signing_jwk": vector["device_public_jwk"],
    }
    return row, runtime


def verify(row, runtime, now=NOW):
    return verify_teamcenter_launch_evidence(
        row, runtime, actor_id="user-001", tenant_id="tenant-001", now=now
    )


def test_verifies_only_persisted_signed_teamcenter_launch():
    row, runtime = evidence()
    assert verify(row, runtime) == {
        "connector_device_id": "device-001",
        "source_identity_hash": SOURCE_HASH,
        "launch_id": LAUNCH_ID,
    }


@pytest.mark.parametrize(
    "target,field,value",
    [
        ("row", "actor_gid", "other"),
        ("row", "tenant_gid", "other"),
        ("row", "device_id", "other"),
        ("row", "status", "failed_without_effect"),
        ("runtime", "owner_user_gid", "other"),
        ("runtime", "tenant_gid", "other"),
        ("runtime", "device_id", "other"),
        ("runtime", "status", "revoked"),
        ("row", "updated_at", NOW - timedelta(minutes=3)),
    ],
)
def test_refuses_wrong_scope_runtime_status_and_stale_receipt(target, field, value):
    row, runtime = evidence()
    (row if target == "row" else runtime)[field] = value
    with pytest.raises(ValueError):
        verify(row, runtime)


@pytest.mark.parametrize("change", ["operation", "capability", "result", "failed", "signature"])
def test_refuses_wrong_operation_unsigned_shape_and_failed_result(change):
    row, runtime = evidence()
    plan, outcome = row["plan_json"], row["outcome_json"]
    if change == "operation":
        plan["steps"][0]["operation_id"] = "teamcenter.visualization.insert@1"
    elif change == "capability":
        plan["capability_id"] = "simulation.teamcenter.visualization.insert.request"
    elif change == "result":
        outcome["steps"][0]["result"]["source_identity_hash"] = "sha256:" + "0" * 64
    elif change == "failed":
        outcome["overall_status"] = "failed_without_effect"
    else:
        outcome["signature"] = ("A" if outcome["signature"][0] != "A" else "B") + outcome["signature"][1:]
    if change != "signature":
        result = outcome["steps"][0]["result"]
        outcome["steps"][0]["result_hash"] = "sha256:" + hashlib.sha256(canonicalize_v2(result)).hexdigest()
        plan["plan_hash"] = compute_plan_hash(plan)
        row["plan_hash"] = outcome["plan_hash"] = plan["plan_hash"]
        outcome["signature"] = sign_outcome(outcome)
    row["outcome_hash"] = hashlib.sha256(canonicalize_v2(outcome)).hexdigest()
    with pytest.raises(ValueError):
        verify(row, runtime)

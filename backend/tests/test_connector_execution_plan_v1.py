from __future__ import annotations

from copy import deepcopy
import importlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError


VECTOR = json.loads(
    (Path(__file__).with_name("fixtures") / "connector_execution_plan_v1.json").read_text(encoding="utf-8")
)


def _contracts():
    return importlib.import_module("backend.contracts.connector_execution_plan_v1")


def test_plan_hash_matches_checked_in_cross_language_vector():
    contracts = _contracts()
    plan = contracts.ConnectorExecutionPlanV1.model_validate(VECTOR["plan"])

    assert plan.plan_hash == VECTOR["plan_hash"]
    assert plan.compute_hash() == "sha256:d364d115e2ff3827befdc5ed8d4ab536de05a5e4e335ea23370464f33369531c"


def test_plan_rejects_duplicate_step_ids():
    contracts = _contracts()
    value = deepcopy(VECTOR["plan"])
    value["steps"].append(deepcopy(value["steps"][0]))
    value["plan_hash"] = contracts.canonical_hash({key: item for key, item in value.items() if key != "plan_hash"})

    with pytest.raises(ValidationError, match="duplicate_step_id"):
        contracts.ConnectorExecutionPlanV1.model_validate(value)


def test_plan_rejects_forward_and_missing_dependencies():
    contracts = _contracts()
    value = deepcopy(VECTOR["plan"])
    value["steps"][0]["depends_on"] = ["step-later"]
    value["plan_hash"] = contracts.canonical_hash({key: item for key, item in value.items() if key != "plan_hash"})

    with pytest.raises(ValidationError, match="invalid_step_dependency"):
        contracts.ConnectorExecutionPlanV1.model_validate(value)


def test_plan_rejects_payload_and_plan_hash_tampering():
    contracts = _contracts()
    payload_tampered = deepcopy(VECTOR["plan"])
    payload_tampered["steps"][0]["payload"] = {"unexpected": True}
    with pytest.raises(ValidationError, match="payload_hash_mismatch"):
        contracts.ConnectorExecutionPlanV1.model_validate(payload_tampered)

    plan_tampered = deepcopy(VECTOR["plan"])
    plan_tampered["device_id"] = "device-other"
    with pytest.raises(ValidationError, match="plan_hash_mismatch"):
        contracts.ConnectorExecutionPlanV1.model_validate(plan_tampered)


def test_plan_requires_aware_increasing_timestamps():
    contracts = _contracts()
    naive = deepcopy(VECTOR["plan"])
    naive["issued_at"] = "2026-09-03T00:00:00"
    naive["plan_hash"] = contracts.canonical_hash({key: item for key, item in naive.items() if key != "plan_hash"})
    with pytest.raises(ValidationError, match="plan timestamps must be timezone-aware"):
        contracts.ConnectorExecutionPlanV1.model_validate(naive)

    reversed_time = deepcopy(VECTOR["plan"])
    reversed_time["expires_at"] = "2026-09-02T23:59:59Z"
    reversed_time["plan_hash"] = contracts.canonical_hash({key: item for key, item in reversed_time.items() if key != "plan_hash"})
    with pytest.raises(ValidationError, match="plan must expire after it is issued"):
        contracts.ConnectorExecutionPlanV1.model_validate(reversed_time)


def test_completed_step_requires_exact_result_hash_and_no_error():
    contracts = _contracts()
    value = {
        "step_id": "step-1", "status": "completed", "result": {"connected": True},
        "result_hash": "sha256:5588d7b359436afbb86c38afcbf0bb45350bf00e0fe608978558df3286956f6e",
        "error_code": "", "started_at": "2026-09-03T00:00:01Z", "completed_at": "2026-09-03T00:00:02Z",
    }
    result = contracts.ConnectorStepResultV1.model_validate(value)
    assert result.status == "completed"

    with pytest.raises(ValidationError, match="result_hash_mismatch"):
        contracts.ConnectorStepResultV1.model_validate({**value, "result": {"connected": False}})


def test_failed_or_unknown_step_requires_stable_error_code():
    contracts = _contracts()
    value = {
        "step_id": "step-1", "status": "outcome_unknown", "result": None,
        "result_hash": None, "error_code": "", "started_at": "2026-09-03T00:00:01Z",
        "completed_at": "2026-09-03T00:00:02Z",
    }
    with pytest.raises(ValidationError, match="error_code_required"):
        contracts.ConnectorStepResultV1.model_validate(value)


def test_plan_outcome_requires_aware_report_time():
    contracts = _contracts()
    with pytest.raises(ValidationError, match="plan outcome timestamp must be timezone-aware"):
        contracts.ConnectorPlanOutcomeV1.model_validate({
            "protocol": "ai00.connector.execution-plan.v1", "plan_id": "plan-001",
            "status": "cancelled", "steps": [], "reported_at": "2026-09-03T00:00:02",
        })

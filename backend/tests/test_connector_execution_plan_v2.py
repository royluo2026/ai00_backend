from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.contracts.connector_execution_plan_v2 import (
    ConnectorExecutionPlanV2,
    ConnectorPlanOutcomeV2,
    canonicalize_v2,
    compute_plan_hash,
    plan_signature_bytes,
    verify_outcome_signature,
    verify_plan_signature,
)


VECTOR_PATH = Path(__file__).with_name("fixtures") / "connector_execution_plan_v2.json"


@pytest.fixture(scope="module")
def vector() -> dict:
    return json.loads(VECTOR_PATH.read_text(encoding="utf-8"))


def test_plan_hash_excludes_hash_and_signature_but_signature_includes_hash(vector):
    raw = vector["plan"]
    plan = ConnectorExecutionPlanV2.model_validate(raw)

    assert plan.compute_hash() == raw["plan_hash"]
    assert compute_plan_hash(raw) == raw["plan_hash"]
    assert verify_plan_signature(plan, vector["plan_public_jwk"]) is True
    assert plan.verify_signature(vector["plan_public_jwk"]) is True
    assert canonicalize_v2({
        key: value for key, value in raw.items() if key not in {"plan_hash", "signature"}
    }).hex() == vector["canonical_plan_without_hash_or_signature_hex"]
    assert plan_signature_bytes(raw).hex() == vector["canonical_plan_without_signature_hex"]

    changed_metadata = {**raw, "plan_hash": "0" * 64, "signature": "changed"}
    assert compute_plan_hash(changed_metadata) == raw["plan_hash"]
    assert plan_signature_bytes(changed_metadata) != plan_signature_bytes(raw)


def test_outcome_matches_checked_in_device_signature(vector):
    outcome = ConnectorPlanOutcomeV2.model_validate(vector["outcome"])

    assert verify_outcome_signature(outcome, vector["device_public_jwk"]) is True
    assert outcome.verify_signature(vector["device_public_jwk"]) is True


@pytest.mark.parametrize("record_name", ["plan", "outcome"])
def test_v2_records_are_closed_and_every_field_is_required(vector, record_name):
    model = ConnectorExecutionPlanV2 if record_name == "plan" else ConnectorPlanOutcomeV2
    raw = vector[record_name]

    for field in raw:
        with pytest.raises(ValidationError):
            model.model_validate({key: value for key, value in raw.items() if key != field})

    with pytest.raises(ValidationError, match="extra_forbidden"):
        model.model_validate({**raw, "unknown": True})


def test_v2_rejects_timestamp_coercion_and_non_json_numbers(vector):
    with pytest.raises(ValidationError):
        ConnectorExecutionPlanV2.model_validate({
            **vector["plan"],
            "issued_at": datetime(2026, 9, 7, tzinfo=timezone.utc),
        })

    with pytest.raises(ValidationError, match="json_finite_number_required"):
        ConnectorExecutionPlanV2.model_validate({
            **vector["plan"],
            "steps": [{**vector["plan"]["steps"][0], "payload": {"scale": float("nan")}}],
        })

    with pytest.raises(ValidationError, match="json_value_required"):
        ConnectorExecutionPlanV2.model_validate({
            **vector["plan"],
            "steps": [{**vector["plan"]["steps"][0], "payload": (1, 2)}],
        })


def test_canonicalization_uses_utf16_property_order():
    assert canonicalize_v2({"\ue000": 1, "\U00010000": 2}) == '{"\U00010000":2,"\ue000":1}'.encode()


def test_canonicalization_uses_rfc8785_number_serialization():
    assert canonicalize_v2({
        "numbers": [333333333.33333329, 1e30, 4.50, 2e-3, 1e-27, -0.0]
    }) == b'{"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27,0]}'


@pytest.mark.parametrize("case", ["mutation", "der", "high_s", "padding", "downgrade", "unknown_field"])
def test_checked_in_rejection_vectors_fail_closed(vector, case):
    rejected = vector["rejection_cases"][case]
    model = ConnectorExecutionPlanV2 if rejected["record"] == "plan" else ConnectorPlanOutcomeV2
    value = deepcopy(vector[rejected["record"]])
    value[rejected["field"]] = rejected["value"]

    with pytest.raises(ValidationError):
        model.model_validate(value)


def test_plan_verifier_rejects_wrong_curve_and_private_jwk_members(vector):
    plan = ConnectorExecutionPlanV2.model_validate(vector["plan"])

    assert verify_plan_signature(plan, {**vector["plan_public_jwk"], "crv": "P-384"}) is False
    assert verify_plan_signature(plan, {**vector["plan_public_jwk"], "d": "private"}) is False
    outcome = ConnectorPlanOutcomeV2.model_validate(vector["outcome"])
    assert verify_plan_signature(outcome, vector["device_public_jwk"]) is False

    with pytest.raises(ValidationError):
        ConnectorExecutionPlanV2.model_validate({**vector["plan"], "signature": "a"})


def test_outcome_requires_at_least_one_ordered_step_result(vector):
    with pytest.raises(ValidationError):
        ConnectorPlanOutcomeV2.model_validate({**vector["outcome"], "steps": []})


def test_fixture_private_material_is_unmistakably_test_only(vector):
    fixture_keys = vector["test_only_private_keys"]

    assert fixture_keys["marker"] == "TEST_VECTOR_PRIVATE_KEY_DO_NOT_USE"
    assert "d" not in vector["plan_public_jwk"]
    assert "d" not in vector["device_public_jwk"]


def test_mutating_any_signed_top_level_plan_binding_is_rejected(vector):
    raw = vector["plan"]
    unsigned_metadata = {"plan_hash", "signature"}

    for field in raw.keys() - unsigned_metadata:
        mutated = deepcopy(raw)
        original = mutated[field]
        if original is None:
            mutated[field] = "changed"
        elif isinstance(original, str):
            mutated[field] = original + "x"
        elif isinstance(original, int):
            mutated[field] = original + 1
        elif isinstance(original, list):
            mutated[field] = []
        else:
            mutated[field] = None
        with pytest.raises(ValidationError):
            ConnectorExecutionPlanV2.model_validate(mutated)

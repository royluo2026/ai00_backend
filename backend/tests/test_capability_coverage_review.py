"""Contract tests for per-domain capability coverage review documents."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "docs" / "governance" / "capability-coverage-review.schema.json"
FIXTURE_DIR = ROOT / "backend" / "tests" / "fixtures" / "capability_coverage_review"


@pytest.fixture
def review_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def fixture():
    def load(name: str) -> dict:
        return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))

    return load


def test_minimal_domain_review_is_closed_and_valid(review_schema, fixture):
    """Catches a valid document becoming invalid or accepting unknown root fields."""
    document = fixture("minimal-valid.json")
    jsonschema.Draft202012Validator(review_schema).validate(document)

    document["unexpected"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(review_schema).validate(document)


def test_generic_exclusion_is_rejected(review_schema, fixture):
    """Catches an excluded function without source evidence or a specific reason."""
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(review_schema).validate(
            fixture("invalid-generic-exclusion.json")
        )


def test_consumer_specific_duplicate_implementation_is_rejected(review_schema, fixture):
    """Catches a consumer-specific delivery pipeline instead of the shared pipeline."""
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(review_schema).validate(
            fixture("invalid-consumer-duplicate.json")
        )


def test_exclusion_without_a_domain_owner_is_rejected(review_schema, fixture):
    """Catches an otherwise evidenced exclusion that omits its accountable owner."""
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(review_schema).validate(
            fixture("invalid-exclusion-missing-owner.json")
        )


def test_new_capability_cannot_reference_a_dangling_candidate_id(review_schema, fixture):
    """Catches a new-capability disposition detached from its candidate record."""
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(review_schema).validate(
            fixture("invalid-dangling-candidate-id.json")
        )


def test_candidate_cannot_reference_a_mismatched_exposure_id(review_schema, fixture):
    """Catches candidate delivery evidence detached from its shared exposure record."""
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(review_schema).validate(
            fixture("invalid-mismatched-exposure-id.json")
        )


def test_generic_exclusion_reason_is_rejected_independently(review_schema, fixture):
    """Catches a generic exclusion reason even when all other exclusion evidence is valid."""
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(review_schema).validate(
            fixture("invalid-generic-exclusion-reason.json")
        )

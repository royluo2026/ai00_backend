"""Contract tests for normalized per-domain capability coverage reviews."""
from __future__ import annotations

import json
import importlib.util
import os
from pathlib import Path

import jsonschema
import pytest


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "docs" / "governance" / "capability-coverage-review.schema.json"
FIXTURE_DIR = ROOT / "backend" / "tests" / "fixtures" / "capability_coverage_review"
BUILDER_PATH = ROOT / "backend" / "scripts" / "build_capability_coverage_review.py"


@pytest.fixture
def review_schema() -> dict:
    schema_path = Path(os.environ.get("CAPABILITY_COVERAGE_SCHEMA_PATH", SCHEMA_PATH))
    return json.loads(schema_path.read_text(encoding="utf-8"))


@pytest.fixture
def fixture():
    def load(name: str) -> dict:
        return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))

    return load


@pytest.fixture
def builder():
    spec = importlib.util.spec_from_file_location("build_capability_coverage_review", BUILDER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _validate(schema: dict, document: dict) -> None:
    jsonschema.Draft202012Validator(schema).validate(document)


def test_minimal_domain_review_is_closed_and_valid(review_schema, fixture):
    """Proves one normalized document can contain both existing and candidate groups."""
    document = fixture("minimal-valid.json")
    _validate(review_schema, document)

    document["unexpected"] = True
    with pytest.raises(jsonschema.ValidationError):
        _validate(review_schema, document)


def test_generic_exclusion_is_rejected(review_schema, fixture):
    """Catches an otherwise valid exclusion with a generic review reason."""
    with pytest.raises(jsonschema.ValidationError):
        _validate(review_schema, fixture("invalid-generic-exclusion.json"))


def test_consumer_specific_duplicate_implementation_is_rejected(review_schema, fixture):
    """Catches a consumer-specific pipeline in an otherwise valid candidate group."""
    with pytest.raises(jsonschema.ValidationError):
        _validate(review_schema, fixture("invalid-consumer-duplicate.json"))


def test_candidate_with_wrong_nested_resolution_is_rejected(review_schema, fixture):
    """Catches an existing-capability row inside a candidate Capability group."""
    document = fixture("minimal-valid.json")
    document["capabilities"]["project.project.create"]["function_dispositions"][
        "rest:POST:/api/projects"
    ]["resolution"] = "existing_capability"

    with pytest.raises(jsonschema.ValidationError):
        _validate(review_schema, document)


def test_existing_group_with_candidate_definition_is_rejected(review_schema, fixture):
    """Catches a candidate definition attached to an existing Catalog Capability group."""
    document = fixture("minimal-valid.json")
    document["capabilities"]["project.project.list"]["candidate_definition"] = {
        "business_outcome": "Must not be attached to an existing Capability.",
        "non_goals": ["No-op"],
        "owner_domain": "project_management",
        "application_port": "project_management.list_projects",
        "provider_artifact": "official.project-management",
        "owned_tables": ["projects"],
        "migration_stream": "project_management"
    }

    with pytest.raises(jsonschema.ValidationError):
        _validate(review_schema, document)


def test_candidate_without_definition_is_rejected(review_schema, fixture):
    """Catches a candidate group that lacks its required inline candidate definition."""
    document = fixture("minimal-valid.json")
    del document["capabilities"]["project.project.create"]["candidate_definition"]

    with pytest.raises(jsonschema.ValidationError):
        _validate(review_schema, document)


def test_capability_group_requires_function_dispositions(review_schema, fixture):
    """Catches removal of the non-empty map that binds functions to the sole Capability ID."""
    document = fixture("minimal-valid.json")
    document["capabilities"]["project.project.create"]["function_dispositions"].clear()

    with pytest.raises(jsonschema.ValidationError):
        _validate(review_schema, document)


def test_free_candidate_id_and_duplicate_exposure_map_are_rejected(review_schema, fixture):
    """Catches reintroduced sibling Capability identity or exposure data."""
    document = fixture("minimal-valid.json")
    document["capabilities"]["project.project.create"]["candidate_id"] = "project.project.other"
    with pytest.raises(jsonschema.ValidationError):
        _validate(review_schema, document)

    document = fixture("minimal-valid.json")
    document["consumer_exposures"] = {"project.project.create": {}}
    with pytest.raises(jsonschema.ValidationError):
        _validate(review_schema, document)


def test_draft_unreviewed_function_does_not_forge_review_approval(review_schema, fixture):
    """Catches a schema that forces scanner-discovered rows to invent reviewer metadata."""
    document = fixture("minimal-valid.json")
    document["unreviewed_functions"]["rest:GET:/api/new-route"] = {
        "resolution": "unreviewed",
        "source_paths": ["backend/routers/new_route.py"],
        "owner": "project-management-owner",
        "evidence": "Discovered from the stable FastAPI route decorator."
    }

    _validate(review_schema, document)

    document["review"]["status"] = "approved"
    with pytest.raises(jsonschema.ValidationError):
        _validate(review_schema, document)


def test_merge_preserves_reviewed_dispositions_and_adds_new_candidates(builder, fixture):
    reviewed = fixture("minimal-valid.json")
    discovered = [
        {
            "function_id": "rest:GET:/api/projects",
            "domain": "Project Management",
            "source_paths": ["backend/routers/projects.py"],
        },
        {
            "function_id": "rest:GET:/api/new-route",
            "domain": "Project Management",
            "source_paths": ["backend/routers/new_route.py"],
        },
    ]

    merged = builder.merge_domain_review(reviewed, discovered)

    assert merged["capabilities"]["project.project.list"]["function_dispositions"][
        "rest:GET:/api/projects"
    ]["resolution"] == "existing_capability"
    assert merged["unreviewed_functions"]["rest:GET:/api/new-route"]["resolution"] == "unreviewed"


def test_generated_views_are_order_independent(builder, fixture):
    project = fixture("minimal-valid.json")
    base = fixture("minimal-valid.json")
    base["domain"] = "Base Platform"

    assert builder.render_views([project, base]) == builder.render_views([base, project])

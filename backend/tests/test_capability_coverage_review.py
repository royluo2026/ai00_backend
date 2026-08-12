"""Contract tests for normalized per-domain capability coverage reviews."""
from __future__ import annotations

import json
import importlib.util
import os
import subprocess
import sys
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


def test_merge_drops_a_reviewed_disposition_that_moved_to_another_domain(builder, fixture):
    """Catches the old owner retaining a function after its Registry domain changes."""
    reviewed = fixture("minimal-valid.json")

    merged = builder.merge_domain_review(reviewed, [])

    assert merged["capabilities"] == {}


def test_aligns_reviewed_function_with_its_current_published_capability(builder, fixture):
    """Catches a reviewed transport disposition remaining under a retired Capability ID."""
    document = fixture("minimal-valid.json")
    row = {
        "function_id": "rest:GET:/api/projects",
        "domain": "Project Management",
        "source_paths": ["backend/routers/projects.py"],
        "current_consumers": ["REST"],
        "target_capability": "project.project.create",
    }

    aligned = builder._align_published_function_targets(
        document,
        [row],
        {"project.project.create"},
    )

    assert "project.project.list" not in aligned["capabilities"]
    group = aligned["capabilities"]["project.project.create"]
    assert group["kind"] == "existing"
    assert "candidate_definition" not in group
    assert group["function_dispositions"]["rest:GET:/api/projects"]["resolution"] == (
        "existing_capability"
    )


def test_binds_new_registry_evidence_to_its_published_capability(builder, fixture):
    """Catches mapped Catalog evidence being left in the unreviewed bucket."""
    document = fixture("minimal-valid.json")
    function_id = "capability:project.project.create"
    document["unreviewed_functions"][function_id] = {
        "resolution": "unreviewed",
        "source_paths": ["plugins/project_management/capabilities/projects.py"],
        "owner": "Project Management",
        "evidence": "Discovered from the frozen provider.",
    }
    row = {
        "function_id": function_id,
        "domain": "Project Management",
        "source_paths": ["plugins/project_management/capabilities/projects.py"],
        "current_consumers": ["Capability"],
        "target_capability": "project.project.create",
    }

    aligned = builder._align_published_function_targets(
        document,
        [row],
        {"project.project.create"},
    )

    assert function_id not in aligned["unreviewed_functions"]
    disposition = aligned["capabilities"]["project.project.create"][
        "function_dispositions"
    ][function_id]
    assert disposition["resolution"] == "existing_capability"
    assert disposition["source_paths"] == row["source_paths"]


def test_generated_views_are_order_independent(builder, fixture):
    project = fixture("minimal-valid.json")
    base = fixture("minimal-valid.json")
    base["domain"] = "Base Platform"

    assert builder.render_views([project, base]) == builder.render_views([base, project])


def test_every_baseline_violation_and_table_has_one_generated_review_row(builder):
    sources = builder.load_sources(ROOT)
    documents = builder.initialize_documents(sources, builder._load_documents())
    debt_ids = [row["id"] for document in documents for row in document["debt_dispositions"]]
    expected_debt_ids = {
        builder._module_debt(row)["id"]
        for row in sources.dependency_baseline["violations"]
    } | {
        "boundary:" + row["fingerprint"]
        for row in sources.boundary_baseline["violations"]
    }
    tables = [row["table"] for document in documents for row in document["database_boundaries"]]

    assert set(debt_ids) == expected_debt_ids
    assert len(debt_ids) == len(set(debt_ids))
    assert len(tables) == len(set(tables)) == sources.table_inventory["table_count"]


def test_complete_audit_has_zero_unreviewed_and_consistent_candidates(builder):
    sources = builder.load_sources(ROOT)
    existing = builder._load_documents()
    documents = builder.initialize_documents(sources, existing)
    summary = json.loads(builder.render_evidence_views(builder.render_views(documents), sources)["summary.json"])

    assert builder.audit_consistency_errors(documents, sources) == []
    assert summary["resolutions"]["unreviewed"] == 0
    assert summary["candidate_capabilities"] == sum(
        summary["candidate_additions_by_domain"].values()
    )
    assert summary["proposed_final_catalog_capabilities"] == (
        summary["current_catalog_capabilities"]
        + summary["candidate_capabilities"]
    )


def test_approved_base_integration_correction_is_applied(builder):
    sources = builder.load_sources(ROOT)
    documents = {
        item["domain"]: item
        for item in builder.initialize_documents(
            sources, builder._load_documents()
        )
    }
    base = documents["Base Platform"]["capabilities"]
    integration = documents["Integration"]["capabilities"]
    removed = {
        "base.external_datasource.change.apply",
        "base.external_datasource.connection.test",
        "base.external_datasource.search",
        "base.external_mapping.change.apply",
        "base.external_mapping.read",
        "base.plugin.marketplace.usage.close",
        "plugin.upgrade.finish",
        "system.worker.outbox.health",
    }
    assert removed.isdisjoint(base)

    expected = {
        "rest:POST:/api/ext-datasources": "integration.connector.create",
        "rest:PATCH:/api/ext-datasources/{gid}": "integration.connector.update",
        "rest:DELETE:/api/ext-datasources/{gid}": "integration.connector.archive",
        "rest:POST:/api/ext-datasources/{gid}/test": "integration.connector.connection.test",
        "rest:GET:/api/ext-datasources": "integration.connector.search",
        "rest:GET:/api/ext-datasources/{gid}/tables": "integration.connector.schema.discover",
        "rest:POST:/api/ext-mappings": "integration.mapping.create",
        "rest:PATCH:/api/ext-mappings/{gid}": "integration.mapping.update",
        "rest:DELETE:/api/ext-mappings/{gid}": "integration.mapping.archive",
        "rest:POST:/api/ext-mappings/{gid}/import": "integration.sync.start",
        "rest:PUT:/api/ext-field-mappings/batch": "integration.mapping.update",
        "rest:GET:/api/ext-mappings": "integration.mapping.search",
        "rest:GET:/api/ext-field-mappings": "integration.mapping.get",
        "rest:GET:/api/ext-mappings/{gid}/columns": "integration.connector.schema.discover",
        "rest:GET:/api/ext-mappings/{gid}/preview": "integration.mapping.preview",
    }
    stable_ids = {
        function_id
        for function_id, row in sources.registry["functions"].items()
        if row.get("stability") == "stable"
    }
    expected = {key: value for key, value in expected.items() if key in stable_ids}
    actual = {
        function_id: capability_id
        for capability_id, capability in integration.items()
        for function_id in capability["function_dispositions"]
    }
    assert {key: actual.get(key) for key in expected} == expected


def test_approved_corrections_ignore_functions_retired_from_the_registry(builder):
    """Catches a second generation run failing after corrected REST surfaces retire."""
    reviewed_against = {
        "git_commit": "0" * 40,
        "registry_sha256": "sha256:" + "0" * 64,
        "catalog_release": "test-release",
        "catalog_sha256": "sha256:" + "1" * 64,
    }
    documents = [
        builder._empty_review("Base Platform", reviewed_against),
        builder._empty_review("Integration", reviewed_against),
    ]

    corrected = builder._apply_approved_corrections(documents, set())

    assert all(document["capabilities"] == {} for document in corrected)


def test_strict_stops_at_architecture_threshold_with_exact_counts():
    result = subprocess.run(
        [sys.executable, str(BUILDER_PATH), "--strict"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 3
    payload = json.loads(result.stdout)
    summary = json.loads(
        (ROOT / "docs/governance/capability-coverage-review/generated/summary.json")
        .read_text(encoding="utf-8")
    )
    assert payload == {
        "status": "architecture_review_required",
        "current_catalog_capabilities": summary["current_catalog_capabilities"],
        "candidate_capabilities": summary["candidate_capabilities"],
        "proposed_final_catalog_capabilities": summary[
            "proposed_final_catalog_capabilities"
        ],
        "candidate_additions_by_domain": summary[
            "candidate_additions_by_domain"
        ],
    }

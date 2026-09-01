from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from backend.capability_governance_test.analysis import AnalysisRequest, run_deterministic_analysis
from backend.capability_governance_test.config import GovernanceSettings
from backend.capability_governance_test.fingerprint import snapshot_fingerprint
from backend.capability_governance_test.models import ScannedCapability
from backend.capability_governance_test.scanner import GovernanceScanner
from backend.capability_v2.business_definition import business_definition_hash
from backend.capability_v2.catalog import CatalogRelease, build_release
from backend.capability_v2.contracts import (
    AutomationLevel,
    CapabilityDescriptorV2,
    ExposurePolicy,
)


def _author_release(rules: tuple[dict[str, object], ...]) -> CatalogRelease:
    descriptor = CapabilityDescriptorV2(
        id="person.height.write",
        major_version=1,
        owner_domain="person",
        title="Write person height",
        description="Record a normalized person height.",
        use_when="A caller needs to record height.",
        do_not_use_when="A caller needs another attribute.",
        business_effect="Personnel planning can use one normalized height measurement.",
        business_acceptance_criteria=("The normalized height is persisted.",),
        business_invariants=rules,
        side_effect_level="write",
        side_effects="Stores the normalized height.",
        exposure=ExposurePolicy(api=True),
        automation_level=AutomationLevel.A2,
        authorization_policy="person.height.write",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        output_schema={"type": "object", "properties": {}, "additionalProperties": False},
        schema_hash="sha256:" + "a" * 64,
        provider_ref="person.provider:write_height",
    )
    return build_release((descriptor,), created_at=datetime(2026, 9, 1, tzinfo=UTC))


def _author_rule(rule_id: str = "person.height.valid_range", version: object = 1) -> dict[str, object]:
    return {
        "rule_id": rule_id,
        "version": version,
        "statement": "Height is valid.",
        "applies_when": "Height changes.",
        "enforcement_ref": "person/provider.py:validate_height",
        "error_code": "height_out_of_range",
        "test_refs": ("person/test_height.py::test_accepts_boundary",),
    }


def _scan_author_release(scanner: GovernanceScanner, release: CatalogRelease):
    parsed = CatalogRelease.model_validate_json(release.model_dump_json())
    return GovernanceScanner(
        scanner.settings,
        product_catalog=parsed,
        domain_manifests={"domains": [{"domain_id": "person", "artifact_path": "person"}]},
    ).scan("abc123")


@pytest.fixture
def catalog() -> dict[str, object]:
    return {
        "release_id": "catalog-business-test",
        "descriptors": [{
            "id": "person.height.write",
            "major_version": 1,
            "owner_domain": "person",
            "side_effect_level": "write",
            "lifecycle_status": "experimental",
            "title": "Write height",
            "description": "Technical height write operation.",
            "business_effect": "Personnel planning can use one normalized height measurement.",
            "business_acceptance_criteria": ("The normalized height is persisted.",),
            "business_invariants": (),
            "no_business_invariant_reason": "No additional domain invariant applies.",
            "input_schema": {"type": "object", "properties": {"height": {"type": "number"}}},
            "output_schema": {"type": "object", "properties": {"height": {"type": "number"}}},
            "domain_errors": (),
            "provider_ref": "person.provider:write_height",
            "resource_selectors": ({"resource_type": "person.height", "payload_path": "$.person_gid"},),
            "read_scope": ("person.profile", "person.height"),
            "write_scope": ("person.height",),
        }],
    }


@pytest.fixture
def scanner(tmp_path, catalog) -> GovernanceScanner:
    source_root = tmp_path / "person"
    source_root.mkdir()
    (source_root / "provider.py").write_text(
        "def validate_height():\n    return None\n", encoding="utf-8",
    )
    (source_root / "test_height.py").write_text(
        "def test_accepts_boundary():\n    assert True\n\n"
        "def test_rejects_out_of_range():\n    assert True\n",
        encoding="utf-8",
    )
    return GovernanceScanner(
        GovernanceSettings("test-governance", tmp_path, ("person",)),
        product_catalog=catalog,
        domain_manifests={"domains": [{"domain_id": "person", "artifact_path": "person"}]},
    )


def test_scanner_uses_business_effect_not_description(scanner, catalog):
    catalog["descriptors"][0].update(
        business_effect="Approved outcome", description="Technical text",
    )

    item = scanner.scan("abc123").capabilities[0]

    assert item.business_effect == "Approved outcome"


def test_scanner_marks_generated_effect_as_l1(scanner, catalog):
    descriptor = catalog["descriptors"][0]
    descriptor["business_effect"] = f"Business outcome: {descriptor['description']}"

    item = scanner.scan("abc123").capabilities[0]

    assert item.business_maturity.level == "L1"
    assert "generated_business_effect" in item.business_maturity.reason_codes


def test_scanner_marks_empty_effect_as_missing_l1_evidence(scanner, catalog):
    catalog["descriptors"][0]["business_effect"] = ""

    item = scanner.scan("abc123").capabilities[0]

    assert item.business_effect == ""
    assert item.business_layer_evidence["A"] == (
        "The normalized height is persisted.",
    )
    assert item.business_maturity.level == "L1"
    assert item.business_maturity.reason_codes == ("missing_business_effect",)


def test_scanner_normalizes_fingerprint_order(scanner, catalog):
    descriptor = catalog["descriptors"][0]
    descriptor["business_invariants"] = (
        {
            "rule_id": "person.height.maximum",
            "version": 1,
            "statement": "Height is at most 2.5 metres.",
            "applies_when": "A height is changed.",
            "enforcement_ref": "person.provider:validate_height",
            "error_code": "height_out_of_range",
            "test_refs": ("tests/test_height.py::test_maximum",),
        },
        {
            "rule_id": "person.height.minimum",
            "version": 1,
            "statement": "Height is greater than zero.",
            "applies_when": "A height is changed.",
            "enforcement_ref": "person.provider:validate_height",
            "error_code": "height_out_of_range",
            "test_refs": ("tests/test_height.py::test_minimum",),
        },
    )
    descriptor["no_business_invariant_reason"] = None
    first_document = scanner.scan("abc123")
    first = first_document.capabilities[0].fingerprint

    reordered = deepcopy(catalog)
    reordered["descriptors"][0]["business_invariants"] = tuple(
        reversed(reordered["descriptors"][0]["business_invariants"])
    )
    reordered["descriptors"][0]["read_scope"] = tuple(
        reversed(reordered["descriptors"][0]["read_scope"])
    )
    second_document = GovernanceScanner(
        scanner.settings,
        product_catalog=reordered,
        domain_manifests={"domains": [{"domain_id": "person", "artifact_path": "person"}]},
    ).scan("abc123")
    second = second_document.capabilities[0].fingerprint

    assert first == second
    assert first.business_object == "height"
    assert first.action == "write"
    assert first.rule_ids == ("person.height.maximum", "person.height.minimum")
    assert first.read_scope == ("person.height", "person.profile")
    assert first_document.snapshot_hash == second_document.snapshot_hash


def test_scanner_emits_all_business_layers_and_l3_rule_evidence(scanner, catalog):
    descriptor = catalog["descriptors"][0]
    descriptor["no_business_invariant_reason"] = None
    descriptor["business_invariants"] = ({
        "rule_id": "person.height.valid_range",
        "version": 1,
        "statement": "Height is greater than zero and at most 2.5 metres.",
        "applies_when": "A height is changed.",
        "enforcement_ref": "person/provider.py:validate_height",
        "error_code": "height_out_of_range",
        "test_refs": (
            "person/test_height.py::test_accepts_boundary",
            "person/test_height.py::test_rejects_out_of_range",
        ),
    },)

    item = scanner.scan("abc123").capabilities[0]

    assert tuple(item.business_layer_evidence) == tuple("ABCDEFG")
    assert item.business_maturity.level == "L3"
    assert item.business_rules[0]["rule_id"] == "person.height.valid_range"
    assert item.business_rules[0]["version"] == 1
    assert "rule_version" not in item.business_rules[0]
    assert "person/provider.py:validate_height" in item.business_layer_evidence["D"]
    assert "person/test_height.py::test_rejects_out_of_range" in item.business_layer_evidence["E"]
    assert item.business_maturity.reason_codes == (
        "enforcement_mapping_resolved", "rule_test_evidence_resolved",
    )


def test_scanner_keeps_unresolved_rule_evidence_at_l2(scanner, catalog):
    descriptor = catalog["descriptors"][0]
    descriptor["no_business_invariant_reason"] = None
    descriptor["business_invariants"] = ({
        "rule_id": "person.height.valid_range",
        "version": 1,
        "statement": "Height is within the valid range.",
        "applies_when": "A height is changed.",
        "enforcement_ref": "person/missing.py:validate_height",
        "error_code": "height_out_of_range",
        "test_refs": ("person/test_height.py::test_missing",),
    },)

    item = scanner.scan("abc123").capabilities[0]

    assert item.business_maturity.level == "L2"
    assert item.business_layer_evidence["D"] == ()
    assert item.business_layer_evidence["E"] == ()
    assert item.business_maturity.reason_codes == (
        "enforcement_ref_unresolved", "rule_test_ref_unresolved",
    )


def test_scanner_returns_syntax_error_as_structured_blocking_finding(tmp_path, catalog):
    source_root = tmp_path / "person"
    source_root.mkdir()
    (source_root / "provider.py").write_text("def broken(:\n", encoding="utf-8")
    scanner = GovernanceScanner(
        GovernanceSettings("test-governance", tmp_path, ("person",)),
        product_catalog=catalog,
        domain_manifests={"domains": [{"domain_id": "person", "artifact_path": "person"}]},
    )

    document = scanner.scan("abc123")

    assert document.scan_status == "blocked"
    assert document.scan_findings[0].severity == "blocking"
    assert document.scan_findings[0].category == "parser"
    assert document.scan_findings[0].source_path == "person/provider.py"


def test_scanner_returns_configuration_error_as_structured_report(tmp_path, catalog):
    scanner = GovernanceScanner(
        GovernanceSettings("test-governance", tmp_path, ("person",)),
        product_catalog=catalog,
        domain_manifests=None,
    )

    document = scanner.scan("abc123")
    repeated = scanner.scan("abc123")

    assert document.capabilities == ()
    assert document.scan_status == "blocked"
    assert document.snapshot_hash == repeated.snapshot_hash
    assert snapshot_fingerprint(document) == document.snapshot_hash
    assert document.scan_findings[0].severity == "blocking"
    assert document.scan_findings[0].category == "configuration"
    assert document.scan_findings[0].source_path == "official_domain_manifests"
    analysis = run_deterministic_analysis(document, AnalysisRequest())
    assert analysis.status == "blocked"
    assert analysis.findings[0].code == "scan_configuration_error"


def test_scanner_rejects_invalid_string_evidence_as_structured_configuration(scanner, catalog):
    catalog["descriptors"][0]["business_invariants"] = ({
        "rule_id": "person.height.valid_range", "version": 1,
        "statement": "Height is valid.", "applies_when": "Height changes.",
        "enforcement_ref": "person/provider.py:validate_height",
        "error_code": "height_out_of_range", "test_refs": (42,),
    },)

    document = scanner.scan("abc123")

    assert document.scan_status == "blocked"
    assert document.scan_findings[0].category == "configuration"
    assert document.scan_findings[0].message == "product_catalog_string_list_invalid"


def test_scanner_rejects_duplicate_rule_identity_deterministically(scanner, catalog):
    rule = {
        "rule_id": "person.height.valid_range", "version": 1,
        "statement": "Height is valid.", "applies_when": "Height changes.",
        "enforcement_ref": "person/provider.py:validate_height",
        "error_code": "height_out_of_range",
        "test_refs": ("person/test_height.py::test_accepts_boundary",),
    }
    catalog["descriptors"][0]["business_invariants"] = (rule, {**rule, "statement": "Different"})

    first = scanner.scan("abc123")
    catalog["descriptors"][0]["business_invariants"] = tuple(
        reversed(catalog["descriptors"][0]["business_invariants"])
    )
    second = scanner.scan("abc123")

    assert first.scan_status == "blocked"
    assert first.scan_findings[0].message == "product_catalog_business_rule_duplicate"
    assert first.snapshot_hash == second.snapshot_hash


@pytest.mark.parametrize(("field_name", "invalid_value"), (
    ("rule_id", 1),
    ("version", True),
    ("statement", 1),
    ("applies_when", True),
    ("enforcement_ref", 1),
    ("error_code", True),
))
def test_scanner_rejects_business_rule_scalar_type_coercion(
    scanner, catalog, field_name, invalid_value,
):
    rule = {
        "rule_id": "person.height.valid_range", "version": 1,
        "statement": "Height is valid.", "applies_when": "Height changes.",
        "enforcement_ref": "person/provider.py:validate_height",
        "error_code": "height_out_of_range",
        "test_refs": ("person/test_height.py::test_accepts_boundary",),
    }
    catalog["descriptors"][0]["business_invariants"] = ({**rule, field_name: invalid_value},)

    document = scanner.scan("abc123")

    assert document.scan_status == "blocked"
    assert document.scan_findings[0].message == "product_catalog_business_rule_scalar_invalid"


def test_invalid_rule_scalar_order_has_one_deterministic_identity(scanner, catalog):
    rules = (
        {
            "rule_id": 1, "version": 1, "statement": "One.",
            "applies_when": "Always.", "enforcement_ref": "person/provider.py:validate_height",
            "error_code": "one", "test_refs": (),
        },
        {
            "rule_id": "person.height.two", "version": True, "statement": "Two.",
            "applies_when": "Always.", "enforcement_ref": "person/provider.py:validate_height",
            "error_code": "two", "test_refs": (),
        },
    )
    catalog["descriptors"][0]["business_invariants"] = rules
    first = scanner.scan("abc123")
    catalog["descriptors"][0]["business_invariants"] = tuple(reversed(rules))
    second = scanner.scan("abc123")

    assert first.scan_status == second.scan_status == "blocked"
    assert first.snapshot_hash == second.snapshot_hash
    assert first.scan_findings == second.scan_findings


def test_scanner_rejects_persistence_rule_version_alias_at_author_boundary(scanner, catalog):
    catalog["descriptors"][0]["business_invariants"] = ({
        "rule_id": "person.height.valid_range", "rule_version": 1,
        "statement": "Height is valid.", "applies_when": "Height changes.",
        "enforcement_ref": "person/provider.py:validate_height",
        "error_code": "height_out_of_range",
        "test_refs": ("person/test_height.py::test_accepts_boundary",),
    },)

    document = scanner.scan("abc123")

    assert document.scan_status == "blocked"
    assert document.scan_findings[0].message == "product_catalog_business_rule_scalar_invalid"


@pytest.mark.parametrize("invalid_version", (True, "1"))
def test_catalog_release_rejects_coerced_author_rule_version_before_scanning(scanner, invalid_version):
    release = _author_release((_author_rule(),))
    document = json.loads(release.model_dump_json())
    document["descriptors"][0]["business_invariants"][0]["version"] = invalid_version

    with pytest.raises(ValidationError):
        CatalogRelease.model_validate_json(json.dumps(document))


def test_catalog_release_accepts_integer_version_and_rejects_rule_version_alias(scanner):
    release = _author_release((_author_rule(version=1),))

    scanned = _scan_author_release(scanner, release)

    assert scanned.scan_status == "completed"
    assert scanned.capabilities[0].business_rules[0]["version"] == 1
    document = json.loads(release.model_dump_json())
    rule = document["descriptors"][0]["business_invariants"][0]
    rule["rule_version"] = rule.pop("version")
    with pytest.raises(ValidationError):
        CatalogRelease.model_validate_json(json.dumps(document))


def test_catalog_release_preserves_explicit_machine_rule_range_for_formal_relation_analysis(scanner):
    rule = _author_rule()
    rule["machine_constraints"] = {"field": "height", "unit": "m", "maximum": 2.5}

    scanned = _scan_author_release(scanner, _author_release((rule,)))

    assert scanned.capabilities[0].business_rules[0]["machine_constraints"] == {
        "field": "height", "unit": "m", "minimum": None, "maximum": 2.5,
        "minimum_inclusive": True, "maximum_inclusive": True,
    }


def test_catalog_release_rule_version_changes_hash_but_shuffle_does_not(scanner):
    release_one = _author_release((_author_rule(version=1),))
    release_two = _author_release((_author_rule(version=2),))
    version_one = _scan_author_release(scanner, release_one)
    version_two = _scan_author_release(scanner, release_two)
    rules = (
        _author_rule("person.height.minimum", 1),
        _author_rule("person.height.maximum", 1),
    )
    forward = _scan_author_release(scanner, _author_release(rules))
    reverse = _scan_author_release(scanner, _author_release(tuple(reversed(rules))))

    assert version_one.capabilities[0].descriptor_hash != version_two.capabilities[0].descriptor_hash
    assert business_definition_hash(release_one.descriptors[0]) != business_definition_hash(release_two.descriptors[0])
    assert forward.capabilities[0].descriptor_hash == reverse.capabilities[0].descriptor_hash


def test_scanned_capability_preserves_legacy_positional_descriptor_contract():
    descriptor = {"business_object": "height"}

    item = ScannedCapability(
        "person.height.write", 1, "person", "write", "effect", "stable",
        *("sha256:" + character * 64 for character in "abcdef"),
        descriptor,
    )

    assert item.descriptor["business_object"] == "height"
    assert item.business_rules == ()

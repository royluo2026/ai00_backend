from __future__ import annotations

from copy import deepcopy

import pytest

from backend.capability_governance_test.config import GovernanceSettings
from backend.capability_governance_test.scanner import GovernanceScanner


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
        "def write_height_provider():\n    return None\n", encoding="utf-8",
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
            "rule_version": 1,
            "statement": "Height is at most 2.5 metres.",
            "applies_when": "A height is changed.",
            "enforcement_ref": "person.provider:validate_height",
            "error_code": "height_out_of_range",
            "test_refs": ("tests/test_height.py::test_maximum",),
        },
        {
            "rule_id": "person.height.minimum",
            "rule_version": 1,
            "statement": "Height is greater than zero.",
            "applies_when": "A height is changed.",
            "enforcement_ref": "person.provider:validate_height",
            "error_code": "height_out_of_range",
            "test_refs": ("tests/test_height.py::test_minimum",),
        },
    )
    descriptor["no_business_invariant_reason"] = None
    first = scanner.scan("abc123").capabilities[0].fingerprint

    reordered = deepcopy(catalog)
    reordered["descriptors"][0]["business_invariants"] = tuple(
        reversed(reordered["descriptors"][0]["business_invariants"])
    )
    reordered["descriptors"][0]["read_scope"] = tuple(
        reversed(reordered["descriptors"][0]["read_scope"])
    )
    second = GovernanceScanner(
        scanner.settings,
        product_catalog=reordered,
        domain_manifests={"domains": [{"domain_id": "person", "artifact_path": "person"}]},
    ).scan("abc123").capabilities[0].fingerprint

    assert first == second
    assert first.business_object == "height"
    assert first.action == "write"
    assert first.rule_ids == ("person.height.maximum", "person.height.minimum")
    assert first.read_scope == ("person.height", "person.profile")


def test_scanner_emits_all_business_layers_and_l3_rule_evidence(scanner, catalog):
    descriptor = catalog["descriptors"][0]
    descriptor["no_business_invariant_reason"] = None
    descriptor["business_invariants"] = ({
        "rule_id": "person.height.valid_range",
        "rule_version": 1,
        "statement": "Height is greater than zero and at most 2.5 metres.",
        "applies_when": "A height is changed.",
        "enforcement_ref": "person.provider:validate_height",
        "error_code": "height_out_of_range",
        "test_refs": (
            "tests/test_height.py::test_accepts_boundary",
            "tests/test_height.py::test_rejects_out_of_range",
        ),
    },)

    item = scanner.scan("abc123").capabilities[0]

    assert tuple(item.business_layer_evidence) == tuple("ABCDEFG")
    assert item.business_maturity.level == "L3"
    assert item.business_rules[0]["rule_id"] == "person.height.valid_range"
    assert "person.provider:validate_height" in item.business_layer_evidence["D"]
    assert "tests/test_height.py::test_rejects_out_of_range" in item.business_layer_evidence["E"]


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

    assert document.capabilities == ()
    assert document.scan_findings[0].severity == "blocking"
    assert document.scan_findings[0].category == "configuration"
    assert document.scan_findings[0].source_path == "official_domain_manifests"

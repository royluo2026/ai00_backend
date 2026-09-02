from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.capability_v2.catalog_audit import (
    CatalogAuditConfigurationError,
    audit_catalog,
    audit_catalog_entries,
)


def test_audit_catalog_reports_generic_open_and_default_all_descriptors(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "capabilities": [
                    {
                        "id": "project.change.apply",
                        "lifecycle_status": "stable",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "operation": {"type": "string"},
                                "arguments": {"type": "object", "additionalProperties": True},
                            },
                        },
                        "exposure": {
                            "web": True,
                            "api": True,
                            "plugin": True,
                            "agent": True,
                            "mcp": True,
                        },
                        "exposure_policy_source": "adapter_default",
                    },
                    {
                        "id": "base.read",
                        "lifecycle_status": "stable",
                        "input_schema": {"type": "object", "additionalProperties": False},
                        "exposure": {"web": True, "api": False, "plugin": False, "agent": True, "mcp": False},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    report = audit_catalog(catalog)

    assert report.stable_count == 2
    assert report.generic_operation_count == 1
    assert report.open_arguments_count == 1
    assert report.default_all_exposure_count == 1
    assert report.generic_operation_ids == ("project.change.apply",)


def test_generated_business_effect_is_reported_not_silently_accepted() -> None:
    entry = {
        "id": "person.height.write",
        "lifecycle_status": "stable",
        "description": "Record a normalized person height.",
        "business_effect": "Business outcome: Record a normalized person height.",
    }

    report = audit_catalog_entries([entry])

    assert report.generated_business_effect_count == 1


def test_missing_business_rule_declaration_is_reported() -> None:
    report = audit_catalog_entries([{
        "id": "person.height.write",
        "lifecycle_status": "stable",
        "no_business_invariant_reason": "",
    }])

    assert report.missing_business_rule_declaration_count == 1


def test_audit_catalog_reports_missing_v21_fields_and_unrun_test_evidence(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps({
            "capabilities": [{
                "id": "craft.read",
                "lifecycle_status": "stable",
                "input_schema": {"type": "object", "additionalProperties": False},
                "exposure": {"web": True},
                "capability_version_gid": None,
                "error_schema": [],
                "transaction_policy": {},
                "consumer_refs": [],
                "provider_ref": None,
                "api_refs": [],
                "test_refs": [{"path": "tests/test_craft.py", "result": "not_run"}],
                "business_effect": None,
                "side_effects": None,
            }]
        }),
        encoding="utf-8",
    )

    report = audit_catalog(catalog)

    assert report.required_field_missing_counts["capability_version_gid"] == 1
    assert report.required_field_missing_counts["error_schema"] == 1
    assert report.required_field_missing_counts["provider_ref"] == 1
    assert report.required_field_missing_counts["business_effect"] == 1
    assert report.test_evidence_not_run_count == 1
    assert report.invalid_test_ref_count == 1


def test_audit_catalog_fails_closed_for_missing_catalog(tmp_path: Path) -> None:
    with pytest.raises(CatalogAuditConfigurationError, match="missing catalog"):
        audit_catalog(tmp_path / "missing.json")


def test_audit_catalog_accepts_all_exposure_only_when_provider_explicit(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "capabilities": [
                    {
                        "id": "craft.read",
                        "lifecycle_status": "stable",
                        "input_schema": {"type": "object", "additionalProperties": False},
                        "exposure": {
                            "web": True,
                            "api": True,
                            "plugin": True,
                            "agent": True,
                            "mcp": True,
                        },
                        "exposure_policy_source": "provider_explicit",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert audit_catalog(catalog).default_all_exposure_count == 0


def test_audit_catalog_rejects_exposure_placeholder_and_description_fallback(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"capabilities": [{
        "id": "craft.read", "lifecycle_status": "stable",
        "title": "craft.read", "description": "Read craft data",
        "business_effect": "Read craft data",
        "side_effects": "Reads domain state without mutation.",
        "consumer_refs": ["exposure:web"],
        "exposure": {"web": True},
    }]}), encoding="utf-8")

    report = audit_catalog(catalog)

    assert report.invalid_consumer_ref_count == 1
    assert report.invalid_business_effect_count == 1
    assert report.invalid_side_effect_count == 1


def test_audit_catalog_accepts_explicit_no_consumer_reason(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"capabilities": [{
        "id": "craft.read", "lifecycle_status": "stable",
        "title": "craft.read", "description": "Read craft data",
        "business_effect": "A craft operator can inspect the current craft record.",
        "side_effects": "Reads workmanship_craft_records and emits no mutation event.",
        "consumer_refs": [],
        "no_consumer_reason": "No verified consumer is registered for this provider-only capability.",
        "exposure": {"web": True},
    }]}), encoding="utf-8"),

    report = audit_catalog(catalog)

    assert report.invalid_consumer_ref_count == 0
    assert report.invalid_business_effect_count == 0
    assert report.invalid_side_effect_count == 0


def test_audit_catalog_detects_known_multi_operation_ebom_descriptor_without_arguments_wrapper(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"capabilities": [{
        "id": "craft.ebom.change.apply", "lifecycle_status": "stable",
        "input_schema": {"type": "object", "properties": {
            "operation": {"type": "string", "enum": ["snapshot.delete", "part.add"]}
        }},
    }]}), encoding="utf-8")

    report = audit_catalog(catalog)

    assert report.generic_operation_ids == ("craft.ebom.change.apply",)


def test_audit_catalog_counts_failed_test_evidence(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"capabilities": [{
        "id": "craft.read",
        "lifecycle_status": "stable",
        "input_schema": {"type": "object", "additionalProperties": False},
        "test_refs": [{
            "test_type": "contract",
            "test_node_id": "backend/tests/test_craft.py::test_read",
            "code_revision": "sha256:" + "a" * 64,
            "result": "fail",
        }],
    }]}), encoding="utf-8")

    assert audit_catalog(catalog).test_evidence_failed_count == 1


def test_audit_catalog_rejects_self_attested_test_result(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"capabilities": [{
        "id": "craft.read",
        "lifecycle_status": "stable",
        "input_schema": {"type": "object", "additionalProperties": False},
        "test_refs": [{
            "test_type": "contract",
            "test_node_id": "backend/tests/test_craft.py::test_read[craft.read@1]",
            "code_revision": "sha256:" + "a" * 64,
            "result": "pass",
        }],
    }]}), encoding="utf-8")

    assert audit_catalog(catalog).self_attested_test_result_count == 1


def test_audit_catalog_accepts_test_coverage_declaration_without_result(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"capabilities": [{
        "id": "craft.read",
        "lifecycle_status": "stable",
        "input_schema": {"type": "object", "additionalProperties": False},
        "test_refs": [{
            "test_type": "contract",
            "test_node_id": "backend/tests/test_craft.py::test_read[craft.read@1]",
            "code_revision": "sha256:" + "a" * 64,
        }],
    }]}), encoding="utf-8")

    report = audit_catalog(catalog)

    assert report.invalid_test_ref_count == 0
    assert report.test_evidence_not_run_count == 0
    assert report.test_evidence_failed_count == 0

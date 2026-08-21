from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.capability_v2.catalog_audit import CatalogAuditConfigurationError, audit_catalog


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

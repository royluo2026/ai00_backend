from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from backend.capability_v2.atomicity import audit_generic_operations, load_atomicity_dispositions


def _catalog(*ids: str) -> dict:
    return {
        "capabilities": [
            {
                "id": capability_id,
                "major_version": 1,
                "lifecycle_status": "stable",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "operation": {"type": "string"},
                        "arguments": {"type": "object", "additionalProperties": False},
                    },
                },
            }
            for capability_id in ids
        ]
    }


def test_atomicity_audit_accepts_split_disposition_with_existing_replacements(tmp_path: Path) -> None:
    disposition_path = tmp_path / "dispositions.json"
    disposition_path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "dispositions": [
                    {
                        "capability_id": "project.change.apply",
                        "major_version": 1,
                        "disposition": "split",
                        "replacement_capabilities": ["project.task.create"],
                        "evidence_refs": ["backend/tests/test_project.py"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    catalog = _catalog("project.change.apply")
    catalog["capabilities"].append({
        "id": "project.task.create", "major_version": 1, "lifecycle_status": "stable",
        "input_schema": {"type": "object", "additionalProperties": False},
    })
    report = audit_generic_operations(
        catalog,
        load_atomicity_dispositions(disposition_path),
    )

    assert report.unclassified_ids == ()
    assert report.invalid_ids == ()
    assert report.expired_ids == ()
    assert report.missing_replacement_ids == ()
    assert report.passed is True


def test_atomicity_audit_fails_expired_justification_and_missing_replacement(tmp_path: Path) -> None:
    disposition_path = tmp_path / "dispositions.json"
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    disposition_path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "dispositions": [
                    {
                        "capability_id": "project.change.apply",
                        "major_version": 1,
                        "disposition": "justified",
                        "approval_reference": "ARCH-1",
                        "expires_on": yesterday,
                    },
                    {
                        "capability_id": "project.read",
                        "major_version": 1,
                        "disposition": "split",
                        "replacement_capabilities": ["project.missing"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    report = audit_generic_operations(
        _catalog("project.change.apply", "project.read"),
        load_atomicity_dispositions(disposition_path),
    )

    assert report.expired_ids == ("project.change.apply@1",)
    assert report.missing_replacement_ids == ("project.read@1",)
    assert report.passed is False

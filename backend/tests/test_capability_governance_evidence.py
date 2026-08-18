from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.capability_governance_test.evidence import (
    EVIDENCE_LEVELS,
    EvidenceRecord,
    redact_runtime_result,
)


def test_evidence_levels_are_closed_and_ordered() -> None:
    assert EVIDENCE_LEVELS == (
        "contract", "provider", "repository_codec", "gateway",
        "technical_exposure", "runtime_probe", "runtime_e2e",
    )
    with pytest.raises(ValueError, match="unknown_evidence_level"):
        EvidenceRecord(level="invented", status="passed")


def test_evidence_record_redacts_runtime_secrets_without_mutating_input() -> None:
    runtime_result = {
        "status": "passed", "authorization": "Bearer secret-value",
        "nested": {"password": "not-for-reporting", "safe": "value"},
    }

    record = EvidenceRecord(level="runtime_e2e", status="passed", runtime_result=runtime_result)

    assert record.runtime_result == {
        "status": "passed", "authorization": "<redacted>",
        "nested": {"password": "<redacted>", "safe": "value"},
    }
    assert runtime_result["authorization"] == "Bearer secret-value"
    assert redact_runtime_result(runtime_result) == record.runtime_result


def test_evidence_age_and_dependency_hashes_are_deterministic() -> None:
    observed_at = datetime(2026, 8, 18, tzinfo=timezone.utc)
    record = EvidenceRecord(
        level="runtime_probe", status="passed", source_hash="snapshot-a",
        dependency_hashes={"provider": "provider-a", "catalog": "catalog-a"}, observed_at=observed_at,
    )

    assert record.age_seconds(observed_at + timedelta(seconds=17)) == 17
    assert record.matches(snapshot_hash="snapshot-a", dependency_hashes={"catalog": "catalog-a", "provider": "provider-a"})
    assert not record.matches(snapshot_hash="snapshot-b", dependency_hashes={"catalog": "catalog-a", "provider": "provider-a"})


def test_equivalent_records_have_the_same_hash_regardless_of_mapping_order() -> None:
    first = EvidenceRecord("runtime_probe", "passed", runtime_result={"safe": "value", "nested": {"a": 1, "b": 2}})
    second = EvidenceRecord("runtime_probe", "passed", runtime_result={"nested": {"b": 2, "a": 1}, "safe": "value"})

    assert first == second
    assert hash(first) == hash(second)

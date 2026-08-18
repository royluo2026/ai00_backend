from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.capability_governance_test.evidence import passed
from backend.capability_governance_test.health import HEALTH_STATES, compute_health
from backend.capability_governance_test.rules import FindingCandidate


def test_contract_only_evidence_is_unverified() -> None:
    result = compute_health(required={"contract", "gateway"}, evidence={passed("contract")})

    assert result.status == "unverified"
    assert result.missing_levels == ("gateway",)


def test_changed_provider_hash_makes_runtime_evidence_stale() -> None:
    result = compute_health(snapshot_hash="new", evidence={passed("runtime_e2e", source_hash="old")})

    assert result.status == "stale"


def test_blocking_finding_breaks_health_and_nonblocking_failure_degrades() -> None:
    blocking = FindingCandidate("provider_missing", "blocking")
    broken = compute_health(required={"contract"}, evidence={passed("contract")}, findings=(blocking,))
    degraded = compute_health(required={"contract"}, evidence=(passed("contract"), passed("provider", status="failed")))

    assert broken.status == "broken"
    assert degraded.status == "degraded"


def test_expired_required_evidence_is_stale_and_latest_status_is_deterministic() -> None:
    observed_at = datetime(2026, 8, 18, tzinfo=timezone.utc)
    result = compute_health(
        required={"contract"},
        evidence=(
            passed("contract", observed_at=observed_at),
            passed("provider", status="failed", observed_at=observed_at + timedelta(seconds=1)),
        ),
        now=observed_at + timedelta(seconds=5), max_age_seconds=1,
    )

    assert result.status == "stale"
    assert result.latest_test_status == "failed"
    assert result.evidence_ages["contract"] == 5
    assert HEALTH_STATES == ("healthy", "degraded", "broken", "unverified", "stale")


def test_fresh_evidence_supersedes_an_older_stale_record_at_the_same_level() -> None:
    observed_at = datetime(2026, 8, 18, tzinfo=timezone.utc)
    result = compute_health(
        required={"runtime_e2e"}, snapshot_hash="new",
        evidence=(
            passed("runtime_e2e", source_hash="old", observed_at=observed_at),
            passed("runtime_e2e", source_hash="new", observed_at=observed_at + timedelta(seconds=1)),
        ),
    )

    assert result.status == "healthy"

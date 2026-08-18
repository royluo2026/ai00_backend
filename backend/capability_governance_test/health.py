"""Deterministic health rollups from immutable evidence and findings."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any

from .evidence import EVIDENCE_LEVELS, EvidenceRecord


HEALTH_STATES = ("healthy", "degraded", "broken", "unverified", "stale")


@dataclass(frozen=True)
class HealthRollup:
    status: str
    required_levels: tuple[str, ...]
    missing_levels: tuple[str, ...]
    stale_levels: tuple[str, ...]
    blocking_finding_codes: tuple[str, ...]
    latest_test_status: str | None
    evidence_ages: Mapping[str, int | None]
    evidence: tuple[EvidenceRecord, ...]


def _evidence_order(record: EvidenceRecord) -> tuple[float, int, str, str]:
    timestamp = record.observed_at.timestamp() if record.observed_at else float("-inf")
    return timestamp, EVIDENCE_LEVELS.index(record.level), record.test_case_id, record.status


def _is_blocking(finding: Any) -> bool:
    if isinstance(finding, Mapping):
        severity = finding.get("severity", "")
    else:
        severity = getattr(finding, "severity", "")
    return str(severity).lower() in {"blocking", "critical"}


def _finding_code(finding: Any) -> str:
    if isinstance(finding, Mapping):
        return str(finding.get("code", "blocking_finding"))
    return str(getattr(finding, "code", "blocking_finding"))


def compute_health(
    *,
    required: Iterable[str] = (),
    evidence: Iterable[EvidenceRecord] = (),
    snapshot_hash: str = "",
    dependency_hashes: Mapping[str, str] | None = None,
    findings: Iterable[Any] = (),
    now: datetime | None = None,
    max_age_seconds: int | Mapping[str, int] | None = None,
) -> HealthRollup:
    """Calculate health without side effects or traversal-order-dependent results."""
    required_levels = tuple(sorted(set(str(level) for level in required), key=EVIDENCE_LEVELS.index))
    unknown = set(required_levels).difference(EVIDENCE_LEVELS)
    if unknown:
        raise ValueError("unknown_evidence_level")
    records = tuple(sorted(tuple(evidence), key=_evidence_order))
    by_level: dict[str, tuple[EvidenceRecord, ...]] = {
        level: tuple(record for record in records if record.level == level) for level in EVIDENCE_LEVELS
    }
    latest_by_level = {
        level: max(values, key=_evidence_order) for level, values in by_level.items() if values
    }
    stale: set[str] = set()
    # History remains auditable, but only the latest result for a level represents
    # current health.  A fresh run must be able to replace prior stale evidence.
    for record in latest_by_level.values():
        if not record.matches(snapshot_hash=snapshot_hash, dependency_hashes=dependency_hashes):
            stale.add(record.level)
            continue
        if now is not None and max_age_seconds is not None:
            limit = max_age_seconds.get(record.level) if isinstance(max_age_seconds, Mapping) else max_age_seconds
            age = record.age_seconds(now)
            if limit is not None and (age is None or age > int(limit)):
                stale.add(record.level)
    passed_current = {
        level for level, record in latest_by_level.items()
        if record.status == "passed" and level not in stale
    }
    missing = tuple(level for level in required_levels if level not in passed_current and level not in stale)
    blocking = tuple(sorted({_finding_code(finding) for finding in findings if _is_blocking(finding)}))
    failed_required = any(
        record.status in {"failed", "blocked", "error"} and record.level in required_levels and record.level not in stale
        for record in latest_by_level.values()
    )
    failed_noncritical = any(
        record.status in {"failed", "blocked", "error"} and record.level not in required_levels and record.level not in stale
        for record in latest_by_level.values()
    )
    latest = max(records, key=_evidence_order).status if records else None
    evidence_ages = MappingProxyType({
        level: record.age_seconds(now) if now is not None else None
        for level, record in latest_by_level.items()
    })
    if blocking or failed_required:
        status = "broken"
    elif stale:
        status = "stale"
    elif missing:
        status = "unverified"
    elif failed_noncritical:
        status = "degraded"
    else:
        status = "healthy"
    return HealthRollup(
        status=status, required_levels=required_levels, missing_levels=missing,
        stale_levels=tuple(sorted(stale, key=EVIDENCE_LEVELS.index)),
        blocking_finding_codes=blocking, latest_test_status=latest, evidence_ages=evidence_ages,
        evidence=records,
    )


__all__ = ["HEALTH_STATES", "HealthRollup", "compute_health"]

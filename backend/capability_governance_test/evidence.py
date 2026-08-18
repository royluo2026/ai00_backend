"""Immutable, redacted evidence records for the test-governance extension."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any


EVIDENCE_LEVELS = (
    "contract", "provider", "repository_codec", "gateway",
    "technical_exposure", "runtime_probe", "runtime_e2e",
)

_REDACTED = "<redacted>"
_SENSITIVE_KEYS = (
    "authorization", "cookie", "credential", "password", "payload", "secret", "token", "url", "username",
)


def redact_runtime_result(value: Any) -> Any:
    """Return a report-safe deep copy without credentials or runtime payload secrets."""
    if isinstance(value, Mapping):
        return {
            str(key): _REDACTED if any(part in str(key).lower() for part in _SENSITIVE_KEYS)
            else redact_runtime_result(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple | list):
        return tuple(redact_runtime_result(item) for item in value)
    if isinstance(value, set | frozenset):
        return tuple(sorted((redact_runtime_result(item) for item in value), key=repr))
    return value


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    redacted = redact_runtime_result(value)
    assert isinstance(redacted, Mapping)
    frozen = _deep_freeze(redacted)
    assert isinstance(frozen, Mapping)
    return frozen


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, tuple | list):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, set | frozenset):
        return tuple(sorted((_deep_freeze(item) for item in value), key=repr))
    return value


def _mutable_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _mutable_copy(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_mutable_copy(item) for item in value]
    return value


def _normalize_time(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _hashable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return tuple(sorted((str(key), _hashable(item)) for key, item in value.items()))
    if isinstance(value, tuple | list | set | frozenset):
        return tuple(sorted((_hashable(item) for item in value), key=repr))
    try:
        hash(value)
    except TypeError:
        return repr(value)
    return value


@dataclass(frozen=True)
class EvidenceRecord:
    """A single level of evidence bound to the snapshot and its dependencies."""

    level: str
    status: str
    source_hash: str = ""
    dependency_hashes: Mapping[str, str] = field(default_factory=dict)
    observed_at: datetime | None = None
    runtime_result: Mapping[str, Any] = field(default_factory=dict)
    test_case_id: str = ""
    fixture_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.level not in EVIDENCE_LEVELS:
            raise ValueError("unknown_evidence_level")
        object.__setattr__(self, "source_hash", str(self.source_hash))
        object.__setattr__(self, "dependency_hashes", MappingProxyType(
            {str(key): str(value) for key, value in sorted(self.dependency_hashes.items())},
        ))
        object.__setattr__(self, "observed_at", _normalize_time(self.observed_at))
        object.__setattr__(self, "runtime_result", _freeze_mapping(self.runtime_result))
        object.__setattr__(self, "fixture_ids", tuple(sorted(set(str(value) for value in self.fixture_ids))))

    def __hash__(self) -> int:
        return hash((
            self.level, self.status, self.source_hash, tuple(self.dependency_hashes.items()), self.observed_at,
            _hashable(self.runtime_result), self.test_case_id, self.fixture_ids,
        ))

    def age_seconds(self, now: datetime) -> int | None:
        """Return a non-negative, whole-second age using an explicit reference time."""
        if self.observed_at is None:
            return None
        moment = _normalize_time(now)
        assert moment is not None
        return max(0, int((moment - self.observed_at).total_seconds()))

    def matches(self, *, snapshot_hash: str = "", dependency_hashes: Mapping[str, str] | None = None) -> bool:
        """Whether this evidence is still bound to the supplied immutable inputs."""
        if snapshot_hash and self.source_hash != str(snapshot_hash):
            return False
        if dependency_hashes is None:
            return True
        expected = {str(key): str(value) for key, value in sorted(dependency_hashes.items())}
        return dict(self.dependency_hashes) == expected

    def to_json(self) -> dict[str, Any]:
        return {
            "level": self.level, "status": self.status, "source_hash": self.source_hash,
            "dependency_hashes": dict(self.dependency_hashes),
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "runtime_result": _mutable_copy(self.runtime_result), "test_case_id": self.test_case_id,
            "fixture_ids": list(self.fixture_ids),
        }


def passed(level: str, **kwargs: Any) -> EvidenceRecord:
    """Small test and call-site convenience constructor for passed evidence."""
    return EvidenceRecord(level=level, status=str(kwargs.pop("status", "passed")), **kwargs)


__all__ = ["EVIDENCE_LEVELS", "EvidenceRecord", "passed", "redact_runtime_result"]

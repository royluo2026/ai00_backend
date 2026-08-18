"""Append-only, redacted audit evidence for the test-governance control plane."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from types import MappingProxyType
from typing import Any


class AuditError(RuntimeError):
    """Raised when audit history would be altered rather than appended."""


_SENSITIVE_KEY = re.compile(r"(?:pass(?:word)?|token|secret|credential|authorization|cookie|api[_-]?key|url)", re.I)
_SENSITIVE_VALUE = re.compile(r"(?:https?://[^\s/@:]+:[^\s/@]+@|(?:pass(?:word)?|token|secret|api[_-]?key)\s*[=:])", re.I)


def redact_detail(value: Any) -> Any:
    """Produce a safe immutable-detail equivalent without secret-bearing values."""
    if isinstance(value, Mapping):
        return {str(key): "<redacted>" if _SENSITIVE_KEY.search(str(key)) else redact_detail(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return tuple(redact_detail(item) for item in value)
    if isinstance(value, set | frozenset):
        return tuple(sorted((redact_detail(item) for item in value), key=repr))
    if isinstance(value, str) and _SENSITIVE_VALUE.search(value):
        return "<redacted>"
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, tuple | list):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class AuditEvent:
    audit_event_gid: int
    operation: str
    entity_gid: int | None
    actor_gid: str
    request_gid: str
    detail: Mapping[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        safe = redact_detail(self.detail)
        if not isinstance(safe, Mapping):
            raise AuditError("audit_detail_mapping_required")
        object.__setattr__(self, "detail", _freeze(safe))
        if self.occurred_at.tzinfo is None:
            object.__setattr__(self, "occurred_at", self.occurred_at.replace(tzinfo=timezone.utc))


class AuditSink:
    """In-memory append-only sink; persistence adapters must preserve this contract."""

    def __init__(self, *, next_gid: Callable[[], int]) -> None:
        self._next_gid = next_gid
        self._events: list[AuditEvent] = []
        self._idempotency: dict[str, AuditEvent] = {}

    @property
    def events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)

    def append(self, *, operation: str, entity_gid: int | None, actor_gid: str, request_gid: str, detail: Mapping[str, Any], idempotency_key: str, occurred_at: datetime | None = None) -> AuditEvent:
        key = str(idempotency_key).strip()
        if not key:
            raise AuditError("idempotency_key_required")
        if key in self._idempotency:
            return self._idempotency[key]
        event = AuditEvent(self._next_gid(), str(operation), entity_gid, str(actor_gid), str(request_gid), detail, occurred_at or datetime.now(timezone.utc))
        self._events.append(event)
        self._idempotency[key] = event
        return event

    def update(self, audit_event_gid: int, **_: Any) -> None:
        raise AuditError("append_only")

    def delete(self, audit_event_gid: int) -> None:
        raise AuditError("append_only")


__all__ = ["AuditError", "AuditEvent", "AuditSink", "redact_detail"]

"""Runtime-side operation replay boundary keyed by the signed operation ID."""
from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock


class ReplayDetected(ValueError):
    pass


class ReplayGuard:
    def __init__(self):
        self._accepted: dict[str, datetime] = {}
        self._lock = Lock()

    def accept(self, operation_id: str, *, expires_at: datetime, now: datetime | None = None) -> None:
        current = now or datetime.now(UTC)
        current = current if current.tzinfo else current.replace(tzinfo=UTC)
        expiry = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)
        if expiry <= current:
            raise ValueError("local operation is expired")
        key = str(operation_id or "").strip()
        if not key:
            raise ValueError("local operation ID is required")
        with self._lock:
            self._accepted = {item: deadline for item, deadline in self._accepted.items() if deadline > current}
            if key in self._accepted:
                raise ReplayDetected("local operation replay detected")
            self._accepted[key] = expiry

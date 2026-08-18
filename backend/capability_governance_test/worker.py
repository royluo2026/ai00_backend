"""Exclusive, renewable run leases for test-governance analysis and test workers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
import inspect
from threading import Event, RLock, Thread
from typing import Any, Callable

from backend.utils.gid import next_gid


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class RunLease:
    kind: str
    run_gid: str
    status: str
    worker_id: str | None = None
    lease_expires_at: datetime | None = None


class RunLeaseStore(ABC):
    """A persistence port. Implementations must atomically claim queued runs."""

    @abstractmethod
    def acquire(self, kind: str, run_gid: str, worker_id: str, *, lease_seconds: int) -> bool:
        """Claim a queued/expired run exclusively."""

    @abstractmethod
    def renew(self, kind: str, run_gid: str, worker_id: str, *, lease_seconds: int) -> bool:
        """Extend only the current worker's live lease."""

    @abstractmethod
    def complete(self, kind: str, run_gid: str, worker_id: str) -> bool:
        """Transition a current live lease to completed once."""


class InMemoryRunLeaseStore(RunLeaseStore):
    """Thread-safe fake implementing the same exclusive state transitions as SQL."""

    def __init__(self, *, clock: Callable[[], datetime] = _now) -> None:
        self._clock = clock
        self._lock = RLock()
        self._runs: dict[tuple[str, str], RunLease] = {}

    def queue(self, kind: str, run_gid: str) -> None:
        with self._lock:
            self._runs[(kind, str(run_gid))] = RunLease(kind, str(run_gid), "queued")

    def acquire(self, kind: str, run_gid: str, worker_id: str, *, lease_seconds: int) -> bool:
        with self._lock:
            key = (kind, str(run_gid))
            current = self._expired_to_queued(key, self._clock())
            if current is None or current.status != "queued":
                return False
            self._runs[key] = replace(
                current, status="running", worker_id=worker_id,
                lease_expires_at=self._clock() + timedelta(seconds=lease_seconds),
            )
            return True

    def renew(self, kind: str, run_gid: str, worker_id: str, *, lease_seconds: int) -> bool:
        with self._lock:
            key = (kind, str(run_gid))
            current = self._expired_to_queued(key, self._clock())
            if current is None or current.status != "running" or current.worker_id != worker_id:
                return False
            self._runs[key] = replace(current, lease_expires_at=self._clock() + timedelta(seconds=lease_seconds))
            return True

    def complete(self, kind: str, run_gid: str, worker_id: str) -> bool:
        with self._lock:
            key = (kind, str(run_gid))
            current = self._expired_to_queued(key, self._clock())
            if current is None or current.status != "running" or current.worker_id != worker_id:
                return False
            self._runs[key] = replace(current, status="completed", worker_id=None, lease_expires_at=None)
            return True

    def expire(self, kind: str, run_gid: str, now: datetime | None = None) -> None:
        with self._lock:
            self._expired_to_queued((kind, str(run_gid)), now or self._clock())

    def status(self, kind: str, run_gid: str) -> str | None:
        with self._lock:
            current = self._expired_to_queued((kind, str(run_gid)), self._clock())
            return current.status if current else None

    def _expired_to_queued(self, key: tuple[str, str], now: datetime) -> RunLease | None:
        current = self._runs.get(key)
        if current is not None and current.status == "running" and current.lease_expires_at is not None and current.lease_expires_at <= now:
            current = replace(current, status="queued", worker_id=None, lease_expires_at=None)
            self._runs[key] = current
        return current


class SqlRunLeaseStore(RunLeaseStore):
    """Database-backed lease port using compare-and-set updates.

    The test-governance deployment owns the lease table; callers inject a DB-API
    connection factory, which keeps the state machine testable without a server.
    """

    TABLE = "workmanship_base_capability_worker_leases"

    def __init__(
        self,
        connection_factory: Callable[[], Any],
        *,
        clock: Callable[[], datetime] = _now,
        next_ids: Callable[[], int] = next_gid,
    ) -> None:
        self._connection_factory = connection_factory
        self._clock = clock
        self._next_ids = next_ids

    def acquire(self, kind: str, run_gid: str, worker_id: str, *, lease_seconds: int) -> bool:
        now = self._clock()
        expiry = now + timedelta(seconds=lease_seconds)
        connection = self._connection_factory()
        cursor = connection.cursor()
        try:
            cursor.execute(
                "INSERT INTO " + self.TABLE + " "
                "(worker_lease_gid, run_kind, run_gid, status, worker_id, lease_expires_at, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE updated_at=updated_at",
                (self._next_ids(), kind, int(run_gid), "queued", None, None, now, now),
            )
            cursor.execute(
                "UPDATE " + self.TABLE + " SET status=%s, worker_id=%s, lease_expires_at=%s, updated_at=%s "
                "WHERE run_kind=%s AND run_gid=%s AND (status='queued' OR (status='running' AND lease_expires_at <= %s))",
                ("running", worker_id, expiry, now, kind, int(run_gid), now),
            )
            changed = int(cursor.rowcount) == 1
            connection.commit()
            return changed
        except Exception:
            connection.rollback()
            raise
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def renew(self, kind: str, run_gid: str, worker_id: str, *, lease_seconds: int) -> bool:
        now = self._clock()
        return self._update(
            "UPDATE " + self.TABLE + " SET lease_expires_at=%s WHERE run_kind=%s AND run_gid=%s "
            "AND status='running' AND worker_id=%s AND lease_expires_at > %s",
            (now + timedelta(seconds=lease_seconds), kind, str(run_gid), worker_id, now),
        )

    def complete(self, kind: str, run_gid: str, worker_id: str) -> bool:
        now = self._clock()
        completed = self._update(
            "UPDATE " + self.TABLE + " SET status=%s, worker_id=NULL, lease_expires_at=NULL "
            "WHERE run_kind=%s AND run_gid=%s AND status='running' AND worker_id=%s AND lease_expires_at > %s",
            ("completed", kind, str(run_gid), worker_id, now),
        )
        if not completed:
            self._update(
                "UPDATE " + self.TABLE + " SET status=%s, worker_id=NULL, lease_expires_at=NULL "
                "WHERE run_kind=%s AND run_gid=%s AND status='running' AND worker_id=%s AND lease_expires_at <= %s",
                ("queued", kind, str(run_gid), worker_id, now),
            )
        return completed

    def _update(self, statement: str, values: tuple[Any, ...]) -> bool:
        connection = self._connection_factory()
        cursor = connection.cursor()
        try:
            cursor.execute(statement, values)
            changed = int(cursor.rowcount) == 1
            connection.commit()
            return changed
        except Exception:
            connection.rollback()
            raise
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()


class LeasedGovernanceWorker:
    """Worker facade that renews before completion and never double-completes a run."""

    def __init__(self, leases: RunLeaseStore, *, worker_id: str, lease_seconds: int = 30) -> None:
        self._leases = leases
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds

    def acquire(self, kind: str, run_gid: str) -> bool:
        return self._leases.acquire(kind, str(run_gid), self._worker_id, lease_seconds=self._lease_seconds)

    def renew(self, kind: str, run_gid: str) -> bool:
        return self._leases.renew(kind, str(run_gid), self._worker_id, lease_seconds=self._lease_seconds)

    def complete(self, kind: str, run_gid: str) -> bool:
        return self._leases.complete(kind, str(run_gid), self._worker_id)

    def run_once(self, kind: str, run_gid: str, execute: Callable[..., Any]) -> bool:
        if not self.acquire(kind, run_gid):
            return False
        stop = Event()
        lease_lost = Event()

        def heartbeat() -> bool:
            renewed = self.renew(kind, run_gid)
            if not renewed:
                lease_lost.set()
            return renewed

        def renew_while_active() -> None:
            while not stop.wait(max(0.01, self._lease_seconds / 3)):
                if not heartbeat():
                    return

        renewal_thread = Thread(target=renew_while_active, daemon=True)
        renewal_thread.start()
        try:
            if len(inspect.signature(execute).parameters) == 0:
                execute()
            else:
                execute(heartbeat)
            if lease_lost.is_set() or not heartbeat():
                return False
            return self.complete(kind, run_gid)
        except Exception:
            # Lease expiry returns the run to queued; failures never masquerade as complete.
            raise
        finally:
            stop.set()
            renewal_thread.join(timeout=1)


__all__ = [
    "InMemoryRunLeaseStore", "LeasedGovernanceWorker", "RunLease", "RunLeaseStore", "SqlRunLeaseStore",
]

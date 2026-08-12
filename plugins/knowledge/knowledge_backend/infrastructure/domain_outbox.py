"""Knowledge-owned durable Outbox poller for domain-event transport."""
from __future__ import annotations

import json
from datetime import UTC, datetime

from backend.capability_v2.domain_events import DomainEventEnvelope
from ..data.connection import _get_pool


class KnowledgeOutboxPoller:
    def __init__(self, connection_factory=None, *, max_attempts: int = 5):
        self._connection_factory = connection_factory
        self._max_attempts = max_attempts

    def _connection(self):
        if self._connection_factory is not None:
            return self._connection_factory()
        return _get_pool().connection()

    @staticmethod
    def _close(connection) -> None:
        connection.close()

    def poll(self, *, limit: int = 100) -> tuple[DomainEventEnvelope, ...]:
        connection = self._connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT gid,event_type,event_version,subject_ref,payload,attempts,created_at "
                    "FROM workmanship_know_domain_outbox WHERE status IN ('pending','retry') "
                    "AND attempts < %s ORDER BY created_at LIMIT %s", (self._max_attempts, limit),
                )
                rows = cursor.fetchall()
            return tuple(self._envelope(row) for row in rows)
        finally:
            self._close(connection)

    def mark_delivered(self, event_id: str) -> None:
        self._mark(event_id, status="delivered", last_error=None)

    def mark_failed(self, event_id: str, error: Exception) -> None:
        self._mark(event_id, status="retry", last_error=str(error)[:2048])

    def _mark(self, event_id: str, *, status: str, last_error: str | None) -> None:
        connection = self._connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE workmanship_know_domain_outbox SET status=%s,attempts=attempts+1,last_error=%s,updated_at=NOW(6) WHERE gid=%s",
                    (status, last_error, event_id),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            self._close(connection)

    @staticmethod
    def _envelope(row) -> DomainEventEnvelope:
        payload = row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"])
        payload = dict(payload); tenant_id = str(payload.pop("tenant_gid"))
        version = int(row["event_version"]); event_id = str(row["gid"])
        occurred_at = row.get("created_at") or datetime.now(UTC)
        if occurred_at.tzinfo is None: occurred_at = occurred_at.replace(tzinfo=UTC)
        return DomainEventEnvelope(
            event_id=event_id, event_type=str(row["event_type"]).removesuffix(f".v{version}"), event_version=version,
            producer_domain="knowledge", tenant_id=tenant_id, aggregate_type="knowledge.document",
            aggregate_id=str(row["subject_ref"]), aggregate_version=1, occurred_at=occurred_at, payload=payload,
            request_id=event_id, trace_id=event_id, causation_id=event_id,
        )


__all__ = ["KnowledgeOutboxPoller"]

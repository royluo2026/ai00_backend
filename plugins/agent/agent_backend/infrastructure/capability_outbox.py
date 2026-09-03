from __future__ import annotations

import asyncio
import inspect
import json
import uuid
from datetime import UTC, datetime

from ..data.connection import get_agent_conn


class AgentCapabilityOutboxRepository:
    """Agent-owned claim/retry state for committed capability outcomes."""

    def __init__(self, connection_factory=get_agent_conn):
        self._connections = connection_factory

    def claim_next(self, worker_id: str, *, lease_seconds: int = 30):
        lease_token = f"{worker_id}:{uuid.uuid4().hex}"
        with self._connections() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM workmanship_agent_capability_outbox WHERE "
                "(state='pending' AND (next_attempt_at IS NULL OR next_attempt_at<=NOW(6))) OR "
                "(state='processing' AND lease_expires_at<NOW(6)) "
                "ORDER BY created_at,event_id LIMIT 1 FOR UPDATE SKIP LOCKED"
            )
            row = cursor.fetchone()
            if row is None:
                return None
            cursor.execute(
                "UPDATE workmanship_agent_capability_outbox SET state='processing',"
                "attempt_count=attempt_count+1,lease_owner=%s,lease_token=%s,"
                "lease_expires_at=DATE_ADD(NOW(6),INTERVAL %s SECOND),last_error=NULL "
                "WHERE event_id=%s AND (state='pending' OR "
                "(state='processing' AND lease_expires_at<NOW(6)))",
                (worker_id, lease_token, max(1, int(lease_seconds)), row["event_id"]),
            )
            if cursor.rowcount != 1:
                return None
        event = dict(row)
        payload = event.get("payload_json") or {}
        if isinstance(payload, (bytes, bytearray)):
            payload = payload.decode("utf-8")
        event["payload"] = json.loads(payload) if isinstance(payload, str) else dict(payload)
        event["lease_token"] = lease_token
        return event

    def mark_delivered(self, event_id: str, lease_token: str) -> bool:
        with self._connections() as conn, conn.cursor() as cursor:
            cursor.execute(
                "UPDATE workmanship_agent_capability_outbox SET state='delivered',"
                "delivered_at=NOW(6),lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,"
                "next_attempt_at=NULL,last_error=NULL "
                "WHERE event_id=%s AND state='processing' AND lease_token=%s",
                (event_id, lease_token),
            )
            return cursor.rowcount == 1

    def retry(self, event_id: str, lease_token: str, error: Exception, *, delay_seconds: int) -> bool:
        with self._connections() as conn, conn.cursor() as cursor:
            cursor.execute(
                "UPDATE workmanship_agent_capability_outbox SET state='pending',"
                "next_attempt_at=DATE_ADD(NOW(6),INTERVAL %s SECOND),"
                "lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,last_error=%s "
                "WHERE event_id=%s AND state='processing' AND lease_token=%s",
                (max(1, int(delay_seconds)), str(error)[:500], event_id, lease_token),
            )
            return cursor.rowcount == 1


class AgentCapabilityOutboxDispatcher:
    def __init__(self, repository, deliver, *, poll_interval: float = 1.0, worker_id: str | None = None):
        self._repository = repository
        self._deliver = deliver
        self._poll_interval = max(0.01, float(poll_interval))
        self._worker_id = worker_id or f"agent-outbox-{uuid.uuid4().hex[:12]}"
        self._task = None
        self._stopping = asyncio.Event()
        self._health = {
            "status": "stopped", "delivered": 0, "failures": 0,
            "last_error": None, "last_success_at": None,
        }

    @property
    def health(self):
        return dict(self._health)

    async def run_once(self) -> bool:
        event = await asyncio.to_thread(self._repository.claim_next, self._worker_id)
        if event is None:
            return False
        try:
            if inspect.iscoroutinefunction(self._deliver):
                await self._deliver(event)
            else:
                value = await asyncio.to_thread(self._deliver, event)
                if inspect.isawaitable(value):
                    await value
        except Exception as exc:
            attempts = max(1, int(event.get("attempt_count") or 0) + 1)
            await asyncio.to_thread(
                self._repository.retry, event["event_id"], event["lease_token"], exc,
                delay_seconds=min(300, 2 ** min(attempts, 8)),
            )
            self._health.update(
                failures=self._health["failures"] + 1, last_error=type(exc).__name__,
            )
            return False
        delivered = await asyncio.to_thread(
            self._repository.mark_delivered, event["event_id"], event["lease_token"],
        )
        if delivered:
            self._health.update(
                delivered=self._health["delivered"] + 1,
                last_error=None, last_success_at=datetime.now(UTC).isoformat(),
            )
        return delivered

    async def _run(self):
        self._health["status"] = "running"
        try:
            while not self._stopping.is_set():
                try:
                    worked = await self.run_once()
                except Exception as exc:
                    self._health.update(
                        failures=self._health["failures"] + 1,
                        last_error=type(exc).__name__,
                    )
                    worked = False
                if not worked:
                    try:
                        await asyncio.wait_for(
                            self._stopping.wait(), timeout=self._poll_interval,
                        )
                    except TimeoutError:
                        pass
        finally:
            self._health["status"] = "stopped"

    async def start(self):
        if self._task is None or self._task.done():
            self._stopping.clear()
            self._task = asyncio.create_task(self._run())

    async def stop(self):
        self._stopping.set()
        task, self._task = self._task, None
        if task is not None:
            await task


def default_agent_outcome_delivery(event):
    from backend.capability_v2.gateway import get_default_gateway
    return get_default_gateway().reconcile_committed_agent_outcome(event)


__all__ = [
    "AgentCapabilityOutboxDispatcher", "AgentCapabilityOutboxRepository",
    "default_agent_outcome_delivery",
]

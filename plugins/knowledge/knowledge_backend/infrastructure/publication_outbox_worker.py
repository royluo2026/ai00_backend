"""Knowledge-owned worker for OIS publication outbox jobs."""
from __future__ import annotations

import asyncio
import json
import logging
import socket
import uuid
from datetime import UTC, datetime
from typing import Any

_log = logging.getLogger(__name__)
_LOCK_NAME = "ai00:knowledge-publish-outbox"
_WORKER_ID = f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"

def _heartbeat(cur, status: str, details: dict[str, Any]) -> None:
    cur.execute(
        """INSERT INTO workmanship_app_worker_heartbeats
           (worker_name, worker_id, status, details, heartbeat_at, started_at)
           VALUES ('knowledge-outbox', %s, %s, %s, NOW(), NOW())
           ON DUPLICATE KEY UPDATE worker_id=VALUES(worker_id), status=VALUES(status),
             details=VALUES(details), heartbeat_at=NOW()""",
        (_WORKER_ID, status, json.dumps(details, ensure_ascii=False)),
    )


def _open_dead_alert(cur, outbox_gid: str, error: str) -> None:
    cur.execute(
        """INSERT INTO workmanship_app_operational_alerts
           (gid, alert_type, severity, source_gid, message, status, created_at, updated_at)
           VALUES (%s, 'knowledge_publish_dead', 'high', %s, %s, 'open', NOW(), NOW())
           ON DUPLICATE KEY UPDATE message=VALUES(message), status='open', updated_at=NOW()""",
        (f"alert:{outbox_gid}", outbox_gid, error[:4000]),
    )


def deliver_capability_audit_once(limit: int = 100) -> int:
    """Deliver the V2 audit outbox idempotently into the immutable audit ledger."""
    from backend.capability_v2.outcomes import SqlOutcomeStore
    from backend.knowledge.data.connection import get_knowledge_conn as get_conn

    store = SqlOutcomeStore(get_conn)

    def persist(event) -> None:
        payload = event.payload
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT IGNORE INTO workmanship_base_capability_audit_ledger "
                    "(event_id,operation_id,capability_id,major_version,request_id,tenant_id,"
                    "actor_id,consumer_type,consumer_id,consumer_instance_id,policy_version,"
                    "payload_hash,status,created_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        event.event_id, event.operation_id, payload["capability_id"],
                        payload["major_version"], payload["request_id"], payload["tenant_id"],
                        payload["actor_id"], payload["consumer_type"], payload["consumer_id"],
                        payload.get("consumer_instance_id"), payload["policy_version"],
                        payload["payload_hash"], payload["status"], event.created_at,
                    ),
                )

    return store.deliver_audit_outbox(persist, limit=limit)


async def run_once(limit: int = 20) -> dict[str, Any]:
    """Run one locked batch. MySQL GET_LOCK prevents duplicate workers."""
    from backend.knowledge.data.connection import get_knowledge_conn as get_conn

    limit = max(1, min(int(limit or 20), 100))
    with get_conn() as lock_conn:
        with lock_conn.cursor() as cur:
            cur.execute("SELECT GET_LOCK(%s, 0) AS acquired", (_LOCK_NAME,))
            lock_row = cur.fetchone() or {}
            if not bool(lock_row.get("acquired")):
                return {"locked_out": True, "scanned": 0, "completed": 0, "failed": 0, "dead": 0, "results": []}
            _heartbeat(cur, "running", {"batch_size": limit})
            lock_conn.commit()
        try:
            audit_delivered = deliver_capability_audit_once(limit=max(limit, 100))
            with lock_conn.cursor() as cur:
                cur.execute(
                    "SELECT gid FROM workmanship_know_publish_outbox "
                    "WHERE status='pending' AND next_retry_at <= NOW() "
                    "ORDER BY next_retry_at ASC LIMIT %s",
                    (limit,),
                )
                rows = cur.fetchall()
            job_ids = [str(row["gid"]) for row in rows]
            results: list[dict[str, Any]] = []
            for outbox_gid in job_ids:
                try:
                    from backend.capability_v2.contracts import (
                        ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType,
                        InvocationEnvelope, TenantIdentity,
                    )
                    from backend.capability_v2.gateway import get_default_gateway

                    payload = {"outbox_gid": outbox_gid}
                    request_id = f"worker:{_WORKER_ID}:{outbox_gid}"
                    gateway = get_default_gateway()
                    result = await gateway.invoke(InvocationEnvelope(
                        capability_id="knowledge.proposal.outbox.retry",
                        major_version=1,
                        catalog_release=gateway.catalog_release,
                        payload=payload,
                        identity=ConsumerIdentity(
                            actor=ActorIdentity(
                                service_id="system:outbox-worker",
                                authentication_method="service_runtime",
                                authenticated_at=datetime.now(UTC),
                            ),
                            tenant=TenantIdentity(
                                tenant_id="system", membership="service", active_roles=("outbox_worker",),
                            ),
                            consumer=ConsumerDescriptor(
                                type=ConsumerType.WORKER, consumer_id="knowledge-outbox",
                            ),
                        ),
                        request_id=request_id,
                        trace_id=request_id,
                    ))
                    if not result.ok:
                        raise RuntimeError(result.error.code if result.error else "capability_failed")
                    result_status = str((result.data or {}).get("status") or "completed")
                    results.append({"outbox_gid": outbox_gid, "status": result_status, "data": result.data})
                    if result_status == "dead":
                        with lock_conn.cursor() as cur:
                            _open_dead_alert(cur, outbox_gid, "maximum retry attempts reached")
                            lock_conn.commit()
                except Exception as exc:
                    _log.warning("outbox retry failed gid=%s: %s", outbox_gid, exc)
                    results.append({"outbox_gid": outbox_gid, "status": "failed", "error": str(exc)})

            summary = {
                "locked_out": False,
                "scanned": len(job_ids),
                "completed": sum(r["status"] == "completed" for r in results),
                "failed": sum(r["status"] == "failed" for r in results),
                "dead": sum(r["status"] == "dead" for r in results),
                "capability_audit_delivered": audit_delivered,
                "results": results,
            }
            with lock_conn.cursor() as cur:
                _heartbeat(cur, "idle", {k: v for k, v in summary.items() if k != "results"})
                lock_conn.commit()
            return summary
        finally:
            with lock_conn.cursor() as cur:
                cur.execute("SELECT RELEASE_LOCK(%s)", (_LOCK_NAME,))


async def run_forever(interval_seconds: int = 30, batch_size: int = 20) -> None:
    interval_seconds = max(5, min(int(interval_seconds), 3600))
    while True:
        try:
            await run_once(batch_size)
        except Exception:
            _log.exception("outbox worker iteration failed")
        await asyncio.sleep(interval_seconds)

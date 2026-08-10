"""Base operational capabilities composed through public domain ports."""
from __future__ import annotations

from typing import Any

from backend.capabilities.models_next import CapabilitySpec
from backend.domain_ports.operations import operations_registry

from .provider import register_capability


def _base_health() -> dict[str, Any]:
    from backend.db.connection import get_conn

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT worker_name, worker_id, status, details, heartbeat_at, started_at "
                "FROM workmanship_app_worker_heartbeats WHERE worker_name='knowledge-outbox'"
            )
            heartbeat = cur.fetchone()
            cur.execute(
                "SELECT COUNT(*) AS count FROM workmanship_app_operational_alerts "
                "WHERE status='open'"
            )
            alert_row = cur.fetchone() or {"count": 0}
    heartbeat_value = dict(heartbeat) if heartbeat else None
    if heartbeat_value:
        for field in ("heartbeat_at", "started_at"):
            value = heartbeat_value.get(field)
            heartbeat_value[field] = value.isoformat() if hasattr(value, "isoformat") else str(value or "")
    return {"heartbeat": heartbeat_value, "open_alerts": int(alert_row["count"])}


def worker_health(_payload: dict[str, Any], context: object) -> dict[str, Any]:
    provider = operations_registry.get("knowledge")
    if provider is None:
        raise LookupError("knowledge operations provider is unavailable")
    return {**_base_health(), **dict(provider.health(context))}


def register_worker_capability(registry: Any) -> None:
    register_capability(registry, CapabilitySpec(
        owner="base",
        id="system.worker.outbox.health",
        version=1,
        description="Read the Knowledge publication worker heartbeat, queue totals, and alert total.",
        permissions=("system.tech_config",),
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        tags=("system", "operations", "read"),
    ), worker_health)


__all__ = ["register_worker_capability", "worker_health"]

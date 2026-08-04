"""Persistent capability audit sink with a bounded fallback buffer."""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

from .confirmation_next import payload_digest

_log = logging.getLogger(__name__)


class AuditSink:
    def __init__(self, max_events: int = 2000) -> None:
        self._events: deque[dict[str, Any]] = deque(maxlen=max_events)
        self._lock = threading.Lock()
        self._db_disabled = False

    def record(self, *, capability_id: str, version: int, context: Any, payload: dict[str, Any], status: str, error: str | None = None) -> dict[str, Any]:
        event = {
            "event_type": "capability.invocation",
            "capability_id": capability_id,
            "version": version,
            "user_gid": context.user_gid,
            "source": context.source,
            "request_id": context.request_id,
            "plugin_id": getattr(context, "plugin_id", None),
            "plugin_version": getattr(context, "plugin_version", None),
            "payload_hash": payload_digest(payload),
            "status": status,
            "error": error,
            "created_at": time.time(),
        }
        with self._lock:
            self._events.append(event)
        self._persist(event)
        return event

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events)[-max(1, min(limit, 500)):]

    def _persist(self, event: dict[str, Any]) -> None:
        if self._db_disabled:
            return
        try:
            from backend.db.connection import get_conn

            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO workmanship_app_capability_audit
                           (event_type, capability_id, version, user_gid, source,
                            request_id, payload_hash, status, error_message, created_at)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())""",
                        (
                            event["event_type"], event["capability_id"], event["version"],
                            event["user_gid"], event["source"], event["request_id"],
                            event["payload_hash"], event["status"], event["error"],
                        ),
                    )
                conn.commit()
        except Exception as exc:
            self._db_disabled = True
            _log.warning("Capability audit persistence disabled for this process: %s", exc)


audit_sink = AuditSink()

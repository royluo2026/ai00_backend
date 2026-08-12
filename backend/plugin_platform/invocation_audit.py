"""Base-owned audit trail for Plugin mount capability attempts."""
from __future__ import annotations

import hashlib
import json
import logging
from collections import deque
from threading import Lock
from time import time


_log = logging.getLogger(__name__)


class PluginInvocationAuditSink:
    def __init__(self, connection_factory=None, *, max_events: int = 2000) -> None:
        self._connection_factory = connection_factory
        self._events = deque(maxlen=max_events)
        self._lock = Lock()
        self._db_disabled = False

    def record(
        self, *, session, capability_id: str, major_version: int,
        request_id: str, payload: dict, status: str, error: str | None = None,
    ) -> dict:
        payload_hash = "sha256:" + hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        event = {
            "tenant_gid": session.tenant_id,
            "plugin_id": session.plugin_id,
            "installation_id": session.installation_id,
            "mount_session_id": session.mount_session_id,
            "capability_id": capability_id,
            "major_version": major_version,
            "request_id": request_id,
            "payload_hash": payload_hash,
            "status": status,
            "error": error,
            "created_at": time(),
        }
        with self._lock:
            self._events.append(event)
        self._persist(event)
        return event

    def recent(self, limit: int = 100) -> list[dict]:
        with self._lock:
            return list(self._events)[-max(1, min(limit, 500)):]

    def _persist(self, event: dict) -> None:
        if self._db_disabled:
            return
        try:
            if self._connection_factory is None:
                from backend.base.approval import _base_runtime_connection
                connection_factory = _base_runtime_connection
            else:
                connection_factory = self._connection_factory
            with connection_factory() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO workmanship_base_plugin_invocation_audit "
                        "(tenant_gid,plugin_id,installation_id,mount_session_id,capability_id,"
                        "major_version,request_id,payload_hash,status,error_code) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        tuple(event[key] for key in (
                            "tenant_gid", "plugin_id", "installation_id",
                            "mount_session_id", "capability_id", "major_version",
                            "request_id", "payload_hash", "status", "error",
                        )),
                    )
                connection.commit()
        except Exception as exc:
            self._db_disabled = True
            _log.warning("Plugin invocation audit persistence disabled: %s", exc)


mount_invocation_audit = PluginInvocationAuditSink()


__all__ = ["PluginInvocationAuditSink", "mount_invocation_audit"]

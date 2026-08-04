"""One-time confirmation tokens shared by Web, Agent and future MCP calls."""
from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any

_TTL_SECONDS = 300


def payload_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass
class _PendingConfirmation:
    capability_id: str
    version: int
    user_gid: str
    payload_hash: str
    expires_at: float


class ConfirmationManager:
    def __init__(self, ttl_seconds: int = _TTL_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds
        self._pending: dict[str, _PendingConfirmation] = {}
        self._lock = threading.Lock()

    def issue(self, capability_id: str, version: int, user_gid: str, payload: dict[str, Any]) -> str:
        token = secrets.token_urlsafe(32)
        pending = _PendingConfirmation(capability_id, version, user_gid, payload_digest(payload), time.time() + self.ttl_seconds)
        with self._lock:
            self._purge_locked()
            self._pending[token] = pending
        return token

    def consume(self, token: str, capability_id: str, version: int, user_gid: str, payload: dict[str, Any]) -> bool:
        if not token:
            return False
        with self._lock:
            pending = self._pending.pop(token, None)
            if pending is None or pending.expires_at <= time.time():
                return False
            return (
                pending.capability_id == capability_id
                and pending.version == version
                and pending.user_gid == user_gid
                and secrets.compare_digest(pending.payload_hash, payload_digest(payload))
            )

    def _purge_locked(self) -> None:
        now = time.time()
        expired = [token for token, pending in self._pending.items() if pending.expires_at <= now]
        for token in expired:
            self._pending.pop(token, None)


confirmation_manager = ConfirmationManager()

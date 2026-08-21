"""Process-local cancellation state shared by Agent chat adapters and provider."""
from __future__ import annotations

from threading import Lock

_LOCK = Lock()
_ABORTED: set[str] = set()


def request_abort(session_gid: str) -> None:
    with _LOCK:
        _ABORTED.add(session_gid)


def consume_abort(session_gid: str) -> bool:
    with _LOCK:
        if session_gid not in _ABORTED:
            return False
        _ABORTED.remove(session_gid)
        return True


__all__ = ["consume_abort", "request_abort"]

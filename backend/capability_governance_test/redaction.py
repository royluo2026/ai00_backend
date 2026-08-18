"""Recursive, fail-closed redaction for governance-to-Agent data."""
from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any


REDACTED = "[REDACTED]"

_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|authorization|cookie|credential|db(?:[_-]?(?:url|uri))?|"
    r"pass(?:word)?|secret|token|url|uri|payload)",
    re.IGNORECASE,
)
_SENSITIVE_VALUE = re.compile(
    r"(?:[a-z][a-z0-9+.-]*://|(?:api[_-]?key|authorization|password|secret|token)\s*[=:])",
    re.IGNORECASE,
)


def redact(value: Any) -> Any:
    """Return a recursive copy with credentials, URLs, and business payloads removed."""
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if _SENSITIVE_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, set | frozenset):
        return tuple(sorted((redact(item) for item in value), key=repr))
    if isinstance(value, str) and _SENSITIVE_VALUE.search(value):
        return REDACTED
    return value


__all__ = ["REDACTED", "redact"]

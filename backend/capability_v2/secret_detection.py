"""Canonical secret detection shared by capability projections and owner services."""
from __future__ import annotations

import re
from typing import Any, Mapping

_SENSITIVE_PARTS = {
    "secret", "password", "passwd", "pwd", "token", "credential", "privatekey",
    "accesskey", "apikey", "authorization", "session", "cookie", "email", "phone",
    "mobile", "idcard", "filepath", "localpath", "rawpath",
}
_CREDENTIAL_URI = re.compile(r"^[a-z][a-z0-9+.-]*://[^\s/:]+:[^\s/@]+@", re.IGNORECASE)
_PEM = re.compile(r"-----BEGIN [A-Z0-9 ]*(?:PRIVATE KEY|CERTIFICATE)-----", re.IGNORECASE)
_TEXT_REDACTIONS = (
    (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE), "[redacted-email]"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]+=*", re.IGNORECASE), "Bearer [redacted]"),
    (re.compile(r"\b(?:api[_-]?key|access[_-]?key|password|passwd|pwd|secret|token)\s*[:=]\s*\S+", re.IGNORECASE), "[redacted-credential]"),
    (_CREDENTIAL_URI, "[redacted-credential-uri]"),
    (re.compile(r"-----BEGIN [A-Z0-9 ]*(?:PRIVATE KEY|CERTIFICATE)-----[\s\S]*?-----END [A-Z0-9 ]*(?:PRIVATE KEY|CERTIFICATE)-----", re.IGNORECASE), "[redacted-pem]"),
    (re.compile(r"\b[A-Za-z]:\\[^\s;]+"), "[redacted-path]"),
    (re.compile(r"(?<![A-Za-z0-9])/(?:home|Users|private|var|etc)/[^\s;]+"), "[redacted-path]"),
)

def is_sensitive_key(key: object) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
    return any(part in normalized for part in _SENSITIVE_PARTS)

def contains_secret(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(is_sensitive_key(key) or contains_secret(child) for key, child in value.items())
    if isinstance(value, (list, tuple, set)):
        return any(contains_secret(child) for child in value)
    if isinstance(value, str):
        return bool(_CREDENTIAL_URI.search(value.strip()) or _PEM.search(value))
    return False

def redact_text(value: str) -> tuple[str, bool]:
    text, redacted = str(value), False
    for pattern, replacement in _TEXT_REDACTIONS:
        text, count = pattern.subn(replacement, text)
        redacted = redacted or bool(count)
    return text, redacted

__all__ = ["contains_secret", "is_sensitive_key", "redact_text"]

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import base64
import hashlib
import hmac
import os
from typing import Any, Mapping


def canvas_token_secret(value: str | bytes | None = None) -> bytes:
    raw = value if value is not None else os.getenv("JWT_SECRET", "")
    secret = raw if isinstance(raw, bytes) else str(raw).encode("utf-8")
    if not secret:
        raise RuntimeError("JWT_SECRET is required for Agent canvas bearer tokens")
    return secret


def derive_canvas_token(
    secret: str | bytes, run_id: str, purpose: str, revision: int = 0,
) -> str:
    message = f"agent-canvas-v1\0{purpose}\0{run_id}\0{int(revision)}".encode("utf-8")
    digest = hmac.new(canvas_token_secret(secret), message, hashlib.sha256).digest()
    encoded = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"{purpose}_{encoded}"


def canvas_token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canvas_token_matches(
    supplied: str, secret: str | bytes, run_id: str, purpose: str, revision: int = 0,
) -> bool:
    return hmac.compare_digest(
        str(supplied), derive_canvas_token(secret, run_id, purpose, revision),
    )


def canvas_result_template(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        value = asdict(value)
    result = dict(value) if isinstance(value, Mapping) else {}
    result.pop("run_token", None)
    result.pop("pause_token", None)
    return result


def materialize_canvas_result(
    template: Mapping[str, Any], secret: str | bytes, run_id: str,
) -> dict[str, Any]:
    result = dict(template)
    revision = int(result.get("revision") or 0)
    result["run_token"] = derive_canvas_token(secret, run_id, "run")
    result["pause_token"] = (
        derive_canvas_token(secret, run_id, "pause", revision)
        if result.get("status") == "paused" else None
    )
    return result


__all__ = [
    "canvas_result_template", "canvas_token_hash", "canvas_token_matches",
    "canvas_token_secret", "derive_canvas_token", "materialize_canvas_result",
]

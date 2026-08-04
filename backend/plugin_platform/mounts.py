"""Short-lived signed mount URLs for opaque-origin Web Plugin iframes."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from urllib.parse import quote


class MountTokenError(PermissionError):
    pass


@dataclass(frozen=True)
class MountClaims:
    tenant_gid: str
    plugin_id: str
    version: str
    artifact_sha256: str
    expires_at: int


def _secret() -> bytes:
    value = os.getenv("AI00_PLUGIN_MOUNT_SECRET", "").encode("utf-8")
    if len(value) < 32:
        raise MountTokenError("AI00_PLUGIN_MOUNT_SECRET must contain at least 32 bytes")
    return value


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_mount_token(*, tenant_gid: str, plugin_id: str, version: str, artifact_sha256: str, ttl_seconds: int = 300) -> str:
    ttl_seconds = max(30, min(int(ttl_seconds), 600))
    payload = {"t": tenant_gid, "p": plugin_id, "v": version, "h": artifact_sha256, "exp": int(time.time()) + ttl_seconds, "n": secrets.token_urlsafe(12)}
    encoded = _encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    signature = _encode(hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def verify_mount_token(token: str) -> MountClaims:
    try:
        encoded, supplied = token.split(".", 1)
        expected = _encode(hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, supplied): raise MountTokenError("invalid mount token signature")
        value = json.loads(_decode(encoded))
        claims = MountClaims(str(value["t"]), str(value["p"]), str(value["v"]), str(value["h"]), int(value["exp"]))
        if claims.expires_at < int(time.time()): raise MountTokenError("mount token expired")
        if len(claims.artifact_sha256) != 64: raise MountTokenError("invalid artifact binding")
        return claims
    except MountTokenError:
        raise
    except Exception as exc:
        raise MountTokenError("malformed mount token") from exc


def mount_url(token: str, plugin_id: str, version: str, entry: str) -> str:
    parts = [quote(part, safe="") for part in entry.replace("\\", "/").split("/")]
    return f"/api/v1/plugin-marketplace/assets/{quote(token, safe='.')}/{quote(plugin_id, safe='.')}/{quote(version, safe='.-')}/{'/'.join(parts)}"

"""Short-lived authenticated evidence for browser workspace cache reads."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from ..security.export_refs import ExportRefError, issue_export_ref, verify_export_ref


class CacheLeaseError(ValueError):
    pass


def permission_version(context: Any) -> int:
    canonical = json.dumps(
        {
            "user_gid": str(context.user_gid),
            "team_gid": str(context.team_gid or ""),
            "permissions": sorted(set(context.permissions)),
            "active_roles": sorted(set(context.active_roles)),
            "resource_refs": sorted(set(context.resource_refs)),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return int(hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12], 16) + 1


def issue_cache_lease(claims: dict[str, Any]) -> str:
    try:
        return issue_export_ref({"kind": "simulation-workspace-cache-read", **claims})
    except ExportRefError as exc:
        raise CacheLeaseError("cache_lease_signing_key_unavailable") from exc


def verify_cache_lease(lease: str, *, now_epoch: int | None = None) -> dict[str, Any]:
    try:
        claims = verify_export_ref(lease, now_epoch=now_epoch)
    except ExportRefError as exc:
        code = "cache_lease_expired" if str(exc) == "private_export_expired" else "cache_lease_invalid"
        raise CacheLeaseError(code) from exc
    if claims.get("kind") != "simulation-workspace-cache-read":
        raise CacheLeaseError("cache_lease_invalid")
    required = {
        "auth_subject_gid", "workspace_gid", "permission_version", "row_version",
        "cache_revision_hash", "expires_at_epoch",
    }
    if not required.issubset(claims):
        raise CacheLeaseError("cache_lease_invalid")
    return claims


__all__ = ["CacheLeaseError", "issue_cache_lease", "permission_version", "verify_cache_lease"]

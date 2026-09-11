"""Freeze a private workspace through the Base-owned Artifact service."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


class FreezeConflict(ValueError):
    pass


def _canonical_manifest(source: Mapping[str, Any], algorithms: Mapping[str, str]) -> bytes:
    manifest = {
        "schema": "ai00.simulation.environment-manifest.v1",
        "workspace_gid": str(source["workspace_gid"]),
        "version_gid": str(source["version_gid"]),
        "nodes": source.get("nodes", []),
        "bindings": source.get("bindings", []),
        "runtime_model": source.get("runtime_model"),
        "algorithms": dict(sorted((str(key), str(value)) for key, value in algorithms.items())),
    }
    return json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


class WorkspaceFreezeService:
    """Coordinates Artifact finalization and the Simulation-side DB commit.

    The repository owns durable idempotency. The small process cache only prevents a
    duplicate Artifact if one request is replayed through the same provider instance.
    """

    def __init__(self, repository, artifact_port) -> None:
        self.repository = repository
        self.artifact_port = artifact_port
        self._completed: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}

    def freeze(
        self, *, workspace_gid: str, tenant_gid: str, owner_gid: str,
        expected_row_version: int, idempotency_key: str,
        algorithms: Mapping[str, str], context,
    ) -> dict[str, Any]:
        source = self.repository.load_freeze_source(
            workspace_gid=workspace_gid, tenant_gid=tenant_gid, owner_gid=owner_gid,
        )
        tenant_gid = str(source.get("tenant_gid") or tenant_gid)
        if int(source["row_version"]) != int(expected_row_version):
            raise FreezeConflict("version_conflict")
        if source["version_status"] != "draft":
            raise FreezeConflict("workspace_version_not_draft")
        content = _canonical_manifest(source, algorithms)
        content_hash = "sha256:" + hashlib.sha256(content).hexdigest()
        replay_key = (str(workspace_gid), idempotency_key)
        replay = self._completed.get(replay_key)
        if replay:
            if replay[0] != content_hash:
                raise FreezeConflict("idempotency_conflict")
            return replay[1]
        find = getattr(self.repository, "find_freeze_result", None)
        if find:
            stored = find(workspace_gid=workspace_gid, idempotency_key=idempotency_key,
                          request_hash=content_hash)
            if stored is not None:
                self._completed[replay_key] = (content_hash, stored)
                return stored

        try:
            artifact_ref = self.artifact_port.create(
                content, "application/vnd.ai00.simulation-environment+json", context,
            )
        except Exception:
            self.repository.record_unavailable(
                workspace_gid=workspace_gid, version_gid=str(source["version_gid"]),
                tenant_gid=tenant_gid, owner_gid=owner_gid, idempotency_key=idempotency_key,
                content_hash=content_hash, status="unavailable",
            )
            raise
        try:
            result = self.repository.complete_freeze(
                workspace_gid=workspace_gid, tenant_gid=tenant_gid, owner_gid=owner_gid,
                version_gid=str(source["version_gid"]), expected_row_version=expected_row_version,
                idempotency_key=idempotency_key, content_hash=content_hash,
                artifact_ref=artifact_ref, algorithms=dict(algorithms),
            )
        except Exception:
            self.repository.record_orphan(
                workspace_gid=workspace_gid, version_gid=str(source["version_gid"]),
                tenant_gid=tenant_gid, owner_gid=owner_gid, idempotency_key=idempotency_key,
                content_hash=content_hash, artifact_ref=artifact_ref, status="orphaned",
            )
            raise
        self._completed[replay_key] = (content_hash, result)
        return result


__all__ = ["FreezeConflict", "WorkspaceFreezeService"]

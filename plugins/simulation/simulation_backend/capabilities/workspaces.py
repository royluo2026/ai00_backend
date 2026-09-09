"""Experimental private Simulation workspace Capability candidates.

These handlers remain outside the registered release until the later unified
human approval. Keeping registration separate prevents accidental exposure.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.platform_sdk.ids import next_gid

from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError,
    CapabilityContext,
    CapabilityOutput,
    CapabilitySpec,
    EvidenceRef,
)

from ..data.workspace_repository import WorkspaceRepository, WorkspaceRepositoryError
from ..application.workspace_freeze import FreezeConflict, WorkspaceFreezeService
from ..security.export_refs import export_ref_digest, issue_export_ref


class _ArtifactPort:
    @staticmethod
    def create(content, media_type, context):
        from backend.platform_sdk.artifacts import create_artifact
        return create_artifact(content, media_type, context)


def _scope(context: CapabilityContext) -> tuple[str, str]:
    tenant_gid, owner_gid = str(context.team_gid or ""), str(context.user_gid or "")
    if not tenant_gid or not owner_gid:
        raise CapabilityBusinessError("workspace_identity_required", "workspace_identity_required")
    return tenant_gid, owner_gid


def _evidence(data: Any, *, workspace_gid: str | None = None, action: str) -> tuple[EvidenceRef, ...]:
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    digest = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    reference = f"simulation://workspace/{workspace_gid}" if workspace_gid else "simulation://workspace/search"
    return (EvidenceRef(kind="simulation.workspace", reference=reference, digest=digest, summary=action),)


def _output(data: Any, *, workspace_gid: str | None = None, action: str) -> CapabilityOutput:
    return CapabilityOutput(data=data, evidence=_evidence(data, workspace_gid=workspace_gid, action=action))


class WorkspaceProvider:
    def __init__(self, repository: WorkspaceRepository | None = None, freeze_service=None) -> None:
        self.repository = repository or WorkspaceRepository()
        self.freeze_service = freeze_service or WorkspaceFreezeService(self.repository, _ArtifactPort())

    def create(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        name = str(payload.get("name") or "").strip()
        if not name or len(name) > 255:
            raise CapabilityBusinessError("workspace_name_invalid", "workspace_name_invalid")
        tenant_gid, owner_gid = _scope(context)
        try:
            data = self.repository.create(name=name, tenant_gid=tenant_gid, owner_gid=owner_gid)
            return _output(data, workspace_gid=str(data["workspace_gid"]), action="workspace_created")
        except WorkspaceRepositoryError as exc:
            raise CapabilityBusinessError(str(exc), str(exc)) from exc

    def search(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        tenant_gid, owner_gid = _scope(context)
        page_size = payload.get("page_size", 50)
        if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 100:
            raise CapabilityBusinessError("page_size_invalid", "page_size_invalid")
        cursor = payload.get("cursor")
        if cursor in (None, ""):
            offset = 0
        elif isinstance(cursor, str) and cursor.isdecimal():
            offset = int(cursor)
        else:
            raise CapabilityBusinessError("cursor_invalid", "cursor_invalid")
        data = self.repository.search(
            tenant_gid=tenant_gid, owner_gid=owner_gid, offset=offset, page_size=page_size,
        )
        return _output(data, action="workspace_search_completed")

    def get(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        tenant_gid, owner_gid = _scope(context)
        row = self.repository.get(str(payload.get("workspace_gid") or ""), tenant_gid=tenant_gid, owner_gid=owner_gid)
        if not row:
            raise CapabilityBusinessError("workspace_not_found", "workspace_not_found")
        return _output(row, workspace_gid=str(row["workspace_gid"]), action="workspace_loaded")

    def _mutate(self, operation: str, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        tenant_gid, owner_gid = _scope(context)
        try:
            expected = payload.get("expected_row_version")
            key = str(payload.get("idempotency_key") or "")
            if isinstance(expected, bool) or not isinstance(expected, int) or expected < 1:
                raise WorkspaceRepositoryError("expected_row_version_invalid")
            if not key or len(key) > 191:
                raise WorkspaceRepositoryError("idempotency_key_invalid")
            values = {k: v for k, v in payload.items() if k not in {"workspace_gid", "expected_row_version", "idempotency_key"}}
            data = self.repository.mutate(
                workspace_gid=str(payload.get("workspace_gid") or ""), tenant_gid=tenant_gid,
                owner_gid=owner_gid, expected_row_version=expected, idempotency_key=key,
                operation=operation, values=values,
            )
            return _output(data, workspace_gid=str(payload.get("workspace_gid") or ""), action=operation)
        except WorkspaceRepositoryError as exc:
            retryable = str(exc) in {"version_conflict"}
            raise CapabilityBusinessError(str(exc), str(exc), retryable=retryable) from exc

    def create_node(self, payload, context):
        return self._mutate("create_node", payload, context)

    def move_node(self, payload, context):
        return self._mutate("move_node", payload, context)

    def remove_node(self, payload, context):
        return self._mutate("remove_node", payload, context)

    def create_binding(self, payload, context):
        return self._mutate("create_binding", payload, context)

    def remove_binding(self, payload, context):
        return self._mutate("remove_binding", payload, context)

    def freeze(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        tenant_gid, owner_gid = _scope(context)
        try:
            data = self.freeze_service.freeze(
                workspace_gid=str(payload.get("workspace_gid") or ""), tenant_gid=tenant_gid,
                owner_gid=owner_gid, expected_row_version=payload.get("expected_row_version"),
                idempotency_key=str(payload.get("idempotency_key") or ""),
                algorithms=payload.get("algorithms") or {}, context=context,
            )
            return _output(data, workspace_gid=str(data["workspace_gid"]), action="workspace_frozen")
        except (WorkspaceRepositoryError, FreezeConflict) as exc:
            raise CapabilityBusinessError(str(exc), str(exc), retryable=str(exc) == "version_conflict") from exc

    def export_for_import(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        tenant_gid, owner_gid = _scope(context)
        try:
            source = self.repository.get_saved_version(
                workspace_gid=str(payload.get("workspace_gid") or ""),
                version_gid=str(payload.get("version_gid") or ""),
                tenant_gid=tenant_gid, owner_gid=owner_gid,
            )
            if source.get("status") not in {"saved", "frozen"} or not source.get("content_hash"):
                raise WorkspaceRepositoryError("source_version_not_immutable")
            seconds = int(payload.get("expires_in_seconds", 300))
            now = datetime.now(timezone.utc); expires_at = now + timedelta(seconds=seconds)
            consumer = f'{payload["consumer_capability_id"]}@{payload["consumer_major_version"]}'
            claims = {
                "actor_gid": owner_gid, "tenant_gid": tenant_gid,
                "target_personal_space_gid": str(payload["target_personal_space_gid"]),
                "target_repository_gid": str(payload["target_repository_gid"]),
                "consumer": consumer, "workspace_gid": str(source["workspace_gid"]),
                "version_gid": str(source["version_gid"]), "content_hash": str(source["content_hash"]),
                "expires_at_epoch": int(expires_at.timestamp()),
            }
            reference = issue_export_ref(claims)
            self.repository.record_export_ref(
                export_gid=str(next_gid()), workspace_gid=claims["workspace_gid"],
                version_gid=claims["version_gid"], tenant_gid=tenant_gid, owner_gid=owner_gid,
                target_personal_space_gid=claims["target_personal_space_gid"],
                target_repository_gid=claims["target_repository_gid"],
                consumer_capability_id=str(payload["consumer_capability_id"]),
                consumer_major_version=int(payload["consumer_major_version"]),
                content_hash=claims["content_hash"], token_digest=export_ref_digest(reference),
                idempotency_key=str(payload["idempotency_key"]), expires_at=expires_at,
            )
            return _output({"export_ref": reference, "content_hash": claims["content_hash"],
                            "consumer": consumer, "expires_at": expires_at.isoformat()},
                           workspace_gid=claims["workspace_gid"], action="workspace_version_exported")
        except WorkspaceRepositoryError as exc:
            raise CapabilityBusinessError(str(exc), str(exc)) from exc


def candidate_specs(provider: WorkspaceProvider | None = None) -> tuple[tuple[CapabilitySpec, Any], ...]:
    selected = provider or WorkspaceProvider()
    common = dict(owner="simulation", plugin_callable=True, permissions=("simulation.use",),
                  tags=("simulation", "workspace", "experimental"))
    gid = {"type": "string", "pattern": "^[1-9][0-9]*$"}
    node = {"type": "object", "required": ["node_gid", "parent_gid", "node_type", "name", "position", "row_version"],
            "properties": {"node_gid": gid, "parent_gid": {"type": ["string", "null"], "pattern": "^[1-9][0-9]*$"},
                           "node_type": {"type": "string", "enum": ["line", "station", "process", "operation"]},
                           "name": {"type": "string"}, "position": {"type": "integer", "minimum": 0},
                           "row_version": {"type": "integer", "minimum": 1}}, "additionalProperties": False}
    binding = {"type": "object", "required": ["binding_gid", "node_gid", "occurrence_gid", "role", "row_version"],
               "properties": {"binding_gid": gid, "node_gid": gid, "occurrence_gid": gid,
                              "role": {"type": "string", "enum": ["load", "operate"]},
                              "row_version": {"type": "integer", "minimum": 1}}, "additionalProperties": False}
    workspace = {"type": "object", "required": ["workspace_gid", "version_gid", "name", "status", "row_version", "nodes", "bindings"],
                 "properties": {"workspace_gid": gid, "version_gid": gid, "name": {"type": "string"},
                                "status": {"type": "string"}, "row_version": {"type": "integer", "minimum": 1},
                                "nodes": {"type": "array", "items": node},
                                "bindings": {"type": "array", "items": binding}}, "additionalProperties": False}
    workspace_summary = {"type": "object", "required": ["workspace_gid", "version_gid", "name", "status", "row_version"],
                         "properties": {"workspace_gid": gid, "version_gid": gid, "name": {"type": "string"},
                                        "status": {"type": "string"}, "row_version": {"type": "integer", "minimum": 1},
                                        "updated_at": {"type": "string"}}, "additionalProperties": False}
    search_output = {"type": "object", "required": ["items", "next_cursor"],
                     "properties": {"items": {"type": "array", "maxItems": 100, "items": workspace_summary},
                                    "next_cursor": {"type": ["string", "null"], "pattern": "^[0-9]+$"}},
                     "additionalProperties": False}
    cas = {
        "workspace_gid": gid,
        "expected_row_version": {"type": "integer", "minimum": 1},
        "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 191},
    }
    mutation_output = {
        "type": "object", "required": ["entity_gid", "row_version", "patch"],
        "properties": {"entity_gid": gid, "row_version": {"type": "integer", "minimum": 2},
                       "patch": {"type": "object"}}, "additionalProperties": False,
    }
    return (
        (CapabilitySpec(id="simulation.environment.workspace.create", version=1,
                        description="Create a private versioned simulation workspace.", risk="write",
                        confirmation="none", input_schema={"type": "object", "required": ["name"],
                        "properties": {"name": {"type": "string", "minLength": 1, "maxLength": 255}},
                        "additionalProperties": False}, output_schema=workspace, **common), selected.create),
        (CapabilitySpec(id="simulation.environment.workspace.search", version=1,
                        description="Search the current user's private simulation workspaces.",
                        input_schema={"type": "object", "properties": {
                            "cursor": {"type": "string", "pattern": "^[0-9]+$"},
                            "page_size": {"type": "integer", "minimum": 1, "maximum": 100}},
                            "additionalProperties": False}, output_schema=search_output, **common), selected.search),
        (CapabilitySpec(id="simulation.environment.workspace.get", version=1,
                        description="Read one current user's private simulation workspace.",
                        input_schema={"type": "object", "required": ["workspace_gid"],
                                      "properties": {"workspace_gid": gid}, "additionalProperties": False},
                        output_schema=workspace, **common), selected.get),
        (CapabilitySpec(id="simulation.environment.structure_node.create", version=1,
                        description="Create one node in a private simulation workspace.", risk="write",
                        confirmation="none", idempotent=True, input_schema={"type": "object",
                        "required": ["workspace_gid", "expected_row_version", "idempotency_key", "node_type", "name"],
                        "properties": {**cas, "parent_gid": {"type": ["string", "null"], "pattern": "^[1-9][0-9]*$"},
                        "node_type": {"type": "string", "enum": ["line", "station", "process", "operation"]},
                        "name": {"type": "string", "minLength": 1, "maxLength": 255}}, "additionalProperties": False},
                        output_schema=mutation_output, **common), selected.create_node),
        (CapabilitySpec(id="simulation.environment.structure_node.move", version=1,
                        description="Move one node in a private simulation workspace.", risk="write",
                        confirmation="none", idempotent=True, input_schema={"type": "object",
                        "required": ["workspace_gid", "expected_row_version", "idempotency_key", "node_gid"],
                        "properties": {**cas, "node_gid": gid, "parent_gid": {"type": ["string", "null"], "pattern": "^[1-9][0-9]*$"}},
                        "additionalProperties": False}, output_schema=mutation_output, **common), selected.move_node),
        (CapabilitySpec(id="simulation.environment.structure_node.remove", version=1,
                        description="Soft-delete one simulation workspace subtree.", risk="write",
                        confirmation="none", idempotent=True, input_schema={"type": "object",
                        "required": ["workspace_gid", "expected_row_version", "idempotency_key", "node_gid"],
                        "properties": {**cas, "node_gid": gid}, "additionalProperties": False},
                        output_schema=mutation_output, **common), selected.remove_node),
        (CapabilitySpec(id="simulation.environment.binding.create", version=1,
                        description="Bind one VM occurrence to one simulation workspace node.", risk="write",
                        confirmation="none", idempotent=True, input_schema={"type": "object",
                        "required": ["workspace_gid", "expected_row_version", "idempotency_key", "node_gid", "occurrence_gid", "role"],
                        "properties": {**cas, "node_gid": gid, "occurrence_gid": gid,
                        "role": {"type": "string", "enum": ["load", "operate"]}}, "additionalProperties": False},
                        output_schema=mutation_output, **common), selected.create_binding),
        (CapabilitySpec(id="simulation.environment.binding.remove", version=1,
                        description="Remove one VM occurrence binding from a simulation workspace.", risk="write",
                        confirmation="none", idempotent=True, input_schema={"type": "object",
                        "required": ["workspace_gid", "expected_row_version", "idempotency_key", "binding_gid"],
                        "properties": {**cas, "binding_gid": gid}, "additionalProperties": False},
                        output_schema=mutation_output, **common), selected.remove_binding),
        (CapabilitySpec(id="simulation.environment.version.freeze", version=1,
                        description="Freeze one private simulation workspace version as an immutable Base Artifact.",
                        risk="write", confirmation="none", idempotent=True,
                        input_schema={"type": "object",
                        "required": ["workspace_gid", "expected_row_version", "idempotency_key", "algorithms"],
                        "properties": {**cas, "algorithms": {"type": "object", "maxProperties": 16,
                        "additionalProperties": {"type": "string", "minLength": 1, "maxLength": 64}}},
                        "additionalProperties": False},
                        output_schema={"type": "object",
                        "required": ["workspace_gid", "version_gid", "status", "content_hash", "artifact_ref"],
                        "properties": {"workspace_gid": gid, "version_gid": gid,
                        "status": {"type": "string", "const": "frozen"},
                        "content_hash": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
                        "artifact_ref": {"type": "object"}}, "additionalProperties": False}, **common), selected.freeze),
        (CapabilitySpec(id="simulation.environment.workspace_version.export_for_import", version=1,
                        description="Issue an owner-scoped reference to one immutable private workspace version.",
                        risk="write", confirmation="none", idempotent=True,
                        input_schema={"type":"object","required":["workspace_gid","version_gid","target_personal_space_gid","target_repository_gid","consumer_capability_id","consumer_major_version","expires_in_seconds","idempotency_key"],
                        "properties":{"workspace_gid":gid,"version_gid":gid,"target_personal_space_gid":gid,
                        "target_repository_gid":gid,"consumer_capability_id":{"type":"string","const":"craft.bop.managed_personal_space.import.preview"},
                        "consumer_major_version":{"type":"integer","const":1},"expires_in_seconds":{"type":"integer","minimum":60,"maximum":900},
                        "idempotency_key":{"type":"string","minLength":1,"maxLength":191}},"additionalProperties":False},
                        output_schema={"type":"object","required":["export_ref","content_hash","consumer","expires_at"],
                        "properties":{"export_ref":{"type":"string","minLength":32},"content_hash":{"type":"string","pattern":"^sha256:[0-9a-f]{64}$"},
                        "consumer":{"type":"string","const":"craft.bop.managed_personal_space.import.preview@1"},"expires_at":{"type":"string"}},
                        "additionalProperties":False}, **common), selected.export_for_import),
    )


__all__ = ["WorkspaceProvider", "candidate_specs"]

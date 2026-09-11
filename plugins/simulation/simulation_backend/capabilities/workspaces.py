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
from ..domain.cache_lease import CacheLeaseError, issue_cache_lease, permission_version


class _ArtifactPort:
    @staticmethod
    def create(content, media_type, context):
        from backend.platform_sdk.artifacts import create_artifact
        return create_artifact(content, media_type, context)
    @staticmethod
    def read(reference, context):
        from backend.platform_sdk.artifacts import read_artifact
        return read_artifact(reference, context)


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
    def __init__(self, repository: WorkspaceRepository | None = None, freeze_service=None, clock=None) -> None:
        self.repository = repository or WorkspaceRepository()
        self.freeze_service = freeze_service or WorkspaceFreezeService(self.repository, _ArtifactPort())
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def create(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        values = self._metadata(payload)
        tenant_gid, owner_gid = _scope(context)
        try:
            data = self.repository.create(**values, tenant_gid=tenant_gid, owner_gid=owner_gid)
            return _output(data, workspace_gid=str(data["workspace_gid"]), action="workspace_created")
        except WorkspaceRepositoryError as exc:
            raise CapabilityBusinessError(str(exc), str(exc)) from exc

    @staticmethod
    def _metadata(payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        version_label = str(payload.get("version_label") or "V1").strip()
        review_type = str(payload.get("review_type") or "other")
        status = str(payload.get("status") or "active")
        visibility = str(payload.get("visibility") or "private")
        project_gids = payload.get("project_gids") or []
        primary = payload.get("primary_project_gid")
        if not name or len(name) > 255:
            raise CapabilityBusinessError("workspace_name_invalid", "workspace_name_invalid")
        if not version_label or len(version_label) > 128:
            raise CapabilityBusinessError("workspace_version_label_invalid", "workspace_version_label_invalid")
        if review_type not in {"node_review", "scattered_review", "other"}:
            raise CapabilityBusinessError("workspace_review_type_invalid", "workspace_review_type_invalid")
        if status not in {"active", "baseline", "frozen", "archived"}:
            raise CapabilityBusinessError("workspace_status_invalid", "workspace_status_invalid")
        if visibility not in {"private", "shared"}:
            raise CapabilityBusinessError("workspace_visibility_invalid", "workspace_visibility_invalid")
        if not isinstance(project_gids, list) or len(project_gids) > 50:
            raise CapabilityBusinessError("workspace_projects_invalid", "workspace_projects_invalid")
        normalized = []
        for value in project_gids:
            text = str(value or "")
            if not text.isdecimal() or int(text) <= 0 or text in normalized:
                raise CapabilityBusinessError("workspace_projects_invalid", "workspace_projects_invalid")
            normalized.append(text)
        primary = None if primary in (None, "") else str(primary)
        if primary is not None and primary not in normalized:
            raise CapabilityBusinessError("workspace_primary_project_invalid", "workspace_primary_project_invalid")
        if review_type == "node_review" and primary is None:
            raise CapabilityBusinessError("workspace_primary_project_required", "workspace_primary_project_required")
        return {"name": name, "review_type": review_type, "version_label": version_label,
                "status": status, "visibility": visibility, "project_gids": normalized,
                "primary_project_gid": primary}

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

    def cache_lease_get(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        tenant_gid, owner_gid = _scope(context)
        seconds = payload.get("expires_in_seconds", 300)
        if isinstance(seconds, bool) or not isinstance(seconds, int) or not 60 <= seconds <= 300:
            raise CapabilityBusinessError("cache_lease_ttl_invalid", "cache_lease_ttl_invalid")
        row = self.repository.get(
            str(payload.get("workspace_gid") or ""), tenant_gid=tenant_gid, owner_gid=owner_gid,
        )
        if not row:
            raise CapabilityBusinessError("workspace_not_found", "workspace_not_found")
        now = self.clock()
        expires_at = now + timedelta(seconds=seconds)
        data = {
            "auth_subject_gid": owner_gid,
            "workspace_gid": str(row["workspace_gid"]),
            "permission_version": permission_version(context),
            "row_version": int(row["row_version"]),
            "cache_revision_hash": str(row["cache_revision_hash"]),
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            "expires_in_seconds": seconds,
        }
        try:
            data["read_lease"] = issue_cache_lease({
                **data, "expires_at_epoch": int(expires_at.timestamp()),
            })
        except CacheLeaseError as exc:
            raise CapabilityBusinessError(str(exc), str(exc)) from exc
        return _output(data, workspace_gid=data["workspace_gid"], action="workspace_cache_lease_issued")

    def update(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        values = self._metadata(payload)
        return self._mutate("update_workspace", {**payload, **values}, context)

    def delete(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        tenant_gid, owner_gid = _scope(context)
        try:
            data = self.repository.delete(
                workspace_gid=str(payload.get("workspace_gid") or ""), tenant_gid=tenant_gid,
                owner_gid=owner_gid, expected_row_version=payload.get("expected_row_version"),
                idempotency_key=str(payload.get("idempotency_key") or ""),
            )
            return _output(data, workspace_gid=str(data["workspace_gid"]), action="workspace_deleted")
        except WorkspaceRepositoryError as exc:
            raise CapabilityBusinessError(str(exc), str(exc), retryable=str(exc) == "version_conflict") from exc

    def fork_preview(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        tenant_gid, actor_gid = _scope(context)
        name=str(payload.get("target_name") or "").strip();label=str(payload.get("target_version_label") or "V1").strip()
        fork_depth=str(payload.get("fork_depth") or "")
        visibility=str(payload.get("visibility") or "private")
        if not name or len(name)>255:raise CapabilityBusinessError("workspace_name_invalid","workspace_name_invalid")
        if not label or len(label)>128:raise CapabilityBusinessError("workspace_version_label_invalid","workspace_version_label_invalid")
        if fork_depth not in {"all","operation","process","role","station"}:raise CapabilityBusinessError("fork_depth_invalid","fork_depth_invalid")
        if visibility not in {"private","shared"}:raise CapabilityBusinessError("workspace_visibility_invalid","workspace_visibility_invalid")
        try:
            data=self.repository.create_fork_preview(workspace_gid=str(payload.get("source_workspace_gid") or ""),version_gid=str(payload.get("source_version_gid") or ""),target_name=name,target_version_label=label,fork_depth=fork_depth,visibility=visibility,tenant_gid=tenant_gid,actor_gid=actor_gid)
            return _output(data,workspace_gid=str(payload.get("source_workspace_gid") or ""),action="workspace_fork_previewed")
        except WorkspaceRepositoryError as exc:raise CapabilityBusinessError(str(exc),str(exc)) from exc

    def version_search(self,payload:dict[str,Any],context:CapabilityContext)->CapabilityOutput:
        tenant_gid,actor_gid=_scope(context)
        try:
            data=self.repository.search_saved_versions(workspace_gid=str(payload.get("workspace_gid") or ""),tenant_gid=tenant_gid,actor_gid=actor_gid)
            return _output(data,workspace_gid=str(payload.get("workspace_gid") or ""),action="workspace_versions_searched")
        except WorkspaceRepositoryError as exc:raise CapabilityBusinessError(str(exc),str(exc)) from exc

    def fork_apply(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        tenant_gid,actor_gid=_scope(context)
        try:
            plan=self.repository.get_fork_plan(preview_gid=str(payload.get("preview_gid") or ""),tenant_gid=tenant_gid,actor_gid=actor_gid,plan_hash=str(payload.get("plan_hash") or ""))
            content=self.freeze_service.artifact_port.read(plan["manifest_artifact_ref"],context)
            manifest=json.loads(content.decode("utf-8"))
            if manifest.get("schema")!="ai00.simulation.environment-manifest.v1" or str(manifest.get("workspace_gid"))!=str(plan["source_workspace_gid"]) or str(manifest.get("version_gid"))!=str(plan["source_version_gid"]):raise WorkspaceRepositoryError("fork_manifest_invalid")
            digest="sha256:"+hashlib.sha256(content).hexdigest()
            if digest!=plan["content_hash"]:raise WorkspaceRepositoryError("fork_manifest_changed")
            data=self.repository.apply_fork(plan=plan,manifest=manifest,tenant_gid=tenant_gid,actor_gid=actor_gid,idempotency_key=str(payload.get("idempotency_key") or ""))
            return _output(data,workspace_gid=str(data["workspace_gid"]),action="workspace_forked")
        except (WorkspaceRepositoryError,ValueError,KeyError,json.JSONDecodeError) as exc:raise CapabilityBusinessError(str(exc),str(exc)) from exc

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
    cache_revision = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
    node = {"type": "object", "required": ["node_gid", "parent_gid", "node_type", "name", "position", "row_version"],
            "properties": {"node_gid": gid, "parent_gid": {"type": ["string", "null"], "pattern": "^[1-9][0-9]*$"},
                           "node_type": {"type": "string", "enum": ["line", "station", "process", "operation"]},
                           "name": {"type": "string"}, "position": {"type": "integer", "minimum": 0},
                           "row_version": {"type": "integer", "minimum": 1}}, "additionalProperties": False}
    binding = {"type": "object", "required": ["binding_gid", "node_gid", "occurrence_gid", "role", "row_version"],
               "properties": {"binding_gid": gid, "node_gid": gid, "occurrence_gid": gid,
                              "role": {"type": "string", "enum": ["load", "operate"]},
                              "row_version": {"type": "integer", "minimum": 1}}, "additionalProperties": False}
    metadata = {"name": {"type": "string", "minLength": 1, "maxLength": 255},
                "review_type": {"type": "string", "enum": ["node_review", "scattered_review", "other"]},
                "version_label": {"type": "string", "minLength": 1, "maxLength": 128},
                "status": {"type": "string", "enum": ["active", "baseline", "frozen", "archived"]},
                "visibility": {"type": "string", "enum": ["private", "shared"]},
                "project_gids": {"type": "array", "maxItems": 50, "uniqueItems": True, "items": gid},
                "primary_project_gid": {"anyOf": [gid, {"type": "null"}]}}
    workspace = {"type": "object", "required": ["workspace_gid", "version_gid", "owner_gid", "is_owner", *metadata.keys(), "updated_at", "row_version", "cache_revision_hash", "nodes", "bindings"],
                 "properties": {"workspace_gid": gid, "version_gid": gid, "owner_gid": gid, "is_owner": {"type": "boolean"}, **metadata,
                                "updated_at": {"type": "string"}, "row_version": {"type": "integer", "minimum": 1},
                                "cache_revision_hash": cache_revision,
                                "nodes": {"type": "array", "items": node},
                                "bindings": {"type": "array", "items": binding}}, "additionalProperties": False}
    workspace_summary = {"type": "object", "required": ["workspace_gid", "version_gid", "owner_gid", "is_owner", *metadata.keys(), "updated_at", "row_version", "cache_revision_hash"],
                         "properties": {"workspace_gid": gid, "version_gid": gid, "owner_gid": gid, "is_owner": {"type": "boolean"}, **metadata,
                                        "updated_at": {"type": "string"}, "row_version": {"type": "integer", "minimum": 1},
                                        "cache_revision_hash": cache_revision}, "additionalProperties": False}
    search_output = {"type": "object", "required": ["items", "next_cursor"],
                     "properties": {"items": {"type": "array", "maxItems": 100, "items": workspace_summary},
                                    "next_cursor": {"type": ["string", "null"], "pattern": "^[0-9]+$"}},
                     "additionalProperties": False}
    cas = {
        "workspace_gid": gid,
        "expected_row_version": {"type": "integer", "minimum": 1},
        "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 191},
    }
    patch_schema = {"type": "object", "required": ["op"], "properties": {
        "op": {"type": "string", "enum": ["update_workspace", "create", "move", "remove", "bind", "unbind"]},
        "node_gid": gid, "parent_gid": {"anyOf": [gid, {"type": "null"}]},
        "node_type": {"type": "string", "enum": ["line", "station", "process", "operation"]},
        "name": {"type": "string"}, "position": {"type": "integer", "minimum": 0},
        "removed_node_gids": {"type": "array", "items": gid}, "binding_gid": gid,
        "occurrence_gid": gid, "role": {"type": "string", "enum": ["load", "operate"]},
        "review_type": metadata["review_type"], "version_label": metadata["version_label"],
        "status": metadata["status"], "visibility": metadata["visibility"],
        "project_gids": metadata["project_gids"], "primary_project_gid": metadata["primary_project_gid"],
    }, "additionalProperties": False}
    mutation_output = {
        "type": "object", "required": ["entity_gid", "row_version", "cache_revision_hash", "patch"],
        "properties": {"entity_gid": gid, "row_version": {"type": "integer", "minimum": 2},
                       "cache_revision_hash": cache_revision,
                       "patch": patch_schema}, "additionalProperties": False,
    }
    return (
        (CapabilitySpec(id="simulation.environment.workspace.create", version=1,
                        description="Create a versioned private or shared simulation workspace.", risk="write",
                        confirmation="none", input_schema={"type": "object", "required": ["name"],
                        "properties": metadata,
                        "additionalProperties": False}, output_schema=workspace, **common), selected.create),
        (CapabilitySpec(id="simulation.environment.workspace.search", version=1,
                        description="Search simulation workspaces owned by the caller or shared with authenticated users.",
                        input_schema={"type": "object", "properties": {
                            "cursor": {"type": "string", "pattern": "^[0-9]+$"},
                            "page_size": {"type": "integer", "minimum": 1, "maximum": 100}},
                            "additionalProperties": False}, output_schema=search_output, **common), selected.search),
        (CapabilitySpec(id="simulation.environment.workspace.get", version=1,
                        description="Read one simulation workspace owned by the caller or shared with authenticated users.",
                        input_schema={"type": "object", "required": ["workspace_gid"],
                                      "properties": {"workspace_gid": gid}, "additionalProperties": False},
                        output_schema=workspace, **common), selected.get),
        (CapabilitySpec(id="simulation.environment.workspace.cache_lease.get", version=1,
                        description="Authorize one caller to reuse one exact cached simulation workspace projection for at most five minutes.",
                        input_schema={"type": "object", "required": ["workspace_gid"],
                                      "properties": {"workspace_gid": gid,
                                                     "expires_in_seconds": {"type": "integer", "minimum": 60, "maximum": 300}},
                                      "additionalProperties": False},
                        output_schema={"type": "object",
                                       "required": ["auth_subject_gid", "workspace_gid", "permission_version", "row_version", "cache_revision_hash", "expires_at", "expires_in_seconds", "read_lease"],
                                       "properties": {"auth_subject_gid": gid, "workspace_gid": gid,
                                                      "permission_version": {"type": "integer", "minimum": 1},
                                                      "row_version": {"type": "integer", "minimum": 1},
                                                      "cache_revision_hash": cache_revision,
                                                      "expires_at": {"type": "string"},
                                                      "expires_in_seconds": {"type": "integer", "minimum": 60, "maximum": 300},
                                                      "read_lease": {"type": "string", "minLength": 32}},
                                       "additionalProperties": False}, **common), selected.cache_lease_get),
        (CapabilitySpec(id="simulation.environment.workspace.update", version=1,
                        description="Update metadata of one owner-controlled simulation workspace.", risk="write",
                        confirmation="none", idempotent=True, input_schema={"type": "object",
                        "required": ["workspace_gid", "expected_row_version", "idempotency_key", *metadata.keys()],
                        "properties": {**cas, **metadata}, "additionalProperties": False},
                        output_schema=mutation_output, **common), selected.update),
        (CapabilitySpec(id="simulation.environment.workspace.delete", version=1,
                        description="Logically delete one owner-controlled simulation workspace.", risk="write",
                        confirmation="none", input_schema={"type": "object",
                        "required": ["workspace_gid", "expected_row_version", "idempotency_key"],
                        "properties": cas, "additionalProperties": False},
                        output_schema={"type": "object",
                        "required": ["workspace_gid", "deleted", "deletion_gid", "row_version", "cache_revision_hash"],
                        "properties": {"workspace_gid": gid, "deleted": {"const": True},
                                       "deletion_gid": gid, "row_version": {"type": "integer", "minimum": 2},
                                       "cache_revision_hash": cache_revision},
                        "additionalProperties": False}, **common), selected.delete),
        (CapabilitySpec(id="simulation.environment.workspace.fork.preview", version=1,
                        description="Preview a private workspace Fork from an immutable readable version.",risk="write",confirmation="none",
                        input_schema={"type":"object","required":["source_workspace_gid","source_version_gid","target_name","target_version_label","fork_depth"],
                        "properties":{"source_workspace_gid":gid,"source_version_gid":gid,"target_name":metadata["name"],"target_version_label":metadata["version_label"],"fork_depth":{"type":"string","enum":["all","operation","process","role","station"]},"visibility":metadata["visibility"]},"additionalProperties":False},
                        output_schema={"type":"object","required":["preview_gid","plan_hash","source_workspace_gid","source_version_gid","source_content_hash","target_name","target_version_label","fork_depth","visibility","expires_at"],
                        "properties":{"preview_gid":gid,"plan_hash":{"type":"string","pattern":"^sha256:[0-9a-f]{64}$"},"source_workspace_gid":gid,"source_version_gid":gid,"source_content_hash":{"type":"string","pattern":"^sha256:[0-9a-f]{64}$"},"target_name":metadata["name"],"target_version_label":metadata["version_label"],"fork_depth":{"type":"string","enum":["all","operation","process","role","station"]},"visibility":metadata["visibility"],"expires_at":{"type":"string"}},"additionalProperties":False},**common),selected.fork_preview),
        (CapabilitySpec(id="simulation.environment.workspace.fork.apply", version=1,
                        description="Apply a validated private workspace Fork without mutating its immutable source.",risk="write",confirmation="none",idempotent=True,
                        input_schema={"type":"object","required":["preview_gid","plan_hash","idempotency_key"],"properties":{"preview_gid":gid,"plan_hash":{"type":"string","pattern":"^sha256:[0-9a-f]{64}$"},"idempotency_key":{"type":"string","minLength":1,"maxLength":191}},"additionalProperties":False},
                        output_schema={"type":"object","required":["workspace_gid","version_gid","owner_gid","is_owner",*metadata.keys(),"updated_at","row_version","nodes","bindings","fork_base"],"properties":{**workspace["properties"],"fork_base":{"type":"object","required":["workspace_gid","version_gid","content_hash","fork_depth"],"properties":{"workspace_gid":gid,"version_gid":gid,"content_hash":{"type":"string","pattern":"^sha256:[0-9a-f]{64}$"},"fork_depth":{"type":"string","enum":["all","operation","process","role","station"]}},"additionalProperties":False}},"additionalProperties":False},**common),selected.fork_apply),
        (CapabilitySpec(id="simulation.environment.workspace_version.search",version=1,
                        description="Search readable immutable versions of one owned or shared Simulation workspace.",
                        input_schema={"type":"object","required":["workspace_gid"],"properties":{"workspace_gid":gid},"additionalProperties":False},
                        output_schema={"type":"object","required":["items"],"properties":{"items":{"type":"array","items":{"type":"object","required":["version_gid","workspace_gid","sequence","status","content_hash","created_at"],"properties":{"version_gid":gid,"workspace_gid":gid,"sequence":{"type":"integer","minimum":1},"status":{"type":"string","enum":["saved","frozen"]},"content_hash":{"type":"string","pattern":"^sha256:[0-9a-f]{64}$"},"created_at":{"type":"string"}},"additionalProperties":False}}},"additionalProperties":False},**common),selected.version_search),
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
                        "required": ["workspace_gid", "version_gid", "status", "content_hash", "artifact_ref", "row_version", "cache_revision_hash"],
                        "properties": {"workspace_gid": gid, "version_gid": gid,
                        "status": {"type": "string", "const": "frozen"},
                        "content_hash": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
                        "artifact_ref": {"type": "object"}, "row_version": {"type": "integer", "minimum": 2},
                        "cache_revision_hash": cache_revision}, "additionalProperties": False}, **common), selected.freeze),
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

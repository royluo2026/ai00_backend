"""Experimental Capability candidates for the BOP repository foundation."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError, CapabilityContext, CapabilityOutput, CapabilitySpec, EvidenceRef,
)
from backend.base.bop_edit_authorization import get_bop_edit_scope

from ..data.bop_repository import BopRepositoryError, BopRepositoryStore
from ..data.bop_repository_mysql import MysqlBopRepositoryStore


def _scope(context: CapabilityContext) -> tuple[str, str]:
    tenant_gid, actor_gid = str(context.team_gid or ""), str(context.user_gid or "")
    if not tenant_gid or not actor_gid:
        raise CapabilityBusinessError("repository_identity_required", "repository_identity_required")
    return tenant_gid, actor_gid


def _json_safe(data: Any, key: str = "") -> Any:
    """Keep Snowflake identifiers exact across the JSON/JavaScript boundary."""
    if isinstance(data, dict):
        return {name: _json_safe(value, name) for name, value in data.items()}
    if isinstance(data, (list, tuple)):
        return [_json_safe(value, key) for value in data]
    if data is not None and (key in {"gid", "created_by", "updated_by", "deleted_by"} or key.endswith("_gid")):
        return str(data)
    return json.loads(json.dumps(data, default=str))


def _output(data: dict[str, Any], action: str) -> CapabilityOutput:
    digest = "sha256:" + hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
    gid = data.get("repository_gid") or data.get("space_gid") or data.get("version_gid") or "search"
    serializable = _json_safe(data)
    return CapabilityOutput(data=serializable, evidence=(EvidenceRef(
        kind="craft.bop.repository", reference=f"craft://bop-repository/{gid}", digest=digest, summary=action,
    ),))


class RepositoryProvider:
    def __init__(self, store: BopRepositoryStore | None = None) -> None:
        self.store = store or MysqlBopRepositoryStore()

    def _call(self, method: str, payload: dict[str, Any], context: CapabilityContext, **values: Any) -> CapabilityOutput:
        tenant_gid, actor_gid = _scope(context)
        try:
            result = getattr(self.store, method)(tenant_gid=tenant_gid, actor_gid=actor_gid, **values)
            return _output(result, method)
        except BopRepositoryError as exc:
            code = str(exc)
            raise CapabilityBusinessError(code, code, retryable=code == "resource_version_conflict") from exc

    @staticmethod
    def _page(payload: dict[str, Any]) -> tuple[int, int]:
        size = payload.get("page_size", 50)
        cursor = payload.get("cursor", "0")
        if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= 100:
            raise CapabilityBusinessError("page_size_invalid", "page_size_invalid")
        if cursor in (None, ""): cursor = "0"
        if not isinstance(cursor, str) or not cursor.isdecimal():
            raise CapabilityBusinessError("cursor_invalid", "cursor_invalid")
        return int(cursor), size

    def search_repositories(self, p, c):
        offset, size = self._page(p)
        return self._call("search_repositories", p, c, project_gid=p.get("project_gid"), offset=offset, page_size=size)
    def get_repository(self, p, c): return self._call("get_repository", p, c, repository_gid=p["repository_gid"])
    def create_repository(self, p, c): return self._call("create_repository", p, c, project_gid=p["project_gid"], idempotency_key=p["idempotency_key"])
    def archive_repository(self, p, c): return self._lifecycle("archive_repository", p, c)
    def restore_repository(self, p, c): return self._lifecycle("restore_repository", p, c)
    def delete_repository(self, p, c): return self._lifecycle("delete_repository", p, c, reason=p.get("reason", ""))
    def _lifecycle(self, method, p, c, **extra):
        return self._call(method, p, c, repository_gid=p["repository_gid"], expected_row_version=p["expected_row_version"], idempotency_key=p["idempotency_key"], **extra)
    def set_baseline(self, p, c):
        return self._call("set_baseline", p, c, repository_gid=p["repository_gid"], version_gid=p["version_gid"], expected_row_version=p["expected_row_version"], idempotency_key=p["idempotency_key"])
    def search_spaces(self, p, c):
        offset, size = self._page(p)
        return self._call("search_spaces", p, c, repository_gid=p["repository_gid"], owner_gid=str(c.user_gid or ""), offset=offset, page_size=size)
    def get_space(self, p, c):
        tenant_gid, actor_gid = _scope(c)
        try:
            data = self.store.get_space(space_gid=p["space_gid"], tenant_gid=tenant_gid, actor_gid=actor_gid)
        except BopRepositoryError as exc:
            raise CapabilityBusinessError(str(exc), str(exc)) from exc
        nodes = data.get("nodes") or []
        if data.get("space_kind") == "managed_personal" and data.get("project_gid"):
            line_gids = tuple(dict.fromkeys(str(node["line_gid"]) for node in nodes if node.get("line_gid")))
            access = get_bop_edit_scope(
                tenant_gid=tenant_gid, user_gid=actor_gid,
                active_roles=tuple(c.active_roles or ()), project_gid=str(data["project_gid"]),
                line_gids=line_gids,
            )
            editable = set(access["editable_line_gids"])
            for node in nodes:
                node["access_mode"] = "editable" if access["project_wide"] or node.get("line_gid") in editable else "read_only"
            data["access_scope"] = "project" if access["project_wide"] else ("line" if editable else "read_only")
        else:
            for node in nodes:
                node["access_mode"] = "read_only"
            data["access_scope"] = "read_only"
        return _output(data, "get_space")
    def search_versions(self, p, c):
        offset, size = self._page(p)
        return self._call("search_space_versions", p, c, space_gid=p["space_gid"], offset=offset, page_size=size)
    def get_version(self, p, c): return self._call("get_space_version", p, c, version_gid=p["version_gid"])
    def save_version(self, p, c):
        return self._call("save_space_version", p, c, space_gid=p["space_gid"], expected_head_version=p["expected_head_version"], version_kind=p.get("version_kind", "saved"), source_refs=p.get("source_refs", []), algorithm_versions=p.get("algorithm_versions", {}), idempotency_key=p["idempotency_key"])
    def freeze_version(self, p, c):
        return self._call("freeze_team_space", p, c, space_gid=p["space_gid"], expected_head_version=p["expected_head_version"], version_gid=p["version_gid"], idempotency_key=p["idempotency_key"])
    def delete_personal(self, p, c):
        tenant_gid, actor_gid = _scope(c)
        try:
            data = self.store.delete_personal_space(space_gid=p["space_gid"], tenant_gid=tenant_gid, owner_gid=actor_gid, expected_row_version=p["expected_row_version"], idempotency_key=p["idempotency_key"])
            return _output(data, "delete_personal_space")
        except BopRepositoryError as exc:
            raise CapabilityBusinessError(str(exc), str(exc), retryable=str(exc) == "resource_version_conflict") from exc


def candidate_specs(store: BopRepositoryStore | None = None) -> tuple[tuple[CapabilitySpec, Callable[..., Any]], ...]:
    p = RepositoryProvider(store)
    gid = {"type": "string", "pattern": "^[1-9][0-9]*$"}
    key = {"type": "string", "minLength": 1, "maxLength": 191}
    page = {"cursor": {"type": "string", "pattern": "^[0-9]+$"}, "page_size": {"type": "integer", "minimum": 1, "maximum": 100}}
    def schema(properties, required=()): return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}
    identifier = {"type": ["string", "null"]}
    item = {"type": "object", "properties": {
        **{name: identifier for name in (
            "repository_gid", "project_gid", "baseline_version_gid", "space_gid", "owner_user_gid",
            "fork_base_version_gid", "frozen_version_gid", "head_gid", "version_gid", "parent_version_gid",
            "created_by",
        )},
        **{name: {"type": ["string", "null"]} for name in (
            "lifecycle_status", "space_kind", "display_name", "content_hash", "version_kind", "manifest_hash",
            "created_at", "updated_at",
        )},
        "row_version": {"type": "integer", "minimum": 0},
        "head_row_version": {"type": "integer", "minimum": 0},
    }, "additionalProperties": False}
    output = schema({
        "items": {"type": "array", "maxItems": 100, "items": item},
        "next_cursor": identifier,
        **{name: identifier for name in (
            "repository_gid", "space_gid", "version_gid", "project_gid", "team_space_gid", "head_gid",
            "baseline_version_gid", "lifecycle_status", "space_kind", "owner_user_gid", "frozen_version_gid",
            "manifest_hash", "version_kind", "deletion_gid", "deleted_at", "operation", "tenant_gid",
            "actor_gid", "idempotency_key", "fork_base_version_gid", "content_hash", "created_at",
            "updated_at",
        )},
        "row_version": {"type": "integer", "minimum": 0},
        "head_row_version": {"type": "integer", "minimum": 0},
        "offset": {"type": "integer", "minimum": 0},
        "page_size": {"type": "integer", "minimum": 1, "maximum": 100},
        "deleted": {"type": "boolean"},
        "access_scope": {"type": ["string", "null"], "enum": ["project", "line", "read_only", None]},
        "nodes": {"type": "array", "maxItems": 20000, "items": {"type": "object", "properties": {
            "node_gid": identifier, "parent_gid": identifier, "line_gid": identifier,
            "node_type": {"type": "string"}, "name": {"type": "string"},
            "position": {"type": ["string", "number", "integer"]},
            "access_mode": {"type": "string", "enum": ["editable", "read_only"]},
        }, "required": ["node_gid", "parent_gid", "line_gid", "node_type", "name", "position", "access_mode"], "additionalProperties": False}},
        "bindings": {"type": "array", "maxItems": 5000},
    })
    common = dict(owner="craft", plugin_callable=True,
                  confirmation="none", tags=("craft", "bop", "repository", "experimental"), output_schema=output)
    def spec(cid, handler, props, req=(), write=False):
        permissions = ("craft.write_direct",) if write else ("craft.view",)
        return CapabilitySpec(id=cid, version=1, description=cid, risk="write" if write else "read", permissions=permissions, input_schema=schema(props, req), **common), handler
    repo = {"repository_gid": gid}; cas = {**repo, "expected_row_version": {"type":"integer","minimum":1}, "idempotency_key": key}
    space = {"space_gid": gid}; ver = {"version_gid": gid}
    return (
        spec("craft.bop.repository.search", p.search_repositories, {"project_gid": gid, **page}),
        spec("craft.bop.repository.get", p.get_repository, repo, ("repository_gid",)),
        spec("craft.bop.repository.create", p.create_repository, {"project_gid": gid, "idempotency_key": key}, ("project_gid","idempotency_key"), True),
        spec("craft.bop.repository.archive", p.archive_repository, cas, tuple(cas), True),
        spec("craft.bop.repository.restore", p.restore_repository, cas, tuple(cas), True),
        spec("craft.bop.repository.delete", p.delete_repository, {**cas, "reason":{"type":"string","maxLength":1000}}, tuple(cas), True),
        spec("craft.bop.repository_baseline.set", p.set_baseline, {**cas, "version_gid":gid}, (*cas, "version_gid"), True),
        spec("craft.bop.space.search", p.search_spaces, {"repository_gid":gid, **page}, ("repository_gid",)),
        spec("craft.bop.space.get", p.get_space, space, ("space_gid",)),
        spec("craft.bop.space_version.search", p.search_versions, {"space_gid":gid, **page}, ("space_gid",)),
        spec("craft.bop.space_version.get", p.get_version, ver, ("version_gid",)),
        spec("craft.bop.space_version.save", p.save_version, {"space_gid":gid,"expected_head_version":{"type":"integer","minimum":1},"version_kind":{"enum":["saved","frozen","fork_base","proposal_base"]},"source_refs":{"type":"array","maxItems":100},"algorithm_versions":{"type":"object"},"idempotency_key":key}, ("space_gid","expected_head_version","idempotency_key"), True),
        spec("craft.bop.space_version.freeze", p.freeze_version, {"space_gid":gid,"version_gid":gid,"expected_head_version":{"type":"integer","minimum":1},"idempotency_key":key}, ("space_gid","version_gid","expected_head_version","idempotency_key"), True),
        spec("craft.bop.managed_personal_space.delete", p.delete_personal, {"space_gid":gid,"expected_row_version":{"type":"integer","minimum":1},"idempotency_key":key}, ("space_gid","expected_row_version","idempotency_key"), True),
    )


__all__ = ["RepositoryProvider", "candidate_specs"]

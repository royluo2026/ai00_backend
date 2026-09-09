"""Experimental Capability candidates for the BOP repository foundation."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError, CapabilityContext, CapabilityOutput, CapabilitySpec, EvidenceRef,
)

from ..data.bop_repository import BopRepositoryError, BopRepositoryStore
from ..data.bop_repository_mysql import MysqlBopRepositoryStore


def _scope(context: CapabilityContext) -> tuple[str, str]:
    tenant_gid, actor_gid = str(context.team_gid or ""), str(context.user_gid or "")
    if not tenant_gid or not actor_gid:
        raise CapabilityBusinessError("repository_identity_required", "repository_identity_required")
    return tenant_gid, actor_gid


def _output(data: dict[str, Any], action: str) -> CapabilityOutput:
    digest = "sha256:" + hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
    gid = data.get("repository_gid") or data.get("space_gid") or data.get("version_gid") or "search"
    return CapabilityOutput(data=data, evidence=(EvidenceRef(
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
        return self._call("search_spaces", p, c, repository_gid=p["repository_gid"], offset=offset, page_size=size)
    def get_space(self, p, c): return self._call("get_space", p, c, space_gid=p["space_gid"])
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
    output = schema({k: {} for k in ("items", "next_cursor", "repository_gid", "space_gid", "version_gid", "project_gid", "team_space_gid", "head_gid", "baseline_version_gid", "lifecycle_status", "space_kind", "owner_user_gid", "frozen_version_gid", "row_version", "manifest_hash", "version_kind", "deleted", "deletion_gid", "deleted_at", "operation", "tenant_gid", "actor_gid", "idempotency_key", "offset", "page_size")})
    common = dict(owner="craft", permissions=("craft.bop.repository.use",), plugin_callable=True,
                  confirmation="none", tags=("craft", "bop", "repository", "experimental"), output_schema=output)
    def spec(cid, handler, props, req=(), write=False):
        return CapabilitySpec(id=cid, version=1, description=cid, risk="write" if write else "read", input_schema=schema(props, req), **common), handler
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

"""Tenant-bound saved-view aggregate shared by REST and Capability adapters."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
import math
from typing import Any, Iterator

from backend.db.connection import get_conn
from backend.utils.gid import next_gid


_CONFIG_KEYS = {"field_gids", "sort", "filters", "page_size", "presentation"}
_OPERATORS = {"contains", "not_contains", "eq", "not_eq", "empty", "not_empty", "gt", "gte", "lt", "lte"}
_SCOPES = {"private", "team", "shared"}
_ADMIN_ROLES = {"super_admin", "team_admin"}
_SCALAR_TYPES = (str, int, float, bool, type(None))


class SavedViewError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _invalid(message: str) -> None:
    raise SavedViewError("invalid_input", message)


def _closed(value: Any, *, allowed: set[str], required: set[str] = set()) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - allowed or required - set(value):
        _invalid("输入不符合闭合契约")
    return value


def _text(value: Any, *, label: str, required: bool = True, maximum: int = 512) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        _invalid(f"{label} 无效")
    return value.strip() or None


def _integer(value: Any, *, label: str, minimum: int = 0, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum or (maximum is not None and value > maximum):
        _invalid(f"{label} 无效")
    return value


def _filter_value(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        _invalid("filters.value 无效")
    if isinstance(value, _SCALAR_TYPES):
        return deepcopy(value)
    if isinstance(value, list) and len(value) <= 100 and all(
        isinstance(item, _SCALAR_TYPES) and not (isinstance(item, float) and not math.isfinite(item)) for item in value
    ):
        return deepcopy(value)
    _invalid("filters.value 无效")


def _config(value: Any) -> dict[str, Any]:
    config = _closed(value, allowed=_CONFIG_KEYS, required=_CONFIG_KEYS)
    fields = config["field_gids"]
    if not isinstance(fields, list) or len(fields) > 200 or len(set(fields)) != len(fields):
        _invalid("field_gids 无效")
    for field in fields:
        _text(field, label="field_gids", maximum=255)
    sorts = config["sort"]
    if not isinstance(sorts, list) or len(sorts) > 20:
        _invalid("sort 无效")
    for item in sorts:
        clause = _closed(item, allowed={"field_gid", "direction"}, required={"field_gid", "direction"})
        _text(clause["field_gid"], label="sort.field_gid", maximum=255)
        if clause["direction"] not in {"asc", "desc"}:
            _invalid("sort.direction 无效")
    filters = config["filters"]
    if not isinstance(filters, list) or len(filters) > 50:
        _invalid("filters 无效")
    for item in filters:
        clause = _closed(item, allowed={"field_gid", "operator", "value"}, required={"field_gid", "operator", "value"})
        _text(clause["field_gid"], label="filters.field_gid", maximum=255)
        if clause["operator"] not in _OPERATORS:
            _invalid("filters.operator 无效")
        _filter_value(clause["value"])
    _integer(config["page_size"], label="page_size", minimum=1, maximum=200)
    if config["presentation"] not in {"table", "list"}:
        _invalid("presentation 无效")
    return deepcopy(config)


def _legacy_config(value: Any) -> dict[str, Any]:
    """Migrate only the finite legacy AND/table subset; fail closed otherwise."""
    legacy_keys = {"columns", "filters", "filterMode", "sorts", "groupBy", "viewType", "treeParentField"}
    legacy = _closed(value, allowed=legacy_keys, required=legacy_keys)
    if legacy["filterMode"] != "and" or legacy["groupBy"] is not None or legacy["treeParentField"] is not None or legacy["viewType"] != "grid":
        raise SavedViewError("legacy_config_unsupported", "旧视图配置不受支持，需迁移")
    migrated = {
        "field_gids": [item.get("key") for item in sorted(legacy["columns"], key=lambda item: item.get("order", 0)) if item.get("visible")],
        "sort": [{"field_gid": item.get("field"), "direction": item.get("dir")} for item in legacy["sorts"]],
        "filters": [{"field_gid": item.get("field"), "operator": item.get("op"), "value": item.get("value")} for item in legacy["filters"]],
        "page_size": 200,
        "presentation": "table",
    }
    return _config(migrated)


def _actor_gid(actor: dict[str, Any]) -> str:
    return _text(actor.get("gid"), label="actor.gid", maximum=128) or ""


def _tenant_gid(actor: dict[str, Any]) -> str:
    value = actor.get("tenant_gid") or actor.get("team_id") or f"user:{_actor_gid(actor)}"
    return _text(value, label="actor.tenant_gid", maximum=128) or ""


def _team_gids(actor: dict[str, Any]) -> list[str]:
    values = actor.get("team_gids")
    if values is None:
        fallback = actor.get("team_id") or actor.get("tenant_gid")
        values = [] if not fallback or str(fallback).startswith("user:") else [fallback]
    if not isinstance(values, (list, tuple)):
        _invalid("actor.team_gids 无效")
    return [_text(value, label="actor.team_gids", maximum=128) or "" for value in values]


def _is_admin(actor: dict[str, Any]) -> bool:
    return str(actor.get("system_role") or actor.get("org_role") or actor.get("role") or "") in _ADMIN_ROLES


def _json(value: Any, default: Any) -> Any:
    if value is None:
        return deepcopy(default)
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return deepcopy(default)
    return deepcopy(value)


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class SqlSavedViewRepository:
    def __init__(self) -> None:
        self._conn: Any | None = None

    @contextmanager
    def transaction(self) -> Iterator["SqlSavedViewRepository"]:
        with get_conn() as conn:
            self._conn = conn
            try:
                yield self
            finally:
                self._conn = None

    def _cursor(self) -> Any:
        if self._conn is None:
            raise RuntimeError("saved-view repository used outside a transaction")
        return self._conn.cursor()

    def next_gid(self) -> str:
        return str(next_gid())

    @staticmethod
    def _select() -> str:
        return (
            "SELECT v.gid,v.tenant_gid,v.name,v.module,v.list_gid,v.owner_gid,v.is_shared,v.config,v.created_at,v.updated_at,"
            "s.revision AS state_revision,s.deleted AS state_deleted,s.share_scope AS state_share_scope,"
            "s.grants_json AS state_grants_json,s.team_gids_json AS state_team_gids_json,s.restore_json AS state_restore_json "
            "FROM workmanship_app_view_configs v LEFT JOIN workmanship_base_saved_view_states s "
            "ON s.tenant_gid=v.tenant_gid AND s.view_gid=v.gid"
        )

    def get(self, tenant_gid: str, view_gid: str, *, lock: bool = False) -> dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute(self._select() + " WHERE v.tenant_gid=%s AND v.gid=%s" + (" FOR UPDATE" if lock else ""), (tenant_gid, view_gid))
            row = cur.fetchone()
        return _decode_row(dict(row)) if row else None

    def list(self, *, tenant_gid: str, limit: int, offset: int) -> list[dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute(self._select() + " WHERE v.tenant_gid=%s ORDER BY v.gid LIMIT %s OFFSET %s", (tenant_gid, limit, offset))
            rows = cur.fetchall()
        return [_decode_row(dict(row)) for row in rows]

    def save(self, row: dict[str, Any]) -> None:
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_app_view_configs (gid,tenant_gid,name,module,list_gid,owner_gid,is_shared,config) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE name=VALUES(name),module=VALUES(module),"
                "list_gid=VALUES(list_gid),owner_gid=VALUES(owner_gid),is_shared=VALUES(is_shared),config=VALUES(config)",
                (row["gid"], row["tenant_gid"], row["name"], row["module"], row["list_gid"], row["owner_gid"],
                 row["share_scope"] != "private", json.dumps(row["config"], ensure_ascii=False)),
            )
            cur.execute(
                "INSERT INTO workmanship_base_saved_view_states "
                "(tenant_gid,view_gid,revision,deleted,share_scope,grants_json,team_gids_json,restore_json) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE revision=VALUES(revision),deleted=VALUES(deleted),"
                "share_scope=VALUES(share_scope),grants_json=VALUES(grants_json),team_gids_json=VALUES(team_gids_json),restore_json=VALUES(restore_json)",
                (row["tenant_gid"], row["gid"], row["revision"], row["deleted"], row["share_scope"],
                 json.dumps(row["grants"], ensure_ascii=False), json.dumps(row["team_gids"], ensure_ascii=False),
                 json.dumps(row["restore"], ensure_ascii=False) if row["restore"] is not None else None),
            )

    def claim(self, *, tenant_gid: str, actor_gid: str, operation: str, idempotency_key: str, command_digest: str) -> dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_base_saved_view_idempotency "
                "(tenant_gid,actor_gid,operation,idempotency_key,command_digest,status) VALUES (%s,%s,%s,%s,%s,'pending') "
                "ON DUPLICATE KEY UPDATE actor_gid=VALUES(actor_gid)",
                (tenant_gid, actor_gid, operation, idempotency_key, command_digest),
            )
            cur.execute(
                "SELECT command_digest,status,result_json FROM workmanship_base_saved_view_idempotency "
                "WHERE tenant_gid=%s AND actor_gid=%s AND operation=%s AND idempotency_key=%s FOR UPDATE",
                (tenant_gid, actor_gid, operation, idempotency_key),
            )
            row = cur.fetchone()
        if row and str(row.get("command_digest") or "") != command_digest:
            raise SavedViewError("idempotency_conflict", "幂等键已用于不同命令")
        return _json(row.get("result_json"), None) if row and row.get("status") == "completed" else None

    def complete(self, *, tenant_gid: str, actor_gid: str, operation: str, idempotency_key: str,
                 result: dict[str, Any], record_gid: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                "UPDATE workmanship_base_saved_view_idempotency SET status='completed',view_gid=%s,result_json=%s,completed_at=CURRENT_TIMESTAMP(6) "
                "WHERE tenant_gid=%s AND actor_gid=%s AND operation=%s AND idempotency_key=%s",
                (record_gid, json.dumps(result, ensure_ascii=False), tenant_gid, actor_gid, operation, idempotency_key),
            )

    def audit(self, event: dict[str, Any]) -> None:
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_base_saved_view_audit_events "
                "(gid,tenant_gid,view_gid,actor_gid,operation,idempotency_key,status,details_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (self.next_gid(), event["tenant_gid"], event["view_gid"], event["actor_gid"], event["operation"],
                 event.get("idempotency_key") or None, event.get("status", "succeeded"),
                 json.dumps(event.get("details") or {}, ensure_ascii=False)),
            )


def _decode_row(row: dict[str, Any]) -> dict[str, Any]:
    base = {
        "gid": str(row["gid"]), "tenant_gid": str(row.get("tenant_gid") or ""), "name": str(row.get("name") or ""),
        "module": str(row.get("module") or ""), "list_gid": str(row["list_gid"]) if row.get("list_gid") is not None else None,
        "owner_gid": str(row.get("owner_gid") or ""),
    }
    state = {
        "revision": int(row.get("state_revision") or row.get("revision") or 1),
        "deleted": bool(row.get("state_deleted", row.get("deleted", False))),
        "share_scope": str(row.get("state_share_scope") or row.get("share_scope") or ("shared" if row.get("is_shared") else "private")),
        "grants": _json(row.get("state_grants_json", row.get("grants")), []),
        "team_gids": _json(row.get("state_team_gids_json", row.get("team_gids")), []),
        "restore": _json(row.get("state_restore_json", row.get("restore")), None),
    }
    raw = _json(row.get("config"), None)
    try:
        config = _config(raw)
        status = "current"
    except SavedViewError:
        try:
            config = _legacy_config(raw)
            status = "migration_needed"
        except SavedViewError:
            return {**base, **state, "_legacy_status": "legacy_config_unsupported"}
    return {**base, **state, "config": config, "_legacy_status": status}


class SavedViewService:
    def __init__(self, *, repository: Any | None = None) -> None:
        self.repository = repository or SqlSavedViewRepository()

    def search(self, *, actor: dict, query: dict) -> dict:
        query = _closed(query, allowed={"module", "list_gid", "limit", "offset"})
        has_module = "module" in query
        module = (_text(query.get("module"), label="module", required=False) or "") if has_module else None
        list_gid = _text(query.get("list_gid"), label="list_gid", required=False) if query.get("list_gid") is not None else None
        limit = _integer(query.get("limit", 200), label="limit", minimum=1, maximum=200)
        offset = _integer(query.get("offset", 0), label="offset", minimum=0, maximum=10_000_000)
        tenant_gid = _tenant_gid(actor)
        with self.repository.transaction():
            rows = self.repository.list(tenant_gid=tenant_gid, limit=limit + 1, offset=offset)
            views = []
            for row in rows[:limit]:
                if row.get("_legacy_status") == "legacy_config_unsupported":
                    self.repository.audit({"tenant_gid": tenant_gid, "operation": "legacy_migration_needed", "view_gid": row["gid"],
                                           "actor_gid": _actor_gid(actor), "status": "legacy_config_unsupported"})
                    continue
                if not self._visible(actor, row) or (has_module and row["module"] != module):
                    continue
                if list_gid is not None and row["list_gid"] not in {None, list_gid}:
                    continue
                if list_gid is None and has_module and row["list_gid"] is not None:
                    continue
                views.append(self._project(row))
        return {"views": views, "next_offset": offset + limit if len(rows) > limit else None}

    def create(self, *, actor: dict, command: dict) -> dict:
        command = _closed(command, allowed={"name", "module", "list_gid", "config", "share_scope", "idempotency_key"},
                          required={"name", "config", "share_scope", "idempotency_key"})
        scope = command["share_scope"]
        if scope not in _SCOPES:
            _invalid("share_scope 无效")
        tenant_gid = _tenant_gid(actor)
        return self._write(actor=actor, operation="create", command=command, mutate=lambda: {
            "gid": self.repository.next_gid(), "tenant_gid": tenant_gid, "name": _text(command["name"], label="name"),
            "module": _text(command.get("module", ""), label="module", required=False) or "",
            "list_gid": _text(command.get("list_gid"), label="list_gid", required=False), "owner_gid": _actor_gid(actor),
            "config": _config(command["config"]), "revision": 1, "deleted": False, "share_scope": scope,
            "grants": [], "team_gids": _team_gids(actor), "restore": None,
        })

    def update(self, *, actor: dict, view_gid: str, command: dict) -> dict:
        command = _closed(command, allowed={"expected_revision", "name", "module", "list_gid", "config", "share_scope", "idempotency_key"},
                          required={"expected_revision", "name", "config", "idempotency_key"})
        self._revision(command["expected_revision"])
        name, config = _text(command["name"], label="name"), _config(command["config"])
        scope = command.get("share_scope")
        if scope is not None and scope not in _SCOPES:
            _invalid("share_scope 无效")
        def mutate() -> dict[str, Any]:
            row = self._owned(actor, view_gid)
            self._check_revision(row, command["expected_revision"])
            row.update({"name": name, "config": config, "revision": row["revision"] + 1})
            if "module" in command:
                row["module"] = _text(command.get("module"), label="module", required=False) or ""
            if "list_gid" in command:
                row["list_gid"] = _text(command.get("list_gid"), label="list_gid", required=False)
            if scope is not None:
                row["share_scope"] = scope
            row.pop("_legacy_status", None)
            return row
        return self._write(actor=actor, operation="update", command={**command, "view_gid": view_gid}, mutate=mutate)

    def copy(self, *, actor: dict, view_gid: str, command: dict) -> dict:
        command = _closed(command, allowed={"name", "idempotency_key"}, required={"name", "idempotency_key"})
        name = _text(command["name"], label="name")
        def mutate() -> dict[str, Any]:
            source = self.repository.get(_tenant_gid(actor), view_gid, lock=True)
            self._ensure_supported(source)
            if source is None or source["deleted"] or not self._visible(actor, source):
                raise SavedViewError("resource_not_found", "视图不存在")
            return {**source, "gid": self.repository.next_gid(), "name": name, "owner_gid": _actor_gid(actor),
                    "revision": 1, "deleted": False, "share_scope": "private", "grants": [],
                    "team_gids": _team_gids(actor), "restore": None, "_legacy_status": "current"}
        return self._write(actor=actor, operation="copy", command={**command, "view_gid": view_gid}, mutate=mutate)

    def delete(self, *, actor: dict, view_gid: str, command: dict) -> dict:
        command = _closed(command, allowed={"expected_revision", "idempotency_key"}, required={"expected_revision", "idempotency_key"})
        self._revision(command["expected_revision"])
        def mutate() -> dict[str, Any]:
            row = self._owned(actor, view_gid)
            self._check_revision(row, command["expected_revision"])
            row["deleted"], row["revision"] = True, row["revision"] + 1
            row["restore"] = {"available": True, "deleted_by": _actor_gid(actor), "deleted_at": datetime.now(UTC).isoformat()}
            row.pop("_legacy_status", None)
            return row
        return self._write(actor=actor, operation="delete", command={**command, "view_gid": view_gid}, mutate=mutate)

    def _write(self, *, actor: dict, operation: str, command: dict, mutate: Any) -> dict:
        actor_gid, tenant_gid = _actor_gid(actor), _tenant_gid(actor)
        key = _text(command.get("idempotency_key"), label="idempotency_key") or ""
        command_digest = _digest({"operation": operation, **command})
        with self.repository.transaction():
            replay = self.repository.claim(tenant_gid=tenant_gid, actor_gid=actor_gid, operation=operation,
                                           idempotency_key=key, command_digest=command_digest)
            if replay is not None:
                return replay
            row = mutate()
            self.repository.save(row)
            result = {"view": self._project(row)}
            self.repository.complete(tenant_gid=tenant_gid, actor_gid=actor_gid, operation=operation,
                                     idempotency_key=key, result=result, record_gid=row["gid"])
            self.repository.audit({"tenant_gid": tenant_gid, "operation": operation, "view_gid": row["gid"],
                                   "actor_gid": actor_gid, "idempotency_key": key, "status": "succeeded",
                                   "details": {"command_digest": command_digest}})
            return result

    @staticmethod
    def _ensure_supported(row: dict[str, Any] | None) -> None:
        if row is not None and row.get("_legacy_status") == "legacy_config_unsupported":
            raise SavedViewError("legacy_config_unsupported", "旧视图配置不受支持，需迁移")

    def _owned(self, actor: dict, view_gid: str) -> dict[str, Any]:
        row = self.repository.get(_tenant_gid(actor), view_gid, lock=True)
        self._ensure_supported(row)
        if row is None or row["deleted"]:
            raise SavedViewError("resource_not_found", "视图不存在")
        if row["owner_gid"] != _actor_gid(actor) and not _is_admin(actor):
            raise SavedViewError("permission_denied", "无权修改此视图")
        return row

    @staticmethod
    def _revision(value: Any) -> None:
        _integer(value, label="expected_revision", minimum=1)

    @staticmethod
    def _check_revision(row: dict[str, Any], expected: int) -> None:
        if row["revision"] != expected:
            raise SavedViewError("revision_conflict", "视图版本已变化")

    @staticmethod
    def _visible(actor: dict, row: dict[str, Any]) -> bool:
        if row["tenant_gid"] != _tenant_gid(actor) or row["deleted"]:
            return False
        if row["owner_gid"] == _actor_gid(actor) or _is_admin(actor) or row["share_scope"] == "shared":
            return True
        return row["share_scope"] == "team" and bool(set(_team_gids(actor)) & set(row["team_gids"]))

    @staticmethod
    def _project(row: dict[str, Any]) -> dict[str, Any]:
        return {key: deepcopy(row[key]) for key in (
            "gid", "name", "module", "list_gid", "owner_gid", "config", "revision", "deleted", "share_scope", "grants", "restore",
        )}


__all__ = ["SavedViewError", "SavedViewService", "SqlSavedViewRepository"]

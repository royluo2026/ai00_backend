"""Closed saved-view aggregate service shared by REST and Capability adapters."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
import math
from typing import Any, Iterator

from backend.db.connection import get_conn
from backend.utils.gid import next_gid


_CONFIG_KEYS = {"columns", "filters", "filterMode", "sorts", "groupBy", "viewType", "treeParentField"}
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
    if not isinstance(value, str) or len(value) > maximum:
        _invalid(f"{label} 无效")
    if not value.strip() and not required:
        return None
    if not value.strip():
        _invalid(f"{label} 无效")
    return value.strip()


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
        isinstance(item, _SCALAR_TYPES) and not (isinstance(item, float) and not math.isfinite(item))
        for item in value
    ):
        return deepcopy(value)
    _invalid("filters.value 无效")


def _config(value: Any) -> dict[str, Any]:
    config = _closed(value, allowed=_CONFIG_KEYS, required=_CONFIG_KEYS)
    columns = config["columns"]
    if not isinstance(columns, list) or len(columns) > 200:
        _invalid("columns 无效")
    for item in columns:
        column = _closed(item, allowed={"key", "visible", "order", "width"}, required={"key", "visible", "order", "width"})
        _text(column["key"], label="columns.key")
        if not isinstance(column["visible"], bool):
            _invalid("columns.visible 无效")
        _integer(column["order"], label="columns.order")
        _integer(column["width"], label="columns.width", minimum=40, maximum=2000)

    filters = config["filters"]
    if not isinstance(filters, list) or len(filters) > 50:
        _invalid("filters 无效")
    for item in filters:
        clause = _closed(item, allowed={"id", "field", "op", "value"}, required={"id", "field", "op", "value"})
        _text(clause["id"], label="filters.id")
        _text(clause["field"], label="filters.field")
        if clause["op"] not in _OPERATORS:
            _invalid("filters.op 无效")
        _filter_value(clause["value"])

    if config["filterMode"] not in {"and", "or"}:
        _invalid("filterMode 无效")
    sorts = config["sorts"]
    if not isinstance(sorts, list) or len(sorts) > 20:
        _invalid("sorts 无效")
    for item in sorts:
        clause = _closed(item, allowed={"field", "dir"}, required={"field", "dir"})
        _text(clause["field"], label="sorts.field")
        if clause["dir"] not in {"asc", "desc"}:
            _invalid("sorts.dir 无效")
    for key in ("groupBy", "treeParentField"):
        if config[key] is not None:
            _text(config[key], label=key)
    if config["viewType"] not in {"grid", "tree"}:
        _invalid("viewType 无效")
    return deepcopy(config)


def _actor_gid(actor: dict[str, Any]) -> str:
    return _text(actor.get("gid"), label="actor.gid") or ""


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


class SqlSavedViewRepository:
    """Persistence adapter for user config plus Base-owned lifecycle evidence."""

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
            "SELECT v.gid,v.name,v.module,v.list_gid,v.owner_gid,v.is_shared,v.config,v.created_at,v.updated_at,"
            "s.revision AS state_revision,s.deleted AS state_deleted,s.share_scope AS state_share_scope,"
            "s.grants_json AS state_grants_json,s.team_gids_json AS state_team_gids_json,s.restore_json AS state_restore_json "
            "FROM workmanship_app_view_configs v LEFT JOIN workmanship_base_saved_view_states s ON s.view_gid=v.gid"
        )

    def get(self, view_gid: str, *, lock: bool = False) -> dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute(self._select() + " WHERE v.gid=%s" + (" FOR UPDATE" if lock else ""), (view_gid,))
            row = cur.fetchone()
        return _decode_row(dict(row)) if row else None

    def list(self) -> list[dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute(self._select())
            rows = cur.fetchall()
        return [_decode_row(dict(row)) for row in rows]

    def save(self, row: dict[str, Any]) -> None:
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_app_view_configs (gid,name,module,list_gid,owner_gid,is_shared,config) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                "name=VALUES(name),module=VALUES(module),list_gid=VALUES(list_gid),owner_gid=VALUES(owner_gid),"
                "is_shared=VALUES(is_shared),config=VALUES(config)",
                (row["gid"], row["name"], row["module"], row["list_gid"], row["owner_gid"],
                 row["share_scope"] != "private", json.dumps(row["config"], ensure_ascii=False)),
            )
            cur.execute(
                "INSERT INTO workmanship_base_saved_view_states "
                "(view_gid,revision,deleted,share_scope,grants_json,team_gids_json,restore_json) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE revision=VALUES(revision),"
                "deleted=VALUES(deleted),share_scope=VALUES(share_scope),grants_json=VALUES(grants_json),"
                "team_gids_json=VALUES(team_gids_json),restore_json=VALUES(restore_json)",
                (row["gid"], row["revision"], row["deleted"], row["share_scope"],
                 json.dumps(row["grants"], ensure_ascii=False), json.dumps(row["team_gids"], ensure_ascii=False),
                 json.dumps(row["restore"], ensure_ascii=False) if row["restore"] is not None else None),
            )

    def claim(self, *, actor_gid: str, operation: str, idempotency_key: str) -> dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_base_saved_view_idempotency "
                "(actor_gid,operation,idempotency_key,status) VALUES (%s,%s,%s,'pending') "
                "ON DUPLICATE KEY UPDATE actor_gid=VALUES(actor_gid)",
                (actor_gid, operation, idempotency_key),
            )
            cur.execute(
                "SELECT status,result_json FROM workmanship_base_saved_view_idempotency "
                "WHERE actor_gid=%s AND operation=%s AND idempotency_key=%s FOR UPDATE",
                (actor_gid, operation, idempotency_key),
            )
            row = cur.fetchone()
        if row and row.get("status") == "completed":
            return _json(row.get("result_json"), None)
        return None

    def complete(self, *, actor_gid: str, operation: str, idempotency_key: str,
                 result: dict[str, Any], record_gid: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                "UPDATE workmanship_base_saved_view_idempotency SET status='completed',view_gid=%s,result_json=%s,"
                "completed_at=CURRENT_TIMESTAMP(6) "
                "WHERE actor_gid=%s AND operation=%s AND idempotency_key=%s",
                (record_gid, json.dumps(result, ensure_ascii=False), actor_gid, operation, idempotency_key),
            )

    def audit(self, event: dict[str, Any]) -> None:
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_base_saved_view_audit_events "
                "(gid,view_gid,actor_gid,operation,idempotency_key,status,details_json) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (self.next_gid(), event["view_gid"], event["actor_gid"], event["operation"],
                 event.get("idempotency_key") or None, event.get("status", "succeeded"),
                 json.dumps(event.get("details") or {}, ensure_ascii=False)),
            )


def _decode_row(row: dict[str, Any]) -> dict[str, Any]:
    raw_config = _json(row.get("config"), None)
    base = {
        "gid": str(row["gid"]), "name": str(row.get("name") or ""), "module": str(row.get("module") or ""),
        "list_gid": str(row["list_gid"]) if row.get("list_gid") is not None else None,
        "owner_gid": str(row.get("owner_gid") or ""),
    }
    state = {
        "revision": int(row.get("state_revision") or 1), "deleted": bool(row.get("state_deleted")),
        "share_scope": str(row.get("state_share_scope") or ("shared" if row.get("is_shared") else "private")),
        "grants": _json(row.get("state_grants_json"), []),
        "team_gids": _json(row.get("state_team_gids_json"), []),
        "restore": _json(row.get("state_restore_json"), None),
    }
    try:
        config = _config(raw_config)
    except SavedViewError:
        return {**base, **state, "_legacy_status": "legacy_config_unsupported"}
    return {**base, **state, "config": config,
            "_legacy_status": "current" if row.get("state_revision") is not None else "migration_needed"}


class SavedViewService:
    def __init__(self, *, repository: Any | None = None) -> None:
        self.repository = repository or SqlSavedViewRepository()

    def search(self, *, actor: dict, query: dict) -> dict:
        query = _closed(query, allowed={"module", "list_gid"})
        has_module = "module" in query
        module = _text(query.get("module"), label="module", required=False) if has_module else None
        module = (module or "") if has_module else None
        list_gid = _text(query.get("list_gid"), label="list_gid", required=False) if query.get("list_gid") is not None else None
        with self.repository.transaction():
            views = []
            for row in self.repository.list():
                if row.get("_legacy_status") == "legacy_config_unsupported":
                    self.repository.audit({"operation": "legacy_migration_needed", "view_gid": row["gid"],
                                           "actor_gid": _actor_gid(actor), "status": "legacy_config_unsupported"})
                    continue
                if not self._visible(actor, row) or (has_module and row["module"] != module):
                    continue
                if list_gid is not None:
                    if row["list_gid"] not in {None, list_gid}:
                        continue
                elif has_module and row["list_gid"] is not None:
                    continue
                views.append(self._project(row))
        return {"views": views}

    def create(self, *, actor: dict, command: dict) -> dict:
        command = _closed(command, allowed={"name", "module", "list_gid", "config", "share_scope", "idempotency_key"},
                          required={"name", "config", "share_scope", "idempotency_key"})
        name = _text(command["name"], label="name")
        module = _text(command.get("module", ""), label="module", required=False) or ""
        list_gid = _text(command.get("list_gid"), label="list_gid", required=False)
        config = _config(command["config"])
        scope = command["share_scope"]
        if scope not in _SCOPES:
            _invalid("share_scope 无效")
        return self._write(actor=actor, operation="create", command=command, mutate=lambda: {
            "gid": self.repository.next_gid(), "name": name, "module": module, "list_gid": list_gid,
            "owner_gid": _actor_gid(actor), "config": config, "revision": 1, "deleted": False,
            "share_scope": scope, "grants": [], "team_gids": list(actor.get("team_gids") or []), "restore": None,
        })

    def update(self, *, actor: dict, view_gid: str, command: dict) -> dict:
        command = _closed(command, allowed={"expected_revision", "name", "module", "list_gid", "config", "share_scope", "idempotency_key"},
                          required={"expected_revision", "name", "config", "idempotency_key"})
        self._revision(command["expected_revision"])
        name, config = _text(command["name"], label="name"), _config(command["config"])
        module = _text(command.get("module"), label="module", required=False) if "module" in command else None
        list_gid = _text(command.get("list_gid"), label="list_gid", required=False) if "list_gid" in command else None
        scope = command.get("share_scope")
        if scope is not None and scope not in _SCOPES:
            _invalid("share_scope 无效")

        def mutate() -> dict[str, Any]:
            row = self._owned(actor, view_gid)
            self._check_revision(row, command["expected_revision"])
            row.update({"name": name, "config": config, "revision": row["revision"] + 1})
            if "module" in command:
                row["module"] = module or ""
            if "list_gid" in command:
                row["list_gid"] = list_gid
            if scope is not None:
                row["share_scope"] = scope
            row.pop("_legacy_status", None)
            return row
        return self._write(actor=actor, operation="update", command=command, mutate=mutate)

    def copy(self, *, actor: dict, view_gid: str, command: dict) -> dict:
        command = _closed(command, allowed={"name", "idempotency_key"}, required={"name", "idempotency_key"})
        name = _text(command["name"], label="name")

        def mutate() -> dict[str, Any]:
            source = self.repository.get(view_gid, lock=True)
            self._ensure_supported(source)
            if source is None or source["deleted"] or not self._visible(actor, source):
                raise SavedViewError("resource_not_found", "视图不存在")
            return {**source, "gid": self.repository.next_gid(), "name": name, "owner_gid": _actor_gid(actor),
                    "revision": 1, "deleted": False, "share_scope": "private", "grants": [],
                    "team_gids": list(actor.get("team_gids") or []), "restore": None, "_legacy_status": "current"}
        return self._write(actor=actor, operation="copy", command=command, mutate=mutate)

    def delete(self, *, actor: dict, view_gid: str, command: dict) -> dict:
        command = _closed(command, allowed={"expected_revision", "idempotency_key"}, required={"expected_revision", "idempotency_key"})
        self._revision(command["expected_revision"])

        def mutate() -> dict[str, Any]:
            row = self._owned(actor, view_gid)
            self._check_revision(row, command["expected_revision"])
            row["deleted"] = True
            row["revision"] += 1
            row["restore"] = {"available": True, "deleted_by": _actor_gid(actor), "deleted_at": "transaction"}
            row.pop("_legacy_status", None)
            return row
        return self._write(actor=actor, operation="delete", command=command, mutate=mutate)

    def _write(self, *, actor: dict, operation: str, command: dict, mutate: Any) -> dict:
        actor_gid = _actor_gid(actor)
        key = _text(command.get("idempotency_key"), label="idempotency_key") or ""
        with self.repository.transaction():
            replay = self.repository.claim(actor_gid=actor_gid, operation=operation, idempotency_key=key)
            if replay is not None:
                return replay
            row = mutate()
            self.repository.save(row)
            result = {"view": self._project(row)}
            self.repository.complete(actor_gid=actor_gid, operation=operation, idempotency_key=key,
                                     result=result, record_gid=row["gid"])
            self.repository.audit({"operation": operation, "view_gid": row["gid"], "actor_gid": actor_gid,
                                   "idempotency_key": key, "status": "succeeded"})
            return result

    @staticmethod
    def _ensure_supported(row: dict[str, Any] | None) -> None:
        if row is not None and row.get("_legacy_status") == "legacy_config_unsupported":
            raise SavedViewError("legacy_config_unsupported", "旧视图配置不受支持，需迁移")

    def _owned(self, actor: dict, view_gid: str) -> dict[str, Any]:
        row = self.repository.get(view_gid, lock=True)
        self._ensure_supported(row)
        if row is None or row["deleted"]:
            raise SavedViewError("resource_not_found", "视图不存在")
        if row["owner_gid"] != _actor_gid(actor) and not _is_admin(actor):
            raise SavedViewError("permission_denied", "无权修改此视图")
        return row

    @staticmethod
    def _revision(value: Any) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            _invalid("expected_revision 无效")

    @staticmethod
    def _check_revision(row: dict[str, Any], expected: int) -> None:
        if row["revision"] != expected:
            raise SavedViewError("revision_conflict", "视图版本已变化")

    @staticmethod
    def _visible(actor: dict, row: dict[str, Any]) -> bool:
        if row["deleted"]:
            return False
        if row["owner_gid"] == _actor_gid(actor) or _is_admin(actor) or row["share_scope"] == "shared":
            return True
        return row["share_scope"] == "team" and bool(set(actor.get("team_gids") or []) & set(row["team_gids"]))

    @staticmethod
    def _project(row: dict[str, Any]) -> dict[str, Any]:
        return {key: deepcopy(row[key]) for key in (
            "gid", "name", "module", "list_gid", "owner_gid", "config", "revision", "deleted", "share_scope", "grants", "restore",
        )}


__all__ = ["SavedViewError", "SavedViewService", "SqlSavedViewRepository"]

"""Closed saved-view aggregate service shared by REST and Capability adapters."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
from typing import Any, Iterator

from backend.db.connection import get_conn
from backend.utils.gid import next_gid


_CONFIG_KEYS = {"field_gids", "sort", "filters", "page_size", "presentation"}
_OPERATORS = {"eq", "neq", "contains", "in", "gt", "gte", "lt", "lte"}
_PRESENTATIONS = {"table", "kanban", "calendar"}
_SCOPES = {"private", "team", "shared"}
_ADMIN_ROLES = {"super_admin", "team_admin"}


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


def _config(value: Any) -> dict[str, Any]:
    config = _closed(value, allowed=_CONFIG_KEYS, required=_CONFIG_KEYS)
    fields = config["field_gids"]
    if not isinstance(fields, list) or not fields or len(fields) > 200 or any(_text(item, label="field_gid") is None for item in fields):
        _invalid("field_gids 无效")
    sort = config["sort"]
    if not isinstance(sort, list) or len(sort) > 20:
        _invalid("sort 无效")
    for item in sort:
        clause = _closed(item, allowed={"field_gid", "direction"}, required={"field_gid", "direction"})
        _text(clause["field_gid"], label="sort.field_gid")
        if clause["direction"] not in {"asc", "desc"}:
            _invalid("sort.direction 无效")
    filters = config["filters"]
    if not isinstance(filters, list) or len(filters) > 50:
        _invalid("filters 无效")
    for item in filters:
        clause = _closed(item, allowed={"field_gid", "operator", "value"}, required={"field_gid", "operator", "value"})
        _text(clause["field_gid"], label="filters.field_gid")
        if clause["operator"] not in _OPERATORS or isinstance(clause["value"], dict):
            _invalid("filter 无效")
    page_size = config["page_size"]
    if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 200:
        _invalid("page_size 无效")
    if config["presentation"] not in _PRESENTATIONS:
        _invalid("presentation 无效")
    return deepcopy(config)


def _actor_gid(actor: dict[str, Any]) -> str:
    return _text(actor.get("gid"), label="actor.gid") or ""


def _is_admin(actor: dict[str, Any]) -> bool:
    return str(actor.get("system_role") or actor.get("org_role") or actor.get("role") or "") in _ADMIN_ROLES


class SqlSavedViewRepository:
    """Persistence adapter using the existing view table and its JSON column envelope."""

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

    def get(self, view_gid: str, *, lock: bool = False) -> dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute(
                "SELECT gid,name,module,list_gid,owner_gid,is_shared,config,created_at,updated_at "
                "FROM workmanship_app_view_configs WHERE gid=%s" + (" FOR UPDATE" if lock else ""),
                (view_gid,),
            )
            row = cur.fetchone()
        return _decode_row(dict(row)) if row else None

    def list(self) -> list[dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute("SELECT gid,name,module,list_gid,owner_gid,is_shared,config,created_at,updated_at FROM workmanship_app_view_configs")
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
                 row["share_scope"] != "private", json.dumps(_stored(row), ensure_ascii=False)),
            )

    def replay(self, *, actor_gid: str, operation: str, idempotency_key: str) -> dict[str, Any] | None:
        key = f"{actor_gid}:{operation}:{idempotency_key}"
        for row in self.list():
            result = row.get("_replays", {}).get(key)
            if result is not None:
                return deepcopy(result)
        return None

    def remember(self, *, actor_gid: str, operation: str, idempotency_key: str, result: dict[str, Any], record_gid: str) -> None:
        row = self.get(record_gid, lock=True)
        if row is None:
            raise SavedViewError("resource_not_found", "视图不存在")
        row.setdefault("_replays", {})[f"{actor_gid}:{operation}:{idempotency_key}"] = deepcopy(result)
        self.save(row)

    def audit(self, event: dict[str, Any]) -> None:
        row = self.get(str(event["view_gid"]), lock=True)
        if row is None:
            raise SavedViewError("resource_not_found", "视图不存在")
        row.setdefault("_audit", []).append(deepcopy(event))
        self.save(row)


def _decode_row(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("config")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = {}
    stored = raw.get("_saved_view") if isinstance(raw, dict) else None
    if not isinstance(stored, dict):
        stored = {"config": raw if isinstance(raw, dict) else {}, "revision": 1, "deleted": False,
                  "share_scope": "shared" if row.get("is_shared") else "private", "grants": [], "team_gids": [],
                  "restore": None, "replays": {}, "audit": []}
    return {
        "gid": str(row["gid"]), "name": str(row.get("name") or ""), "module": str(row.get("module") or ""),
        "list_gid": str(row["list_gid"]) if row.get("list_gid") is not None else None,
        "owner_gid": str(row.get("owner_gid") or ""), "config": deepcopy(stored.get("config") or {}),
        "revision": int(stored.get("revision") or 1), "deleted": bool(stored.get("deleted")),
        "share_scope": str(stored.get("share_scope") or "private"), "grants": list(stored.get("grants") or []),
        "team_gids": list(stored.get("team_gids") or []), "restore": deepcopy(stored.get("restore")),
        "_replays": deepcopy(stored.get("replays") or {}), "_audit": deepcopy(stored.get("audit") or []),
    }


def _stored(row: dict[str, Any]) -> dict[str, Any]:
    values = {key: deepcopy(row.get(key)) for key in (
        "config", "revision", "deleted", "share_scope", "grants", "team_gids", "restore",
    )}
    values["replays"] = deepcopy(row.get("_replays"))
    values["audit"] = deepcopy(row.get("_audit"))
    return {"_saved_view": values}


class SavedViewService:
    def __init__(self, *, repository: Any | None = None) -> None:
        self.repository = repository or SqlSavedViewRepository()

    def search(self, *, actor: dict, query: dict) -> dict:
        query = _closed(query, allowed={"module", "list_gid"})
        module = query.get("module")
        list_gid = query.get("list_gid")
        if module is not None:
            module = _text(module, label="module", required=False)
        if list_gid is not None:
            list_gid = _text(list_gid, label="list_gid", required=False)
        with self.repository.transaction():
            views = [self._project(row) for row in self.repository.list() if self._visible(actor, row)
                     and (module is None or row["module"] == module)
                     and (list_gid is None or row["list_gid"] == list_gid)]
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
            "_replays": {}, "_audit": [],
        })

    def update(self, *, actor: dict, view_gid: str, command: dict) -> dict:
        command = _closed(command, allowed={"expected_revision", "name", "module", "list_gid", "config", "share_scope", "idempotency_key"},
                          required={"expected_revision", "name", "config", "idempotency_key"})
        self._revision(command["expected_revision"])
        name, config = _text(command["name"], label="name"), _config(command["config"])
        module = command.get("module")
        list_gid = command.get("list_gid")
        if module is not None:
            module = _text(module, label="module", required=False) or ""
        if list_gid is not None:
            list_gid = _text(list_gid, label="list_gid", required=False)
        scope = command.get("share_scope")
        if scope is not None and scope not in _SCOPES:
            _invalid("share_scope 无效")

        def mutate() -> dict[str, Any]:
            row = self._owned(actor, view_gid)
            self._check_revision(row, command["expected_revision"])
            row.update({"name": name, "config": config, "revision": row["revision"] + 1})
            if module is not None: row["module"] = module
            if list_gid is not None: row["list_gid"] = list_gid
            if scope is not None: row["share_scope"] = scope
            return row
        return self._write(actor=actor, operation="update", command=command, mutate=mutate)

    def copy(self, *, actor: dict, view_gid: str, command: dict) -> dict:
        command = _closed(command, allowed={"name", "idempotency_key"}, required={"name", "idempotency_key"})
        name = _text(command["name"], label="name")

        def mutate() -> dict[str, Any]:
            source = self.repository.get(view_gid, lock=True)
            if source is None or source["deleted"] or not self._visible(actor, source):
                raise SavedViewError("resource_not_found", "视图不存在")
            return {**source, "gid": self.repository.next_gid(), "name": name, "owner_gid": _actor_gid(actor),
                    "revision": 1, "deleted": False, "share_scope": "private", "grants": [],
                    "team_gids": list(actor.get("team_gids") or []), "restore": None, "_replays": {}, "_audit": []}
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
            return row
        return self._write(actor=actor, operation="delete", command=command, mutate=mutate)

    def _write(self, *, actor: dict, operation: str, command: dict, mutate: Any) -> dict:
        actor_gid = _actor_gid(actor)
        key = _text(command.get("idempotency_key"), label="idempotency_key") or ""
        with self.repository.transaction():
            replay = self.repository.replay(actor_gid=actor_gid, operation=operation, idempotency_key=key)
            if replay is not None:
                return replay
            row = mutate()
            self.repository.save(row)
            result = {"view": self._project(row)}
            self.repository.remember(actor_gid=actor_gid, operation=operation, idempotency_key=key, result=result, record_gid=row["gid"])
            self.repository.audit({"operation": operation, "view_gid": row["gid"], "actor_gid": actor_gid, "idempotency_key": key})
            return result

    def _owned(self, actor: dict, view_gid: str) -> dict[str, Any]:
        row = self.repository.get(view_gid, lock=True)
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

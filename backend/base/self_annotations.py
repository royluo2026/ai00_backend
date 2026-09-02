"""Tenant-bound self-annotation aggregate shared by every transport."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
from typing import Any, Iterator, Protocol

from backend.db.connection import get_conn
from backend.utils.gid import next_gid


_COMMAND_KEYS = {"item_gid", "expected_revision", "status", "schedule", "note", "attachments", "idempotency_key"}
_ATTACHMENT_KEYS = {"attachment_gid", "media_type", "display_name", "size", "checksum"}


class SelfAnnotationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _invalid(message: str = "输入不符合闭合契约") -> None:
    raise SelfAnnotationError("invalid_input", message)


def _text(value: Any, *, label: str, maximum: int, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or len(value) > maximum:
        _invalid(f"{label} 无效")
    return value.strip()


def _actor_gid(actor: dict[str, Any]) -> str:
    value = _text(actor.get("gid"), label="actor.gid", maximum=128)
    if not value:
        _invalid("actor.gid 无效")
    return value


def _tenant_gid(actor: dict[str, Any]) -> str:
    value = _text(actor.get("tenant_gid", actor.get("team_id")), label="actor.tenant_gid", maximum=128)
    if not value:
        _invalid("actor.tenant_gid 无效")
    return value


def _attachment(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _ATTACHMENT_KEYS:
        _invalid("attachments 无效")
    gid = _text(value["attachment_gid"], label="attachment_gid", maximum=128)
    media_type = _text(value["media_type"], label="media_type", maximum=128)
    display_name = _text(value["display_name"], label="display_name", maximum=512)
    checksum = _text(value["checksum"], label="checksum", maximum=80)
    size = value["size"]
    if not gid or not media_type or not media_type.startswith(("image/", "application/pdf", "text/")):
        _invalid("attachments 无效")
    if not display_name or isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= 50 * 1024 * 1024:
        _invalid("attachments 无效")
    if not checksum or not checksum.startswith("sha256:") or len(checksum) != 71:
        _invalid("attachments 无效")
    return {"attachment_gid": gid, "media_type": media_type, "display_name": display_name, "size": size, "checksum": checksum}


def _typed_attachments(value: Any) -> list[dict[str, Any]]:
    raw = _json(value, [])
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        try:
            result.append(_attachment(item))
        except SelfAnnotationError:
            continue
    return result


def _json(value: Any, default: Any) -> Any:
    if value is None:
        return deepcopy(default)
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return deepcopy(default)
    return deepcopy(value)


def _digest(command: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(command, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class SqlSelfAnnotationRepository:
    def __init__(self) -> None:
        self._conn: Any | None = None

    @contextmanager
    def transaction(self) -> Iterator["SqlSelfAnnotationRepository"]:
        with get_conn() as conn:
            self._conn = conn
            try:
                yield self
            finally:
                self._conn = None

    def _cursor(self) -> Any:
        if self._conn is None:
            raise RuntimeError("annotation repository used outside transaction")
        return self._conn.cursor()

    @staticmethod
    def _select() -> str:
        return (
            "SELECT a.item_gid,a.user_gid,a.tenant_gid,a.module,a.item_title,a.self_status,a.self_schedule,a.self_note,a.self_attachments,"
            "s.revision,s.deleted,s.restore_json FROM workmanship_base_self_annotations a "
            "LEFT JOIN workmanship_base_self_annotation_states s ON "
            "s.tenant_gid COLLATE utf8mb4_unicode_ci=a.tenant_gid COLLATE utf8mb4_unicode_ci AND "
            "s.item_gid COLLATE utf8mb4_unicode_ci=a.item_gid COLLATE utf8mb4_unicode_ci AND "
            "s.user_gid COLLATE utf8mb4_unicode_ci=a.user_gid COLLATE utf8mb4_unicode_ci"
        )

    def get(self, *, tenant_gid: str, actor_gid: str, item_gid: str, lock: bool = False) -> dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute(self._select() + " WHERE a.tenant_gid=%s AND a.item_gid=%s AND a.user_gid=%s" + (" FOR UPDATE" if lock else ""),
                        (tenant_gid, item_gid, actor_gid))
            row = cur.fetchone()
        return _decode(dict(row)) if row else None

    def list(self, *, tenant_gid: str, actor_gid: str, limit: int, status: str | None, module: str | None) -> list[dict[str, Any]]:
        where = ["a.tenant_gid=%s", "a.user_gid=%s", "COALESCE(s.deleted,0)=0"]
        params: list[Any] = [tenant_gid, actor_gid]
        if status is not None:
            where.append("a.self_status=%s")
            params.append(status)
        if module is not None:
            where.append("a.module=%s")
            params.append(module)
        params.append(limit)
        with self._cursor() as cur:
            cur.execute(self._select() + " WHERE " + " AND ".join(where) + " ORDER BY a.updated_at DESC,a.item_gid LIMIT %s", tuple(params))
            rows = cur.fetchall()
        return [_decode(dict(row)) for row in rows]

    def batch(self, *, tenant_gid: str, actor_gid: str, item_gids: list[str]) -> list[dict[str, Any]]:
        if not item_gids:
            return []
        placeholders = ",".join(["%s"] * len(item_gids))
        with self._cursor() as cur:
            cur.execute(self._select() + f" WHERE a.tenant_gid=%s AND a.user_gid=%s AND a.item_gid IN ({placeholders}) ORDER BY a.item_gid",
                        (tenant_gid, actor_gid, *item_gids))
            rows = cur.fetchall()
        return [_decode(dict(row)) for row in rows]

    def attachment_reference_registered(self, *, actor: dict[str, Any], reference: dict[str, Any]) -> bool:
        with self._cursor() as cur:
            cur.execute(
                "SELECT 1 FROM workmanship_base_attachment_references WHERE attachment_gid=%s AND actor_gid=%s AND tenant_gid=%s "
                "AND media_type=%s AND display_name=%s AND size=%s AND checksum=%s LIMIT 1",
                (reference["attachment_gid"], _actor_gid(actor), _tenant_gid(actor), reference["media_type"],
                 reference["display_name"], reference["size"], reference["checksum"]),
            )
            return cur.fetchone() is not None

    def register_attachment_reference(self, *, actor: dict[str, Any], reference: dict[str, Any]) -> None:
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_base_attachment_references "
                "(attachment_gid,actor_gid,tenant_gid,media_type,display_name,size,checksum) VALUES (%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE media_type=VALUES(media_type),display_name=VALUES(display_name),size=VALUES(size),checksum=VALUES(checksum)",
                (reference["attachment_gid"], _actor_gid(actor), _tenant_gid(actor), reference["media_type"],
                 reference["display_name"], reference["size"], reference["checksum"]),
            )

    def save(self, row: dict[str, Any]) -> None:
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_base_self_annotations "
                "(tenant_gid,item_gid,user_gid,module,item_title,self_status,self_schedule,self_note,self_attachments,updated_at) "
                "VALUES (%s,%s,%s,%s,'',%s,%s,%s,%s,NOW()) ON DUPLICATE KEY UPDATE module=VALUES(module),"
                "self_status=VALUES(self_status),self_schedule=VALUES(self_schedule),self_note=VALUES(self_note),"
                "self_attachments=VALUES(self_attachments),updated_at=NOW()",
                (row["tenant_gid"], row["item_gid"], row["actor_gid"], row["module"], row["status"], row["schedule"] or "",
                 row["note"], json.dumps(row["attachments"], ensure_ascii=False)),
            )
            cur.execute(
                "INSERT INTO workmanship_base_self_annotation_states (tenant_gid,item_gid,user_gid,revision,deleted,restore_json) "
                "VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE revision=VALUES(revision),deleted=VALUES(deleted),restore_json=VALUES(restore_json)",
                (row["tenant_gid"], row["item_gid"], row["actor_gid"], row["revision"], row["deleted"],
                 json.dumps(row["restore"], ensure_ascii=False) if row["restore"] else None),
            )

    def claim(self, *, tenant_gid: str, actor_gid: str, operation: str, idempotency_key: str, command_digest: str) -> dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_base_self_annotation_idempotency "
                "(tenant_gid,actor_gid,operation,idempotency_key,command_digest,status) VALUES (%s,%s,%s,%s,%s,'pending') "
                "ON DUPLICATE KEY UPDATE actor_gid=VALUES(actor_gid)",
                (tenant_gid, actor_gid, operation, idempotency_key, command_digest),
            )
            cur.execute(
                "SELECT command_digest,status,result_json FROM workmanship_base_self_annotation_idempotency "
                "WHERE tenant_gid=%s AND actor_gid=%s AND operation=%s AND idempotency_key=%s FOR UPDATE",
                (tenant_gid, actor_gid, operation, idempotency_key),
            )
            row = cur.fetchone()
        if row and str(row.get("command_digest") or "") != command_digest:
            raise SelfAnnotationError("idempotency_conflict", "幂等键已用于不同命令")
        return _json(row.get("result_json"), None) if row and row.get("status") == "completed" else None

    def complete(self, *, tenant_gid: str, actor_gid: str, operation: str, idempotency_key: str,
                 result: dict[str, Any], item_gid: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                "UPDATE workmanship_base_self_annotation_idempotency SET status='completed',item_gid=%s,result_json=%s,completed_at=CURRENT_TIMESTAMP(6) "
                "WHERE tenant_gid=%s AND actor_gid=%s AND operation=%s AND idempotency_key=%s",
                (item_gid, json.dumps(result, ensure_ascii=False), tenant_gid, actor_gid, operation, idempotency_key),
            )

    def audit(self, event: dict[str, Any]) -> None:
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_base_self_annotation_audit_events "
                "(gid,tenant_gid,item_gid,actor_gid,operation,idempotency_key,status,details_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (str(next_gid()), event["tenant_gid"], event["item_gid"], event["actor_gid"], event["operation"],
                 event["idempotency_key"], event["status"], json.dumps(event["details"], ensure_ascii=False)),
            )


class AttachmentVisibilityPort(Protocol):
    def new_reference_visible(self, *, actor: dict[str, Any], reference: dict[str, Any]) -> bool: ...
    def register_legacy_reference(self, *, actor: dict[str, Any], reference: dict[str, Any]) -> None: ...


class SqlAttachmentVisibilityPort:
    def __init__(self, repository: SqlSelfAnnotationRepository) -> None:
        self.repository = repository

    def new_reference_visible(self, *, actor: dict[str, Any], reference: dict[str, Any]) -> bool:
        return self.repository.attachment_reference_registered(actor=actor, reference=reference)

    def register_legacy_reference(self, *, actor: dict[str, Any], reference: dict[str, Any]) -> None:
        self.repository.register_attachment_reference(actor=actor, reference=reference)


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_gid": str(row["item_gid"]), "actor_gid": str(row.get("user_gid") or row.get("actor_gid") or ""),
        "tenant_gid": str(row.get("tenant_gid") or ""), "module": str(row.get("module") or ""),
        "status": str(row.get("self_status", row.get("status")) or ""),
        "schedule": str(row.get("self_schedule", row.get("schedule")) or "") or None,
        "note": str(row.get("self_note", row.get("note")) or ""),
        "attachments": _typed_attachments(row.get("self_attachments", row.get("attachments"))),
        "revision": int(row.get("revision") or 1), "deleted": bool(row.get("deleted")),
        "restore": _json(row.get("restore_json", row.get("restore")), None),
    }


class SelfAnnotationService:
    def __init__(self, *, repository: Any | None = None, visibility_port: AttachmentVisibilityPort | None = None) -> None:
        self.repository = repository or SqlSelfAnnotationRepository()
        self.visibility_port = visibility_port or SqlAttachmentVisibilityPort(self.repository)

    def get(self, *, actor: dict, item_gid: str) -> dict:
        gid = _text(item_gid, label="item_gid", maximum=128)
        tenant_gid = _tenant_gid(actor)
        with self.repository.transaction():
            row = self.repository.get(tenant_gid=tenant_gid, actor_gid=_actor_gid(actor), item_gid=gid or "")
            return {"annotation": self._project(row or self._empty(actor, gid or ""))}

    def batch(self, *, actor: dict, item_gids: list[str]) -> dict:
        if not isinstance(item_gids, list) or len(item_gids) > 200:
            _invalid("item_gids 无效")
        gids = [_text(value, label="item_gids", maximum=128) or "" for value in item_gids]
        with self.repository.transaction():
            rows = self.repository.batch(tenant_gid=_tenant_gid(actor), actor_gid=_actor_gid(actor), item_gids=gids)
        return {"items": [self._summary(row) for row in rows if not row["deleted"]]}

    def search(self, *, actor: dict, query: dict) -> dict:
        if not isinstance(query, dict) or set(query) - {"limit", "status", "module"}:
            _invalid()
        limit = query.get("limit", 200)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            _invalid("limit 无效")
        status = _text(query["status"], label="status", maximum=64, nullable=True) if "status" in query else None
        module = _text(query["module"], label="module", maximum=128, nullable=True) if "module" in query else None
        with self.repository.transaction():
            rows = self.repository.list(tenant_gid=_tenant_gid(actor), actor_gid=_actor_gid(actor), limit=limit,
                                        status=status, module=module)
        return {"items": [self._project(row) for row in rows]}

    def apply_change(self, *, actor: dict, command: dict) -> dict:
        if not isinstance(command, dict) or set(command) != _COMMAND_KEYS:
            _invalid()
        item_gid = _text(command["item_gid"], label="item_gid", maximum=128)
        status = _text(command["status"], label="status", maximum=64)
        schedule = _text(command["schedule"], label="schedule", maximum=128, nullable=True)
        note = _text(command["note"], label="note", maximum=2000)
        key = _text(command["idempotency_key"], label="idempotency_key", maximum=512)
        expected = command["expected_revision"]
        if not item_gid or not status or note is None or not key or isinstance(expected, bool) or not isinstance(expected, int) or expected < 1:
            _invalid()
        if not isinstance(command["attachments"], list) or len(command["attachments"]) > 100:
            _invalid("attachments 无效")
        attachments = [_attachment(value) for value in command["attachments"]]
        if len({_reference_key(item) for item in attachments}) != len(attachments):
            _invalid("attachments 无效")
        actor_gid, tenant_gid, command_digest = _actor_gid(actor), _tenant_gid(actor), _digest(command)
        with self.repository.transaction():
            replay = self.repository.claim(tenant_gid=tenant_gid, actor_gid=actor_gid, operation="change.apply",
                                           idempotency_key=key, command_digest=command_digest)
            if replay is not None:
                return replay
            row = self.repository.get(tenant_gid=tenant_gid, actor_gid=actor_gid, item_gid=item_gid, lock=True) or self._empty(actor, item_gid)
            if row["revision"] != expected:
                raise SelfAnnotationError("revision_conflict", "标注版本已变化")
            existing = {_reference_key(value) for value in row["attachments"]}
            for reference in attachments:
                exact_existing = _reference_key(reference) in existing
                visible = self.visibility_port.new_reference_visible(actor=actor, reference=reference)
                if exact_existing and not visible and hasattr(self.visibility_port, "register_legacy_reference"):
                    self.visibility_port.register_legacy_reference(actor=actor, reference=reference)
                    visible = True
                if not exact_existing and not visible:
                    raise SelfAnnotationError("attachment_not_visible", "附件不可见或尚未登记")
            deleted = status == "deleted" and schedule is None and note == "" and not attachments
            row.update({"status": status, "schedule": schedule, "note": note, "attachments": attachments,
                        "revision": row["revision"] + 1, "deleted": deleted,
                        "restore": {"available": True, "deleted_by": actor_gid, "deleted_at": datetime.now(UTC).isoformat()} if deleted else None})
            self.repository.save(row)
            result = {"annotation": self._project(row)}
            self.repository.complete(tenant_gid=tenant_gid, actor_gid=actor_gid, operation="change.apply",
                                     idempotency_key=key, result=result, item_gid=item_gid)
            self.repository.audit({"tenant_gid": tenant_gid, "item_gid": item_gid, "actor_gid": actor_gid,
                                   "operation": "change.apply", "idempotency_key": key, "status": "succeeded",
                                   "details": {"deleted": deleted, "revision": row["revision"], "command_digest": command_digest}})
            return result

    @staticmethod
    def _empty(actor: dict, item_gid: str) -> dict:
        return {"item_gid": item_gid, "actor_gid": _actor_gid(actor), "tenant_gid": _tenant_gid(actor), "module": "",
                "status": "", "schedule": None, "note": "", "attachments": [], "revision": 1, "deleted": False, "restore": None}

    @staticmethod
    def _summary(row: dict) -> dict:
        return {"item_gid": row["item_gid"], "status": row["status"], "schedule": row["schedule"] or "",
                "has_note": bool(row["note"]), "attach_count": len(row["attachments"])}

    @staticmethod
    def _project(row: dict) -> dict:
        return {key: deepcopy(row[key]) for key in ("item_gid", "status", "schedule", "note", "attachments", "revision", "deleted", "restore")}


def _reference_key(reference: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(reference[key] for key in ("attachment_gid", "media_type", "display_name", "size", "checksum"))


__all__ = ["AttachmentVisibilityPort", "SelfAnnotationError", "SelfAnnotationService", "SqlAttachmentVisibilityPort", "SqlSelfAnnotationRepository"]

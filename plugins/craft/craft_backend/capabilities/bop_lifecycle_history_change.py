"""Governed undo/redo of a BOP line operation-history batch."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilitySpec

from ..data.connection import get_craft_conn
from ..routers._bop import _history


OPERATIONS = ("undo", "redo")


def _required(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _row_value(row: Any, key: str) -> Any:
    return row.get(key) if isinstance(row, dict) else dict(row).get(key)


def _summary(events: list[dict[str, Any]], direction: str) -> tuple[list[dict[str, Any]], list[str]]:
    summary: list[dict[str, Any]] = []
    affected: list[str] = []
    for event in (reversed(events) if direction == "undo" else events):
        op_type = event.get("op_type")
        entity_title = event.get("entity_title") or ""
        state_key = "old_state" if direction == "undo" else "new_state"
        if op_type in ("create_entry", "delete_entry"):
            entries = (event.get(state_key) or {}).get("entries", [])
            for entry in entries:
                entity_title = entry.get("title", entity_title)
                if entry.get("gid"):
                    affected.append(entry["gid"])
        if event.get("entity_gid"):
            affected.append(event["entity_gid"])
        summary.append({"op_type": op_type, "entity_gid": event.get("entity_gid"), "entity_title": entity_title})
    return summary, list(dict.fromkeys(affected))


def _redo_guard(cur: Any, events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    guard: dict[str, list[dict[str, Any]]] = {"entries": []}
    for event in events:
        entity_gid = event.get("entity_gid")
        if not entity_gid:
            continue
        cur.execute("SELECT updated_at FROM workmanship_bop_bop_entries WHERE gid=%s", (entity_gid,))
        row = cur.fetchone()
        if row:
            guard["entries"].append({"gid": entity_gid, "updated_at": _row_value(row, "updated_at")})
    return guard


def apply_bop_lifecycle_history_change(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    if operation not in OPERATIONS:
        raise ValueError("operation must be one of: undo, redo")
    version_gid = _required(payload, "version_gid")
    line_gid = _required(payload, "line_gid")
    user_gid = context.user_gid or ""

    with get_craft_conn() as conn, conn.cursor() as cur:
        _history.ensure_history_schema(cur)
        sql = _history.latest_active_batch_sql() if operation == "undo" else _history.latest_undo_batch_sql()
        cur.execute(sql, (version_gid, line_gid))
        row = cur.fetchone()
        if not row:
            raise CapabilityBusinessError("resource_not_found", "没有可撤销的历史操作" if operation == "undo" else "没有可重做的历史操作")
        batch_id = _row_value(row, "batch_id")
        events = _history.fetch_batch_events(cur, version_gid, line_gid, batch_id)
        if not events:
            raise CapabilityBusinessError("resource_not_found", "批次历史不存在")

        if operation == "redo" and not _history.validate_redo_guard(cur, _redo_guard(cur, events)):
            _history.mark_batch_status(cur, version_gid, line_gid, batch_id, "redo_invalidated", user_gid)
            conn.commit()
            raise CapabilityBusinessError("invalid_state", "重做已失效：目标对象在撤销后已被修改")

        direction = operation
        for event in (reversed(events) if direction == "undo" else events):
            _history.apply_history_event(cur, event, direction=direction)
        _history.mark_batch_status(cur, version_gid, line_gid, batch_id, "undone" if operation == "undo" else "active", user_gid)
        summary, affected = _summary(events, direction)
        history_data = _history.fetch_line_history(cur, version_gid, line_gid, limit=50)
        conn.commit()
        return {
            "data": {
                "batch_id": batch_id,
                "status": "undone" if operation == "undo" else "active",
                "version_gid": version_gid,
                "line_gid": line_gid,
                "summary": summary,
                "affected_entries": affected,
                "operation_log": history_data["items"],
                "latest_active_batch_id": history_data["latest_active_batch_id"],
            }
        }


def register_bop_lifecycle_history_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.lifecycle.history.change.apply", owner="craft",
        description="Undo or redo one governed BOP line operation-history batch.",
        use_when="A governed Craft consumer explicitly undoes or redoes the latest eligible line history batch.",
        do_not_use_when="The request creates/restores a checkpoint, edits an entry directly, or changes lifecycle phase state.",
        risk="write", confirmation="user", idempotent=False, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["operation", "version_gid", "line_gid"], "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "additionalProperties": True},
        tags=("craft", "bop", "lifecycle", "history", "write"),
    ), apply_bop_lifecycle_history_change)


__all__ = ["OPERATIONS", "apply_bop_lifecycle_history_change", "register_bop_lifecycle_history_change_capability"]

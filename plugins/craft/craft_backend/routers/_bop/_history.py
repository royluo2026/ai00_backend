import copy
import json
from typing import Any


_HISTORY_DDL = (
    "ALTER TABLE workmanship_bop_bop_line_operation_log ADD COLUMN IF NOT EXISTS batch_status TEXT NOT NULL DEFAULT 'active'",
    "ALTER TABLE workmanship_bop_bop_line_operation_log ADD COLUMN IF NOT EXISTS redo_guard_json JSON DEFAULT NULL",
    "ALTER TABLE workmanship_bop_bop_line_operation_log ADD COLUMN IF NOT EXISTS touched_refs_json JSON DEFAULT NULL",
    "ALTER TABLE workmanship_bop_bop_line_operation_log ADD COLUMN IF NOT EXISTS undone_at DATETIME(6) DEFAULT NULL",
    "ALTER TABLE workmanship_bop_bop_line_operation_log ADD COLUMN IF NOT EXISTS undone_by TEXT DEFAULT NULL",
    "ALTER TABLE workmanship_bop_bop_line_operation_log ADD COLUMN IF NOT EXISTS redone_at DATETIME(6) DEFAULT NULL",
    "ALTER TABLE workmanship_bop_bop_line_operation_log ADD COLUMN IF NOT EXISTS redone_by TEXT DEFAULT NULL",
    "ALTER TABLE workmanship_bop_bop_line_operation_log ADD COLUMN IF NOT EXISTS invalidate_reason TEXT DEFAULT NULL",
    "CREATE TABLE IF NOT EXISTS workmanship_bop_bop_line_history_state (version_gid CHAR(36) NOT NULL, line_gid CHAR(36) NOT NULL, current_batch_id TEXT DEFAULT NULL, current_direction TEXT NOT NULL DEFAULT 'active', updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6), PRIMARY KEY (version_gid, line_gid)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
)


def is_history_admin(user: dict | None) -> bool:
    actor_role = (user or {}).get("org_role") or (user or {}).get("system_role", "external")
    return actor_role in ("super_admin", "project_admin", "team_admin")


def can_manage_line_history(user: dict | None, performed_by: str | None) -> bool:
    return True


def ensure_history_schema(cur) -> None:
    for sql in _HISTORY_DDL:
        cur.execute(sql)


def latest_active_batch_sql() -> str:
    return (
        "SELECT batch_id "
        "FROM workmanship_bop_bop_line_operation_log "
        "WHERE version_gid=%s AND line_gid=%s AND batch_status='active' "
        "ORDER BY performed_at DESC, op_seq DESC LIMIT 1"
    )


def latest_undo_batch_sql() -> str:
    return (
        "SELECT batch_id "
        "FROM workmanship_bop_bop_line_operation_log "
        "WHERE version_gid=%s AND line_gid=%s AND batch_status='undone' "
        "ORDER BY undone_at DESC, op_seq DESC LIMIT 1"
    )


def fetch_batch_events(cur, version_gid: str, line_gid: str, batch_id: str) -> list[dict[str, Any]]:
    ensure_history_schema(cur)
    cur.execute(
        "SELECT gid, batch_id, op_type, entity_gid, entity_title, old_state, new_state, "
        "op_seq, performed_by, performed_by_name, performed_at, rolled_back, batch_status, invalidate_reason "
        "FROM workmanship_bop_bop_line_operation_log "
        "WHERE version_gid=%s AND line_gid=%s AND batch_id=%s "
        "ORDER BY op_seq ASC, performed_at ASC",
        (version_gid, line_gid, batch_id),
    )
    rows = [dict(r) for r in cur.fetchall()]
    for row in rows:
        for field in ("old_state", "new_state"):
            if isinstance(row.get(field), str):
                try:
                    row[field] = json.loads(row[field])
                except Exception:
                    pass
    return rows


def mark_batch_status(cur, version_gid: str, line_gid: str, batch_id: str, status: str, user_gid: str | None = None) -> None:
    set_parts = ["batch_status=%s"]
    params: list[Any] = [status]
    if status == "undone":
        set_parts.append("undone_at=NOW()")
        set_parts.append("undone_by=%s")
        params.append(user_gid or "")
    elif status == "active":
        set_parts.append("redone_at=NOW()")
        set_parts.append("redone_by=%s")
        params.append(user_gid or "")
        set_parts.append("invalidate_reason=NULL")
    elif status == "redo_invalidated":
        set_parts.append("invalidate_reason=%s")
        params.append("target changed after undo")
    params.extend([version_gid, line_gid, batch_id])
    cur.execute(
        f"UPDATE workmanship_bop_bop_line_operation_log SET {', '.join(set_parts)} WHERE version_gid=%s AND line_gid=%s AND batch_id=%s",
        params,
    )


def validate_redo_guard(cur, guard: dict[str, Any] | None) -> bool:
    if not guard:
        return True
    for entry in guard.get("entries", []):
        cur.execute(
            "SELECT updated_at FROM workmanship_bop_bop_entries WHERE gid=%s",
            (entry.get("gid"),),
        )
        row = cur.fetchone()
        if not row:
            return False
        if str(row.get("updated_at")) != str(entry.get("updated_at")):
            return False
    return True


    ensure_history_schema(cur)
    cur.execute(
        "SELECT gid FROM workmanship_bop_bop_entries WHERE gid=%s AND version_gid=%s AND is_deleted=FALSE",
        (line_gid, version_gid),
    )
    if not cur.fetchone():
        return {"items": [], "latest_active_batch_id": None}

    cur.execute(
        "SELECT gid, batch_id, op_type, entity_gid, entity_title, old_state, new_state, "
        "op_seq, performed_by, performed_by_name, performed_at, rolled_back, batch_status, invalidate_reason "
        "FROM workmanship_bop_bop_line_operation_log "
        "WHERE version_gid=%s AND line_gid=%s "
        "ORDER BY performed_at DESC, op_seq DESC LIMIT %s",
        (version_gid, line_gid, limit),
    )
    items = [dict(r) for r in cur.fetchall()]

    cur.execute(latest_active_batch_sql(), (version_gid, line_gid))
    latest_row = cur.fetchone()
    return {
        "items": items,
        "latest_active_batch_id": latest_row.get("batch_id") if latest_row else None,
    }


def _normalize_pic_item(item: Any) -> dict[str, str]:
    if isinstance(item, dict):
        return {
            "url": str(item.get("url") or "").strip(),
            "object_key": str(item.get("object_key") or "").strip(),
            "storage": str(item.get("storage") or "").strip(),
        }
    return {
        "url": str(item or "").strip(),
        "object_key": "",
        "storage": "",
    }


def _normalize_pic_list(items: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in items or []:
        normalized = _normalize_pic_item(item)
        if normalized["url"] or normalized["object_key"]:
            out.append(normalized)
    return out


def _pic_identity(item: dict[str, str]) -> str:
    return json.dumps(item, ensure_ascii=False, sort_keys=True)


def build_entry_update_steps(before_entry: dict[str, Any], patch: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    current_state = copy.deepcopy(before_entry)

    for field in ("process_flow_pic", "cad_sim_pics"):
        if field not in patch:
            continue

        before_pics = _normalize_pic_list(current_state.get(field))
        after_pics = _normalize_pic_list(patch.get(field))
        before_ids = [_pic_identity(item) for item in before_pics]
        after_ids = [_pic_identity(item) for item in after_pics]

        common_ids = list(before_ids)
        remove_ids = [item_id for item_id in before_ids if item_id not in after_ids]
        add_ids = [item_id for item_id in after_ids if item_id not in before_ids]

        id_to_item = {_pic_identity(item): item for item in after_pics}
        id_to_item.update({_pic_identity(item): item for item in before_pics})

        working = [copy.deepcopy(id_to_item[item_id]) for item_id in common_ids if item_id in id_to_item]

        for removed_id in remove_ids:
            before_snapshot = copy.deepcopy(working)
            working = [item for item in working if _pic_identity(item) != removed_id]
            steps.append(
                {
                    "op_type": "update_entry_image_remove",
                    "field": field,
                    "old_state": {field: before_snapshot},
                    "new_state": {field: copy.deepcopy(working)},
                }
            )

        for item in after_pics:
            item_id = _pic_identity(item)
            if item_id not in add_ids:
                continue
            before_snapshot = copy.deepcopy(working)
            working.append(copy.deepcopy(item))
            steps.append(
                {
                    "op_type": "update_entry_image_add",
                    "field": field,
                    "old_state": {field: before_snapshot},
                    "new_state": {field: copy.deepcopy(working)},
                }
            )

        current_state[field] = copy.deepcopy(working)

    scalar_updates = {}
    for key, value in patch.items():
        if key in {"process_flow_pic", "cad_sim_pics"}:
            continue
        if current_state.get(key) == value:
            continue
        scalar_updates[key] = value

    if scalar_updates:
        old_state = {key: current_state.get(key) for key in scalar_updates}
        current_state.update(copy.deepcopy(scalar_updates))
        steps.append(
            {
                "op_type": "update_entry",
                "field": None,
                "old_state": old_state,
                "new_state": copy.deepcopy(scalar_updates),
            }
        )

    return steps


def _normalize_state_for_write(state: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(state)
    for field in ("process_flow_pic", "cad_sim_pics"):
        if field in normalized:
            normalized[field] = _normalize_pic_list(normalized[field])
    return normalized


def _restore_entry_snapshot(cur, entry: dict[str, Any]) -> None:
    set_parts = []
    params = []
    for key in ("title", "node_type", "parent_gid", "vpps"):
        if key in entry:
            set_parts.append(f"{key}=%s")
            params.append(entry[key])
    set_parts.extend(["is_deleted=FALSE", "deleted_at=NULL"])
    cur.execute(
        f"UPDATE workmanship_bop_bop_entries SET {', '.join(set_parts)} WHERE gid=%s",
        params + [entry.get("gid")],
    )


def _soft_delete_entry_snapshot(cur, entry: dict[str, Any]) -> None:
    cur.execute(
        "UPDATE workmanship_bop_bop_entries SET is_deleted=TRUE, deleted_at=NOW() WHERE gid=%s",
        (entry.get("gid"),),
    )


def _restore_link_snapshot(cur, link: dict[str, Any]) -> None:
    cur.execute(
        "INSERT INTO workmanship_bop_bop_entry_links (gid, entry_gid, version_gid, link_type, entity_gid, is_primary) VALUES (%s,%s,%s,%s,%s,%s)",
        (link.get("gid"), link.get("entry_gid"), link.get("version_gid"), link.get("link_type"), link.get("entity_gid"), link.get("is_primary", False)),
    )


def _soft_delete_link_snapshot(cur, link: dict[str, Any]) -> None:
    if link.get("gid"):
        cur.execute(
            "UPDATE workmanship_bop_bop_entry_links SET deleted_at=NOW() WHERE gid=%s",
            (link.get("gid"),),
        )
        return
    cur.execute(
        "DELETE FROM workmanship_bop_bop_entry_links WHERE entry_gid=%s AND link_type=%s AND entity_gid=%s",
        (link.get("entry_gid"), link.get("link_type"), link.get("entity_gid")),
    )


def _restore_owned_snapshot(cur, owned: dict[str, Any]) -> None:
    set_parts = ["deleted_at=NULL"]
    params = []
    if "title" in owned:
        set_parts.insert(0, "title=%s")
        params.append(owned.get("title"))
    cur.execute(
        f"UPDATE {owned.get('table')} SET {', '.join(set_parts)} WHERE gid=%s",
        params + [owned.get("gid")],
    )


def _soft_delete_owned_snapshot(cur, owned: dict[str, Any]) -> None:
    cur.execute(
        f"UPDATE {owned.get('table')} SET deleted_at=NOW() WHERE gid=%s",
        (owned.get("gid"),),
    )


def apply_history_event(cur, event: dict[str, Any], direction: str) -> None:
    if direction not in {"undo", "redo"}:
        raise ValueError("direction must be undo or redo")

    op_type = event.get("op_type")
    entry_gid = event.get("entity_gid")
    source_state = event.get("old_state") if direction == "undo" else event.get("new_state")

    if op_type == "update_entry":
        payload = _normalize_state_for_write(source_state or {})
        set_parts = []
        params = []
        for key, value in payload.items():
            if key in {"process_flow_pic", "cad_sim_pics"}:
                set_parts.append(f"{key}=%s")
                params.append(json.dumps(value, ensure_ascii=False))
            else:
                set_parts.append(f"{key}=%s")
                params.append(value)
        if set_parts:
            set_parts.append("updated_at=NOW()")
            cur.execute(
                f"UPDATE workmanship_bop_bop_entries SET {', '.join(set_parts)} WHERE gid=%s",
                params + [entry_gid],
            )
        return

    if op_type == "create_entry":
        payload = (event.get("new_state") if direction == "undo" else event.get("new_state")) or {}
        if direction == "undo":
            for entry in payload.get("entries", []):
                _soft_delete_entry_snapshot(cur, entry)
            for link in payload.get("links", []):
                _soft_delete_link_snapshot(cur, link)
            for owned in payload.get("owned_entities", []):
                _soft_delete_owned_snapshot(cur, owned)
        else:
            for entry in payload.get("entries", []):
                _restore_entry_snapshot(cur, entry)
            for link in payload.get("links", []):
                _restore_link_snapshot(cur, link)
            for owned in payload.get("owned_entities", []):
                _restore_owned_snapshot(cur, owned)
        return

    if op_type == "delete_entry":
        payload = source_state or {}
        if direction == "undo":
            for entry in payload.get("entries", []):
                _restore_entry_snapshot(cur, entry)
            for link in payload.get("links", []):
                _restore_link_snapshot(cur, link)
            for owned in payload.get("owned_entities", []):
                _restore_owned_snapshot(cur, owned)
        else:
            for entry in payload.get("entries", []) or [{"gid": entry_gid}]:
                _soft_delete_entry_snapshot(cur, entry)
            for link in payload.get("links", []):
                _soft_delete_link_snapshot(cur, link)
            for owned in payload.get("owned_entities", []):
                _soft_delete_owned_snapshot(cur, owned)
        return

    if op_type == "add_link":
        payload = (event.get("new_state") if direction == "undo" else event.get("new_state")) or {}
        if direction == "undo":
            cur.execute(
                "DELETE FROM workmanship_bop_bop_entry_links WHERE entry_gid=%s AND link_type=%s AND entity_gid=%s",
                (entry_gid, payload.get("link_type"), payload.get("entity_gid")),
            )
        else:
            cur.execute(
                "INSERT INTO workmanship_bop_bop_entry_links (gid, entry_gid, version_gid, link_type, entity_gid, is_primary) VALUES (%s,%s,%s,%s,%s,%s)",
                (payload.get("link_gid") or f"redo-{entry_gid}-{payload.get('entity_gid')}", entry_gid, payload.get("version_gid") or '', payload.get("link_type"), payload.get("entity_gid"), payload.get("is_primary", False)),
            )
        return

    if op_type == "remove_link":
        payload = event.get("old_state") or {}
        if direction == "undo":
            cur.execute(
                "INSERT INTO workmanship_bop_bop_entry_links (gid, entry_gid, version_gid, link_type, entity_gid, is_primary) VALUES (%s,%s,%s,%s,%s,%s)",
                (payload.get("link_gid") or f"undo-{entry_gid}-{payload.get('entity_gid')}", entry_gid, payload.get("version_gid") or '', payload.get("link_type"), payload.get("entity_gid"), payload.get("is_primary", False)),
            )
        else:
            cur.execute(
                "DELETE FROM workmanship_bop_bop_entry_links WHERE entry_gid=%s AND link_type=%s AND entity_gid=%s",
                (entry_gid, payload.get("link_type"), payload.get("entity_gid")),
            )
        return

    raise NotImplementedError(f"history replay not implemented for {op_type}:{direction}")


def build_create_entry_snapshot(entry_row: dict[str, Any], link_row: dict[str, Any] | None = None, owned_entity: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "entries": [copy.deepcopy(entry_row)] if entry_row else [],
        "links": [copy.deepcopy(link_row)] if link_row else [],
        "owned_entities": [copy.deepcopy(owned_entity)] if owned_entity else [],
    }


def build_delete_entry_snapshot(entry_row: dict[str, Any], links: list[dict[str, Any]] | None = None, owned_entities: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "entries": [copy.deepcopy(entry_row)] if entry_row else [],
        "links": copy.deepcopy(links or []),
        "owned_entities": copy.deepcopy(owned_entities or []),
    }



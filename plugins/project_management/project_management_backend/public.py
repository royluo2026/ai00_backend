"""Versioned public projections for trusted in-process domain composition."""
from __future__ import annotations

from .infrastructure.repository import ProjectManagementRepository
from uuid import uuid4


_FOLLOW_OWNER_FIELDS = {
    "project": ("workmanship_proj_projects", "owner_gid"),
    "approval": ("workmanship_proj_approval_orders", "applicant_gid"),
}


def get_follow_item_owner(item_type: str, item_gid: str) -> str | None:
    target = _FOLLOW_OWNER_FIELDS.get(item_type)
    if not target:
        return None
    table, column = target
    row = ProjectManagementRepository().fetch_one(
        f"SELECT {column} FROM {table} WHERE gid=%s", (item_gid,)
    )
    return str(row[column]) if row and row.get(column) else None


def list_recent_follows(user_gid: str, limit: int = 20) -> list[dict]:
    safe_limit = max(1, min(int(limit), 100))
    return ProjectManagementRepository().fetch_all(
        "SELECT gid,item_type,item_gid,item_title,notify_on FROM workmanship_work_follows "
        f"WHERE user_gid=%s ORDER BY created_at DESC LIMIT {safe_limit}", (user_gid,)
    )


def publish_notification(user_gid: str, type_: str, item_type: str | None, item_gid: str | None, title: str, body: str = "") -> str:
    gid = str(uuid4())
    ProjectManagementRepository().create_notification(gid, {"user_gid": user_gid, "type": type_, "item_type": item_type, "item_gid": item_gid, "title": title, "body": body})
    return gid


def record_changes(
    connection,
    item_type: str,
    item_gid: str,
    list_gid: str | None,
    changed_by: str,
    changes: dict,
) -> None:
    """Persist Project-owned work-item field changes in the caller transaction."""
    rows = [
        (
            str(uuid4()), item_type, item_gid, list_gid, changed_by, field,
            str(old) if old is not None else None,
            str(new) if new is not None else None,
        )
        for field, (old, new) in changes.items()
        if str(old) != str(new)
    ]
    if not rows:
        return
    with connection.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO workmanship_work_item_change_logs "
            "(gid,item_type,item_gid,list_gid,changed_by,field_name,old_value,new_value) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            rows,
        )


__all__ = ["get_follow_item_owner", "list_recent_follows", "publish_notification", "record_changes"]

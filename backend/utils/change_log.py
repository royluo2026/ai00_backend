"""
backend/utils/change_log.py
─────────────────────────────
条目变更历史记录工具

调用方式：
    with get_conn() as conn:
        old_snap = ...read original...
        UPDATE ...
        record_changes(conn, 'task', gid, list_gid, changed_by, {
            'status': (old_status, new_status),
            'title':  (old_title,  new_title),
        })
        conn.commit()
"""
from backend.utils.gid import next_gid


def record_changes(
    conn,
    item_type: str,
    item_gid: str,
    list_gid: str | None,
    changed_by: str,
    changes: dict,  # {field_name: (old_value, new_value)}
) -> None:
    """批量写入变更日志。old_value 和 new_value 统一 str() 存储。"""
    rows = [
        (next_gid(), item_type, item_gid, list_gid, changed_by, field, str(old) if old is not None else None, str(new) if new is not None else None)
        for field, (old, new) in changes.items()
        if str(old) != str(new)  # 仅记录有变化的字段
    ]
    if not rows:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO workmanship_work_item_change_logs
               (gid, item_type, item_gid, list_gid, changed_by, field_name, old_value, new_value)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            rows,
        )

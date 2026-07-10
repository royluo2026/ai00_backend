"""
backend/routers/change_logs.py
──────────────────────────────
条目变更历史查询

GET /api/change-logs?item_type=&item_gid=  单条目历史
GET /api/change-logs?list_gid=             清单全量历史（仅 owner）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, HTTPException
from backend.db.connection import get_conn
from backend.routers.deps import get_current_user

router = APIRouter(prefix="/api/change-logs", tags=["change_logs"])


@router.get("")
def list_change_logs(
    item_type: str | None = Query(None),
    item_gid:  str | None = Query(None),
    list_gid:  str | None = Query(None),
    limit:     int        = Query(100, le=500),
    offset:    int        = Query(0),
    user: dict = Depends(get_current_user),
):
    """
    查询变更历史。
    - item_type + item_gid：单条目历史
      - owner（清单创建者）返回全量；其他人仅返回自己操作的
    - list_gid：清单维度，仅清单 owner 可访问
    """
    if not item_gid and not list_gid:
        raise HTTPException(400, "item_gid 或 list_gid 至少提供一个")

    user_gid = user["gid"]
    org_role  = user.get("org_role") or user.get("system_role", "member")
    is_super  = org_role == "super_admin"

    with get_conn() as conn:
        with conn.cursor() as cur:
            if list_gid:
                # 检查是否为清单 owner（或超管）
                if not is_super:
                    cur.execute(
                        "SELECT owner_gid FROM workmanship_work_lists WHERE gid = %s",
                        (list_gid,),
                    )
                    row = cur.fetchone()
                    if not row or row["owner_gid"] != user_gid:
                        raise HTTPException(403, "仅清单 owner 可查看全量变更历史")

                cur.execute(
                    """
                    SELECT gid, item_type, item_gid, list_gid, changed_by,
                           changed_at, field_name, old_value, new_value
                    FROM workmanship_work_item_change_logs
                    WHERE list_gid = %s
                    ORDER BY changed_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (list_gid, limit, offset),
                )
            else:
                # 单条目历史：先检查是否为 owner
                is_owner = False
                if not is_super:
                    # 通过 list_gid 反查 owner
                    cur.execute(
                        """
                        SELECT l.owner_gid
                        FROM workmanship_work_item_change_logs cl
                        JOIN workmanship_work_lists l ON l.gid = cl.list_gid
                        WHERE cl.item_type = %s AND cl.item_gid = %s
                        LIMIT 1
                        """,
                        (item_type, item_gid),
                    )
                    owner_row = cur.fetchone()
                    is_owner = owner_row and owner_row["owner_gid"] == user_gid

                if is_super or is_owner:
                    # 全量
                    cur.execute(
                        """
                        SELECT gid, item_type, item_gid, list_gid, changed_by,
                               changed_at, field_name, old_value, new_value
                        FROM workmanship_work_item_change_logs
                        WHERE item_type = %s AND item_gid = %s
                        ORDER BY changed_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (item_type, item_gid, limit, offset),
                    )
                else:
                    # 仅自己的操作
                    cur.execute(
                        """
                        SELECT gid, item_type, item_gid, list_gid, changed_by,
                               changed_at, field_name, old_value, new_value
                        FROM workmanship_work_item_change_logs
                        WHERE item_type = %s AND item_gid = %s
                          AND changed_by = %s
                        ORDER BY changed_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (item_type, item_gid, user_gid, limit, offset),
                    )

            rows = cur.fetchall()

    return [dict(r) for r in rows]

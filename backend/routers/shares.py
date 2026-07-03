"""
backend/routers/shares.py
──────────────────────────
点对点清单/条目分享 API

GET    /api/shares/lists/{list_gid}           列出清单分享（owner 权限）
POST   /api/shares/lists/{list_gid}           新增分享（owner 权限）
DELETE /api/shares/lists/{list_gid}/{gid}     删除分享
POST   /api/shares/items                      新增条目分享（清单 owner）
DELETE /api/shares/items/{gid}                删除条目分享
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.db.connection import get_conn
from backend.routers.deps import get_current_user
from backend.utils.gid import next_gid

router = APIRouter(tags=["shares"])


class ListShareBody(BaseModel):
    shared_to: str       # 被分享用户 gid
    permission: str = "read"   # 'read' | 'write'


class ItemShareBody(BaseModel):
    item_type: str
    item_gid: str
    shared_to: str
    permission: str = "read"


def _is_list_owner(conn, list_gid: str, user_gid: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT owner_gid, creator_gid FROM workmanship_work_lists WHERE gid = %s AND deleted_at IS NULL",
            (list_gid,),
        )
        row = cur.fetchone()
        if not row:
            return False
        return row["owner_gid"] == user_gid or row.get("creator_gid") == user_gid


@router.get("/api/shares/lists/{list_gid}")
def get_list_shares(list_gid: str, current_user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        if not _is_list_owner(conn, list_gid, current_user["gid"]):
            raise HTTPException(status_code=403, detail="仅清单 Owner 可查看分享")
        with conn.cursor() as cur:
            cur.execute(
                "SELECT s.*, u.name AS shared_to_name, u.avatar_url AS shared_to_avatar "
                "FROM workmanship_work_list_shares s "
                "LEFT JOIN workmanship_auth_users u ON u.gid = s.shared_to "
                "WHERE s.list_gid = %s ORDER BY s.created_at",
                (list_gid,),
            )
            return {"shares": [dict(r) for r in cur.fetchall()]}


@router.post("/api/shares/lists/{list_gid}", status_code=status.HTTP_201_CREATED)
def create_list_share(
    list_gid: str,
    body: ListShareBody,
    current_user: dict = Depends(get_current_user),
):
    with get_conn() as conn:
        if not _is_list_owner(conn, list_gid, current_user["gid"]):
            raise HTTPException(status_code=403, detail="仅清单 Owner 可分享")
        gid = next_gid()
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO workmanship_work_list_shares (gid, list_gid, shared_to, permission, shared_by)
                   VALUES (%s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE
                     permission = VALUES(permission), shared_by = VALUES(shared_by)""",
                (gid, list_gid, body.shared_to, body.permission, current_user["gid"]),
            )
            cur.execute(
                "SELECT * FROM workmanship_work_list_shares WHERE gid = %s",
                (gid,),
            )
            row = cur.fetchone()
        conn.commit()
    return {"share": dict(row)}


@router.delete("/api/shares/lists/{list_gid}/{gid}")
def delete_list_share(
    list_gid: str,
    gid: str,
    current_user: dict = Depends(get_current_user),
):
    with get_conn() as conn:
        if not _is_list_owner(conn, list_gid, current_user["gid"]):
            raise HTTPException(status_code=403, detail="仅清单 Owner 可撤销分享")
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM workmanship_work_list_shares WHERE gid = %s AND list_gid = %s",
                (gid, list_gid),
            )
        conn.commit()
    return {"ok": True}


@router.post("/api/shares/items", status_code=status.HTTP_201_CREATED)
def create_item_share(body: ItemShareBody, current_user: dict = Depends(get_current_user)):
    gid = next_gid()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO workmanship_work_item_shares
                   (gid, item_type, item_gid, shared_to, permission, shared_by)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE
                     permission = VALUES(permission), shared_by = VALUES(shared_by)""",
                (gid, body.item_type, body.item_gid, body.shared_to,
                 body.permission, current_user["gid"]),
            )
            cur.execute(
                "SELECT * FROM workmanship_work_item_shares WHERE gid = %s",
                (gid,),
            )
            row = cur.fetchone()
        conn.commit()
    return {"share": dict(row)}


@router.delete("/api/shares/items/{gid}")
def delete_item_share(gid: str, current_user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT shared_by FROM workmanship_work_item_shares WHERE gid = %s", (gid,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="分享不存在")
            if row["shared_by"] != current_user["gid"]:
                raise HTTPException(status_code=403, detail="仅分享创建者可撤销")
            cur.execute("DELETE FROM workmanship_work_item_shares WHERE gid = %s", (gid,))
        conn.commit()
    return {"ok": True}

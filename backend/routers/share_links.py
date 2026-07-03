"""
backend/routers/share_links.py
────────────────────────────────
分享链接 API

POST   /api/share-links              创建链接
GET    /api/share-links/{token}      解析 token → 返回 target 信息 + 当前用户权限
DELETE /api/share-links/{token}      撤销链接（owner 权限）
"""
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.db.connection import get_conn
from backend.routers.deps import get_current_user, get_current_user_optional, _derive_org_role

router = APIRouter(tags=["share_links"])


class ShareLinkBody(BaseModel):
    target_type: str           # 'list' | 'item'
    target_gid: str
    item_type: Optional[str] = None
    display_name: str = ""
    expires_at: Optional[str] = None


def _check_list_access(conn, list_gid: str, user_gid: str) -> str:
    """返回用户对清单的权限：'none' | 'read' | 'write'"""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT owner_gid, creator_gid, read_scope, write_scope, team_id FROM workmanship_work_lists "
            "WHERE gid = %s AND deleted_at IS NULL",
            (list_gid,),
        )
        row = cur.fetchone()
        if not row:
            return "none"
        lst = dict(row)
        # owner
        if lst.get("owner_gid") == user_gid or lst.get("creator_gid") == user_gid:
            return "write"
        # list_shares
        cur.execute(
            "SELECT permission FROM workmanship_work_list_shares WHERE list_gid=%s AND shared_to=%s",
            (list_gid, user_gid),
        )
        share_row = cur.fetchone()
        if share_row:
            return share_row["permission"]
        # read_scope 规则
        read_scope = lst.get("read_scope") or "team"
        if read_scope == "global":
            return "read"
        if read_scope == "team":
            # 同团队
            cur.execute(
                "SELECT team_id FROM workmanship_auth_users WHERE gid = %s", (user_gid,)
            )
            urow = cur.fetchone()
            if urow and urow["team_id"] and urow["team_id"] == lst.get("team_id"):
                return "read"
    return "none"


@router.post("/api/share-links", status_code=status.HTTP_201_CREATED)
def create_share_link(body: ShareLinkBody, current_user: dict = Depends(get_current_user)):
    token = secrets.token_urlsafe(16)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO workmanship_work_share_links
                   (token, target_type, target_gid, item_type, display_name, created_by, expires_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (token, body.target_type, body.target_gid, body.item_type,
                 body.display_name, current_user["gid"], body.expires_at),
            )
            cur.execute(
                "SELECT * FROM workmanship_work_share_links WHERE token = %s",
                (token,),
            )
            row = dict(cur.fetchone())
        conn.commit()
    return {"token": token, "link": row}


@router.get("/api/share-links/{token}")
def resolve_share_link(
    token: str,
    current_user: dict = Depends(get_current_user_optional),
):
    """解析分享链接，返回目标信息和当前用户权限。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM workmanship_work_share_links WHERE token = %s "
                "AND (expires_at IS NULL OR expires_at > NOW())",
                (token,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="链接不存在或已过期")
            link = dict(row)

        user_gid = current_user["gid"]
        current_perm = "none"
        can_request = False

        if link["target_type"] == "list":
            current_perm = _check_list_access(conn, link["target_gid"], user_gid)
            can_request = current_perm == "none"

    return {
        "target_type":       link["target_type"],
        "target_gid":        link["target_gid"],
        "item_type":         link.get("item_type"),
        "display_name":      link["display_name"],
        "current_permission": current_perm,
        "can_request":       can_request,
    }


@router.delete("/api/share-links/{token}")
def delete_share_link(token: str, current_user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT created_by FROM workmanship_work_share_links WHERE token = %s", (token,)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="链接不存在")
            org_role = current_user.get("org_role") or _derive_org_role(current_user.get("system_role", "external"))
            if row["created_by"] != current_user["gid"] and org_role != "super_admin":
                raise HTTPException(status_code=403, detail="仅创建者可撤销")
            cur.execute("DELETE FROM workmanship_work_share_links WHERE token = %s", (token,))
        conn.commit()
    return {"ok": True}

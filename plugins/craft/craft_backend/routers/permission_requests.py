"""
backend/routers/permission_requests.py
─────────────────────────────────────────
权限申请 API

POST   /api/permission-requests                  申请访问
GET    /api/permission-requests?target_gid=      列出申请（owner 查看）
POST   /api/permission-requests/{gid}/approve    批准 → 写 list_shares → 站内通知
POST   /api/permission-requests/{gid}/reject     拒绝 → 站内通知
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from ..data.connection import get_conn
from backend.platform_sdk.auth import get_current_user
from backend.platform_sdk.ids import next_gid
from backend.platform_sdk.identity import get_user_summaries
from backend.platform_sdk.notifications import publish_notification

router = APIRouter(tags=["permission_requests"])


class PermReqBody(BaseModel):
    target_type: str       # 'list' | 'item'
    target_gid: str
    want_permission: str = "read"
    message: str = ""


class RejectBody(BaseModel):
    message: str = ""


@router.post("/api/permission-requests", status_code=status.HTTP_201_CREATED)
def create_permission_request(body: PermReqBody, current_user: dict = Depends(get_current_user)):
    gid = next_gid()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO workmanship_work_permission_requests
                   (gid, requester_gid, target_type, target_gid, want_permission, message, status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (gid, current_user["gid"], body.target_type, body.target_gid,
                 body.want_permission, body.message, 'pending'),
            )
            cur.execute("SELECT * FROM workmanship_work_permission_requests WHERE gid = %s", (gid,))
            row = dict(cur.fetchone())
        conn.commit()
    return {"request": row}


@router.get("/api/permission-requests")
def list_permission_requests(
    target_gid: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: dict = Depends(get_current_user),
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            clauses = ["1=1"]
            params = []
            if target_gid:
                clauses.append("r.target_gid = %s")
                params.append(target_gid)
            if status_filter:
                clauses.append("r.status = %s")
                params.append(status_filter)
            cur.execute(
                f"SELECT r.* FROM workmanship_work_permission_requests r "
                f"WHERE {' AND '.join(clauses)} "
                f"ORDER BY r.created_at DESC LIMIT 200",
                params,
            )
            requests = [dict(r) for r in cur.fetchall()]
    users = get_user_summaries(row.get("requester_gid") for row in requests)
    for row in requests:
        user = users.get(str(row.get("requester_gid")), {})
        row["requester_name"] = user.get("name")
        row["requester_avatar"] = user.get("avatar_url")
    return {"requests": requests}


@router.post("/api/permission-requests/{gid}/approve")
def approve_permission_request(gid: str, current_user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM workmanship_work_permission_requests WHERE gid = %s", (gid,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="申请不存在")
            req = dict(row)
            if req["status"] != "pending":
                raise HTTPException(status_code=400, detail="申请已处理")

            # 写 list_shares
            if req["target_type"] == "list":
                share_gid = next_gid()
                cur.execute(
                    """INSERT INTO workmanship_work_list_shares (gid, list_gid, shared_to, permission, shared_by)
                       VALUES (%s, %s, %s, %s, %s)
                       ON DUPLICATE KEY UPDATE
                         permission = VALUES(permission)""",
                    (share_gid, req["target_gid"], req["requester_gid"],
                     req["want_permission"], current_user["gid"]),
                )
            # 更新申请状态
            cur.execute(
                "UPDATE workmanship_work_permission_requests SET status='approved', "
                "responded_by=%s, responded_at=NOW() WHERE gid=%s",
                (current_user["gid"], gid),
            )
        conn.commit()
    publish_notification(req["requester_gid"], "permission_approved", req["target_type"], req["target_gid"],
                         f"您申请访问 {req['target_gid']} 的权限已批准")
    return {"ok": True}


@router.post("/api/permission-requests/{gid}/reject")
def reject_permission_request(
    gid: str,
    body: RejectBody,
    current_user: dict = Depends(get_current_user),
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM workmanship_work_permission_requests WHERE gid = %s", (gid,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="申请不存在")
            req = dict(row)
            if req["status"] != "pending":
                raise HTTPException(status_code=400, detail="申请已处理")
            cur.execute(
                "UPDATE workmanship_work_permission_requests SET status='rejected', "
                "responded_by=%s, responded_at=NOW() WHERE gid=%s",
                (current_user["gid"], gid),
            )
        conn.commit()
    publish_notification(req["requester_gid"], "permission_rejected", req["target_type"], req["target_gid"],
                         f"您申请访问 {req['target_gid']} 的权限已被拒绝")
    return {"ok": True}

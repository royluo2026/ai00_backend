"""
backend/routers/follows.py
────────────────────────────
关注 API（follows）

端点：
  GET    /api/follows                → 当前用户关注列表
  POST   /api/follows                → 关注某条数据
  PATCH  /api/follows/{gid}          → 更新 notify_on 条件
  DELETE /api/follows/{gid}          → 取消关注
  GET    /api/follows/check          → 检查是否已关注（?item_type=&item_gid=）
"""
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.db.connection import get_conn
from backend.routers.deps import get_current_user
from backend.utils.gid import next_gid
from backend.utils.notif import create_notification
from plugins.craft.craft_backend.public import get_follow_item_owner

router = APIRouter(prefix="/api/follows", tags=["follows"])

# 合法条件集合（与 follow_trigger.py 保持同步）
_VALID_CONDITIONS = {"any_change", "status_change", "comment_added",
                     "resolved", "assigned_to_me", "mentioned"}


class CreateFollowBody(BaseModel):
    item_type: str  # task|issue|project|knowledge|rule|std_op|work_plan
    item_gid: str
    item_title: str = ""
    notify_on: List[str] = ["status_change", "resolved"]


class PatchFollowBody(BaseModel):
    notify_on: List[str]


@router.get("")
def list_follows(
    item_type: Optional[str] = Query(None, description="过滤 item_type（可选）"),
    current_user: dict = Depends(get_current_user),
):
    uid = current_user["gid"]
    with get_conn() as conn:
        with conn.cursor() as cur:
            if item_type:
                cur.execute(
                    "SELECT gid, item_type, item_gid, item_title, notify_on, created_at "
                    "FROM workmanship_work_follows WHERE user_gid = %s AND item_type = %s ORDER BY created_at DESC",
                    (uid, item_type)
                )
            else:
                cur.execute(
                    "SELECT gid, item_type, item_gid, item_title, notify_on, created_at "
                    "FROM workmanship_work_follows WHERE user_gid = %s ORDER BY created_at DESC",
                    (uid,)
                )
            rows = cur.fetchall()
    return {"success": True, "data": [
        {"gid": r["gid"], "item_type": r["item_type"], "item_gid": r["item_gid"],
         "item_title": r["item_title"], "notify_on": _parse_notify_on(r["notify_on"]),
         "created_at": str(r["created_at"])}
        for r in rows
    ]}


@router.get("/check")
def check_follow(
    item_type: str = Query(...),
    item_gid: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    uid = current_user["gid"]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid, notify_on FROM workmanship_work_follows "
                "WHERE user_gid = %s AND item_type = %s AND item_gid = %s",
                (uid, item_type, item_gid)
            )
            row = cur.fetchone()
    if row:
        return {"success": True, "data": {"followed": True, "gid": row["gid"], "notify_on": _parse_notify_on(row["notify_on"])}}
    return {"success": True, "data": {"followed": False}}


@router.post("", status_code=201)
def create_follow(body: CreateFollowBody, current_user: dict = Depends(get_current_user)):
    uid = current_user["gid"]
    gid = str(next_gid())
    with get_conn() as conn:
        # 查询 item 的 owner，准备发「有人关注了我的内容」通知
        owner_gid = get_follow_item_owner(body.item_type, body.item_gid)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO workmanship_work_follows (gid, user_gid, item_type, item_gid, item_title, notify_on) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (gid, uid, body.item_type, body.item_gid, body.item_title,
                     json.dumps([c for c in body.notify_on if c in _VALID_CONDITIONS]))
                )
        except Exception:
            raise HTTPException(status_code=409, detail="已关注该内容")

        # 通知 owner（若 owner 不是自己）
        if owner_gid and owner_gid != uid:
            try:
                create_notification(
                    conn,
                    user_gid=owner_gid,
                    type_="new_follower",
                    item_type=body.item_type,
                    item_gid=body.item_gid,
                    title=f"有人关注了你的{_item_type_label(body.item_type)}",
                    body=f"用户 {current_user.get('name','未知')} 开始关注",
                )
            except Exception:
                pass
        conn.commit()
    return {"success": True, "data": {"gid": gid}}


@router.delete("/{gid}")
def delete_follow(gid: str, current_user: dict = Depends(get_current_user)):
    uid = current_user["gid"]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM workmanship_work_follows WHERE gid = %s AND user_gid = %s",
                (gid, uid)
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="关注记录不存在")
        conn.commit()
    return {"success": True}


@router.patch("/{gid}")
def patch_follow(gid: str, body: PatchFollowBody, current_user: dict = Depends(get_current_user)):
    """更新关注条件（notify_on 列表）。"""
    uid = current_user["gid"]
    conditions = [c for c in body.notify_on if c in _VALID_CONDITIONS]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_work_follows SET notify_on = %s WHERE gid = %s AND user_gid = %s",
                (json.dumps(conditions), gid, uid)
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="关注记录不存在")
        conn.commit()
    return {"success": True, "data": {"notify_on": conditions}}


# ── 辅助函数 ──────────────────────────────────────────────────────

def _item_type_label(item_type: str) -> str:
    return {
        "task":      "任务",
        "issue":     "问题",
        "project":   "项目",
        "knowledge": "知识条目",
        "rule":      "规则",
        "std_op":    "标准工序",
        "work_plan": "工艺方案",
    }.get(item_type, "内容")


def _parse_notify_on(raw) -> list:
    """将数据库 notify_on 值解析为条件列表（兼容旧 TEXT 格式）。"""
    if isinstance(raw, list):
        return [c for c in raw if c in _VALID_CONDITIONS]
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith("["):
            try:
                arr = json.loads(s)
                return [c for c in arr if c in _VALID_CONDITIONS]
            except Exception:
                pass
        if s in ("all", "any_change"):
            return ["any_change"]
        if s == "key_changes":
            return ["status_change", "resolved", "assigned_to_me"]
        if s == "none":
            return []
        return [s] if s in _VALID_CONDITIONS else []
    return []

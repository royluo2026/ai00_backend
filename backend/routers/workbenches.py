"""
backend/routers/workbenches.py
──────────────────────────────
多工作台配置 API

端点：
  GET    /workbenches               → 列出个人 + 团队工作台
  POST   /workbenches               → 创建（同一 owner 最多 3 个）
  PATCH  /workbenches/{gid}         → 重命名 / 更新 widgets / 排序
  DELETE /workbenches/{gid}         → 删除
  GET    /workbenches/{gid}/override → 获取团队工作台的成员个性化
  PUT    /workbenches/{gid}/override → 保存 / 更新成员个性化
  DELETE /workbenches/{gid}/override → 重置成员个性化
"""
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from backend.db.connection import get_conn
from backend.routers.deps import get_current_user
from backend.utils.gid import next_gid

router = APIRouter(prefix="/api/workbenches", tags=["workbenches"])


class CreateWbBody(BaseModel):
    name: str
    owner_type: str = "user"              # 'user' | 'team'
    owner_gid: Optional[str] = None       # team_gid when owner_type='team'
    widgets: List[Dict[str, Any]] = []
    sort_order: int = 0


class UpdateWbBody(BaseModel):
    name: Optional[str] = None
    widgets: Optional[List[Dict[str, Any]]] = None
    sort_order: Optional[int] = None


# ── GET /workbenches ──────────────────────────────────────────────────────────

@router.get("")
def list_workbenches(current_user: dict = Depends(get_current_user)):
    user_gid = current_user["gid"]
    team_id  = current_user.get("team_id")

    with get_conn() as conn:
        with conn.cursor() as cur:
            # 个人工作台
            cur.execute(
                "SELECT gid, owner_type, owner_gid, name, sort_order, widgets,"
                "       created_at, updated_at"
                " FROM workmanship_app_workbench_configs"
                " WHERE owner_type='user' AND owner_gid=%s"
                " ORDER BY sort_order, created_at",
                (user_gid,),
            )
            personal = cur.fetchall()

            # 团队工作台
            team_rows = []
            if team_id:
                cur.execute(
                    "SELECT gid, owner_type, owner_gid, name, sort_order, widgets,"
                    "       created_at, updated_at"
                    " FROM workmanship_app_workbench_configs"
                    " WHERE owner_type='team' AND owner_gid=%s"
                    " ORDER BY sort_order, created_at",
                    (team_id,),
                )
                team_rows = cur.fetchall()

            # 该用户对团队工作台的个性化覆盖
            overrides: Dict[str, Any] = {}
            if team_rows:
                wb_gids = [r["gid"] for r in team_rows]
                _ph = ",".join(["%s"] * len(wb_gids))
                cur.execute(
                    f"SELECT workbench_gid, widgets"
                    f" FROM workmanship_app_workbench_member_overrides"
                    f" WHERE user_gid=%s AND workbench_gid IN ({_ph})",
                    [user_gid] + wb_gids,
                )
                for ov in cur.fetchall():
                    overrides[ov["workbench_gid"]] = (
                        ov["widgets"] if isinstance(ov["widgets"], list) else []
                    )

    def _row(r, override=None):
        d = {
            "gid":        r["gid"],
            "owner_type": r["owner_type"],
            "owner_gid":  r["owner_gid"],
            "name":       r["name"],
            "sort_order": r["sort_order"],
            "widgets":    r["widgets"] if isinstance(r["widgets"], list) else [],
            "created_at": str(r["created_at"]),
            "updated_at": str(r["updated_at"]),
        }
        if override is not None:
            d["override"] = override
        return d

    return {
        "success": True,
        "data": {
            "personal": [_row(r) for r in personal],
            "team":     [_row(r, overrides.get(r["gid"])) for r in team_rows],
        },
    }


# ── POST /workbenches ─────────────────────────────────────────────────────────

@router.post("", status_code=201)
def create_workbench(body: CreateWbBody, current_user: dict = Depends(get_current_user)):
    user_gid = current_user["gid"]
    team_id  = current_user.get("team_id")
    role     = current_user.get("system_role", "member")

    if body.owner_type == "team":
        if role not in ("super_admin", "team_admin"):
            raise HTTPException(403, "只有团队管理员可创建团队工作台")
        owner_gid = body.owner_gid or team_id
        if not owner_gid:
            raise HTTPException(400, "缺少 owner_gid（team_gid）")
    else:
        owner_gid = user_gid

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM workmanship_app_workbench_configs"
                " WHERE owner_type=%s AND owner_gid=%s",
                (body.owner_type, owner_gid),
            )
            cnt = cur.fetchone()["count"]
            if cnt >= 3:
                raise HTTPException(400, "每个用户/团队最多创建 3 个工作台")

            gid = str(next_gid())
            cur.execute(
                "INSERT INTO workmanship_app_workbench_configs"
                " (gid, owner_type, owner_gid, name, sort_order, widgets)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                (gid, body.owner_type, owner_gid, body.name,
                 body.sort_order, json.dumps(body.widgets)),
            )
        conn.commit()

    return {"success": True, "data": {"gid": gid, "name": body.name}}


# ── PATCH /workbenches/{gid} ──────────────────────────────────────────────────

@router.patch("/{gid}")
def update_workbench(gid: str, body: UpdateWbBody, current_user: dict = Depends(get_current_user)):
    user_gid = current_user["gid"]
    role     = current_user.get("system_role", "member")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT owner_type, owner_gid FROM workmanship_app_workbench_configs WHERE gid=%s", (gid,)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "工作台不存在")
            if row["owner_type"] == "user" and row["owner_gid"] != user_gid:
                raise HTTPException(403, "无权修改此工作台")
            if row["owner_type"] == "team" and role not in ("super_admin", "team_admin"):
                raise HTTPException(403, "只有团队管理员可修改团队工作台")

            set_parts: List[str] = []
            params: List[Any]    = []
            if body.name is not None:
                set_parts.append("name = %s")
                params.append(body.name)
            if body.sort_order is not None:
                set_parts.append("sort_order = %s")
                params.append(body.sort_order)
            if body.widgets is not None:
                set_parts.append("widgets = %s")
                params.append(json.dumps(body.widgets))
            if not set_parts:
                raise HTTPException(400, "没有需要更新的字段")
            set_parts.append("updated_at = NOW()")
            params.append(gid)

            cur.execute(
                f"UPDATE workmanship_app_workbench_configs SET {', '.join(set_parts)} WHERE gid=%s",
                params,
            )
        conn.commit()

    return {"success": True}


# ── DELETE /workbenches/{gid} ─────────────────────────────────────────────────

@router.delete("/{gid}")
def delete_workbench(gid: str, current_user: dict = Depends(get_current_user)):
    user_gid = current_user["gid"]
    role     = current_user.get("system_role", "member")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT owner_type, owner_gid FROM workmanship_app_workbench_configs WHERE gid=%s", (gid,)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "工作台不存在")
            if row["owner_type"] == "user" and row["owner_gid"] != user_gid:
                raise HTTPException(403, "无权删除此工作台")
            if row["owner_type"] == "team" and role not in ("super_admin", "team_admin"):
                raise HTTPException(403, "只有团队管理员可删除团队工作台")
            cur.execute("DELETE FROM workmanship_app_workbench_configs WHERE gid=%s", (gid,))
        conn.commit()

    return {"success": True}


# ── GET /workbenches/{gid}/override ──────────────────────────────────────────

@router.get("/{gid}/override")
def get_override(gid: str, current_user: dict = Depends(get_current_user)):
    user_gid = current_user["gid"]

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT widgets, updated_at FROM workmanship_app_workbench_member_overrides"
                " WHERE workbench_gid=%s AND user_gid=%s",
                (gid, user_gid),
            )
            row = cur.fetchone()

    if not row:
        return {"success": True, "data": None}
    return {
        "success": True,
        "data": {
            "widgets":    row["widgets"] if isinstance(row["widgets"], list) else [],
            "updated_at": str(row["updated_at"]),
        },
    }


# ── PUT /workbenches/{gid}/override ──────────────────────────────────────────

@router.put("/{gid}/override")
def upsert_override(
    gid: str,
    body: dict = Body(...),
    current_user: dict = Depends(get_current_user),
):
    user_gid = current_user["gid"]
    widgets  = body.get("widgets", [])

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT owner_type FROM workmanship_app_workbench_configs WHERE gid=%s", (gid,)
            )
            wb = cur.fetchone()
            if not wb:
                raise HTTPException(404, "工作台不存在")
            if wb["owner_type"] != "team":
                raise HTTPException(400, "只有团队工作台支持个人覆盖")

            ov_gid = str(next_gid())
            cur.execute(
                """INSERT INTO workmanship_app_workbench_member_overrides (gid, workbench_gid, user_gid, widgets)
                   VALUES (%s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE widgets=VALUES(widgets), updated_at=NOW()""",
                (ov_gid, gid, user_gid, json.dumps(widgets)),
            )
        conn.commit()

    return {"success": True}


# ── DELETE /workbenches/{gid}/override ───────────────────────────────────────

@router.delete("/{gid}/override")
def delete_override(gid: str, current_user: dict = Depends(get_current_user)):
    user_gid = current_user["gid"]

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM workmanship_app_workbench_member_overrides"
                " WHERE workbench_gid=%s AND user_gid=%s",
                (gid, user_gid),
            )
        conn.commit()

    return {"success": True}

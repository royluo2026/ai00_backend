"""
backend/routers/views.py
──────────────────────────
用户自定义视图配置 API

视图现在是清单的子实体：
  - list_gid NOT NULL：清单专属视图
  - list_gid IS NULL ：模块级全局视图（向后兼容）

端点：
  GET    /api/views                  列出视图（支持 module + list_gid 过滤）
  POST   /api/views                  创建视图
  PATCH  /api/views/{gid}            更新视图
  DELETE /api/views/{gid}            删除视图
  POST   /api/views/{gid}/copy       复制视图
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.db.connection import get_conn
from backend.routers.deps import require_role
from backend.utils.gid import next_gid

router = APIRouter(prefix="/api/views", tags=["views"])

_READ = require_role(
    "super_admin", "team_admin", "project_admin",
    "rule_admin", "knowledge_admin", "member",
)


# ── Pydantic 模型 ──────────────────────────────────────────────

class CreateViewBody(BaseModel):
    name: str = "未命名视图"
    module: str
    list_gid: Optional[str] = None   # None = 全局视图
    config: dict = {}
    is_shared: bool = False


class UpdateViewBody(BaseModel):
    name: Optional[str] = None
    config: Optional[dict] = None
    is_shared: Optional[bool] = None
    list_gid: Optional[str] = None   # 允许移动视图到不同清单


# ── 端点 ──────────────────────────────────────────────────────

@router.get("")
def list_views(
    module: str = "",
    list_gid: Optional[str] = None,
    user=Depends(_READ),
):
    """
    list_gid 指定时：返回该清单的视图（自己的 + 共享的）+ 该模块的共享全局视图
    list_gid 未指定时：返回全局视图（list_gid IS NULL）（自己的 + 共享的）
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            if module and list_gid:
                # 清单专属视图（自己的或共享的） + 模块级共享全局视图 + 用户私有全局视图
                cur.execute(
                    "SELECT gid,name,module,list_gid,owner_gid,is_shared,config,created_at,updated_at "
                    "FROM workmanship_app_view_configs "
                    "WHERE ("
                    "  (list_gid=%s AND (owner_gid=%s OR is_shared=TRUE))"
                    "  OR (list_gid IS NULL AND is_shared=TRUE AND module=%s)"
                    "  OR (list_gid IS NULL AND owner_gid=%s AND module=%s)"
                    ") "
                    "ORDER BY (owner_gid=%s) DESC, list_gid , created_at ASC",
                    (list_gid, user["gid"], module, user["gid"], module, user["gid"]),
                )
            elif module:
                # 全局视图（向后兼容）
                cur.execute(
                    "SELECT gid,name,module,list_gid,owner_gid,is_shared,config,created_at,updated_at "
                    "FROM workmanship_app_view_configs "
                    "WHERE list_gid IS NULL AND (owner_gid=%s OR (is_shared=TRUE AND module=%s)) "
                    "ORDER BY (owner_gid=%s) DESC, created_at ASC",
                    (user["gid"], module, user["gid"]),
                )
            else:
                # 全量（管理用）
                cur.execute(
                    "SELECT gid,name,module,list_gid,owner_gid,is_shared,config,created_at,updated_at "
                    "FROM workmanship_app_view_configs WHERE owner_gid=%s ORDER BY module,created_at",
                    (user["gid"],),
                )
            rows = cur.fetchall()
    return {"success": True, "data": [dict(r) for r in rows]}


@router.post("")
def create_view(body: CreateViewBody, user=Depends(_READ)):
    gid = next_gid()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_app_view_configs (gid,name,module,list_gid,owner_gid,is_shared,config) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (gid, body.name, body.module, body.list_gid, user["gid"],
                 body.is_shared, json.dumps(body.config)),
            )
    return {"success": True, "data": {
        "gid": gid, "name": body.name, "module": body.module,
        "list_gid": body.list_gid, "config": body.config,
    }}


@router.patch("/{gid}")
def update_view(gid: str, body: UpdateViewBody, user=Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT owner_gid FROM workmanship_app_view_configs WHERE gid=%s", (gid,)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "视图不存在")
            owner = row["owner_gid"]
            if owner != user["gid"] and user["role"] not in ("super_admin", "team_admin"):
                raise HTTPException(403, "无权修改此视图")

            updates, vals = [], []
            if body.name is not None:
                updates.append("name=%s"); vals.append(body.name)
            if body.config is not None:
                updates.append("config=%s"); vals.append(json.dumps(body.config))
            if body.is_shared is not None:
                updates.append("is_shared=%s"); vals.append(body.is_shared)
            if body.list_gid is not None:
                updates.append("list_gid=%s"); vals.append(body.list_gid)
            if not updates:
                return {"success": True}
            updates.append("updated_at=NOW()")
            vals.append(gid)
            cur.execute(f"UPDATE workmanship_app_view_configs SET {','.join(updates)} WHERE gid=%s", vals)
    return {"success": True}


@router.delete("/{gid}")
def delete_view(gid: str, user=Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT owner_gid FROM workmanship_app_view_configs WHERE gid=%s", (gid,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "视图不存在")
            owner = row["owner_gid"]
            if owner != user["gid"] and user["role"] not in ("super_admin", "team_admin"):
                raise HTTPException(403, "无权删除此视图")
            cur.execute("DELETE FROM workmanship_app_view_configs WHERE gid=%s", (gid,))
    return {"success": True}


@router.post("/{gid}/copy")
def copy_view(gid: str, user=Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name,module,list_gid,config FROM workmanship_app_view_configs WHERE gid=%s", (gid,)
            )
            src = cur.fetchone()
            if not src:
                raise HTTPException(404, "视图不存在")
            new_gid_val = next_gid()
            new_name = src["name"] + " - 副本"
            cur.execute(
                "INSERT INTO workmanship_app_view_configs (gid,name,module,list_gid,owner_gid,config) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (new_gid_val, new_name, src["module"], src["list_gid"],
                 user["gid"], json.dumps(src["config"])),
            )
    return {"success": True, "data": {"gid": new_gid_val, "name": new_name}}

# backend/routers/bitable_sync.py
"""
飞书多维表格同步 REST 端点。
前缀：/api/bitable-sync
自动被 backend/main.py 扫描注册。
"""
import json as _json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.db.connection import get_conn
from backend.routers.deps import get_current_user
from backend.services.bitable_sync_service import bitable_sync_service

_log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/bitable-sync", tags=["bitable-sync"])


# ── Pydantic 模型 ─────────────────────────────────────────────────────────────

class CreateBindingBody(BaseModel):
    app_token: str
    table_id: str
    field_mapping: dict = {}
    sync_enabled: bool = True
    webhook_secret: Optional[str] = None


class UpdateBindingBody(BaseModel):
    field_mapping: Optional[dict] = None
    sync_enabled: Optional[bool] = None
    webhook_secret: Optional[str] = None


class PushRowsBody(BaseModel):
    list_gid: str
    rows: list[dict]


class PushAllBody(BaseModel):
    rows: list[dict] = []


# ── 绑定 CRUD ─────────────────────────────────────────────────────────────────

@router.get("/bindings/{list_gid}")
def get_binding(list_gid: str, _: dict = Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM workmanship_work_list_bitable_bindings "
                "WHERE list_gid=%s AND is_deleted=FALSE",
                (list_gid,),
            )
            row = cur.fetchone()
    if not row:
        return {"success": True, "data": None}
    return {"success": True, "data": dict(row)}


@router.post("/bindings/{list_gid}")
def create_binding(
    list_gid: str,
    body: CreateBindingBody,
    current_user: dict = Depends(get_current_user),
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO workmanship_work_list_bitable_bindings
                    (list_gid, app_token, table_id, field_mapping,
                     sync_enabled, webhook_secret, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    app_token      = VALUES(app_token),
                    table_id       = VALUES(table_id),
                    field_mapping  = VALUES(field_mapping),
                    sync_enabled   = VALUES(sync_enabled),
                    webhook_secret = VALUES(webhook_secret),
                    is_deleted     = FALSE,
                    deleted_at     = NULL
            """, (
                list_gid, body.app_token, body.table_id,
                _json.dumps(body.field_mapping),
                body.sync_enabled, body.webhook_secret,
                current_user["gid"],
            ))
        conn.commit()
    return {"success": True}


@router.put("/bindings/{list_gid}")
def update_binding(
    list_gid: str,
    body: UpdateBindingBody,
    _: dict = Depends(get_current_user),
):
    """Update binding fields (explicit safe UPDATE per field, no f-string)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            if body.field_mapping is not None:
                cur.execute(
                    "UPDATE workmanship_work_list_bitable_bindings SET field_mapping = %s "
                    "WHERE list_gid=%s AND is_deleted=FALSE",
                    (_json.dumps(body.field_mapping), list_gid),
                )
            if body.sync_enabled is not None:
                cur.execute(
                    "UPDATE workmanship_work_list_bitable_bindings SET sync_enabled = %s "
                    "WHERE list_gid=%s AND is_deleted=FALSE",
                    (body.sync_enabled, list_gid),
                )
            if body.webhook_secret is not None:
                cur.execute(
                    "UPDATE workmanship_work_list_bitable_bindings SET webhook_secret = %s "
                    "WHERE list_gid=%s AND is_deleted=FALSE",
                    (body.webhook_secret, list_gid),
                )
        conn.commit()
    return {"success": True}


@router.delete("/bindings/{list_gid}")
def delete_binding(list_gid: str, _: dict = Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_work_list_bitable_bindings "
                "SET is_deleted=TRUE, deleted_at=NOW() WHERE list_gid=%s",
                (list_gid,),
            )
        conn.commit()
    return {"success": True}


# ── Schema + Status ───────────────────────────────────────────────────────────

@router.get("/bindings/{list_gid}/schema")
def get_schema(list_gid: str, _: dict = Depends(get_current_user)):
    """拉取飞书表字段列表（供前端字段映射器使用）。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT app_token, table_id FROM workmanship_work_list_bitable_bindings "
                "WHERE list_gid=%s AND is_deleted=FALSE",
                (list_gid,),
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(404, "binding not found")
    try:
        fields = bitable_sync_service.get_table_schema(row["app_token"], row["table_id"])
        return {"success": True, "data": fields}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/bindings/{list_gid}/schema-by-token")
def get_schema_by_token(
    list_gid: str,
    app_token: str,
    table_id: str,
    _: dict = Depends(get_current_user),
):
    """绑定前验证时用：直接传 app_token+table_id 拉 schema（无需已保存绑定）。"""
    try:
        fields = bitable_sync_service.get_table_schema(app_token, table_id)
        return {"success": True, "data": fields}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/bindings/{list_gid}/status")
def get_status(list_gid: str, _: dict = Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT has_remote_updates, last_push_at, last_pull_at, sync_enabled "
                "FROM workmanship_work_list_bitable_bindings "
                "WHERE list_gid=%s AND is_deleted=FALSE",
                (list_gid,),
            )
            row = cur.fetchone()
    if not row:
        return {"success": True, "data": {"bound": False}}
    return {
        "success": True,
        "data": {
            "bound": True,
            "has_remote_updates": row["has_remote_updates"],
            "last_push_at": str(row["last_push_at"]) if row["last_push_at"] else None,
            "last_pull_at": str(row["last_pull_at"]) if row["last_pull_at"] else None,
            "sync_enabled": row["sync_enabled"],
        },
    }


# ── 推送 / 拉取 ───────────────────────────────────────────────────────────────

@router.post("/bindings/{list_gid}/push")
def push_all(
    list_gid: str,
    body: PushAllBody,
    _: dict = Depends(get_current_user),
):
    """全量推送 AI00 → 飞书。调用方在 body.rows 中传入所有行。"""
    # Validate binding exists and sync enabled (I2)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM workmanship_work_list_bitable_bindings "
                "WHERE list_gid=%s AND is_deleted=FALSE AND sync_enabled=TRUE",
                (list_gid,),
            )
            if not cur.fetchone():
                return {"success": False, "error": "binding not found or sync disabled"}

    # Call service with error handling (I1)
    try:
        result = bitable_sync_service.push_all(list_gid, body.rows)
        return {"success": True, "data": result}
    except Exception as e:
        _log.error("push_all failed list_gid=%s: %s", list_gid, e)
        return {"success": False, "error": str(e)}


@router.post("/bindings/{list_gid}/pull")
def pull_all(list_gid: str, _: dict = Depends(get_current_user)):
    """触发从飞书全量拉取并标记 has_remote_updates，前端 load() 刷新后清除标志。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_work_list_bitable_bindings "
                "SET has_remote_updates=TRUE WHERE list_gid=%s AND is_deleted=FALSE",
                (list_gid,),
            )
        conn.commit()
    return {"success": True}


@router.post("/rows/push")
def push_rows(body: PushRowsBody, _: dict = Depends(get_current_user)):
    """增量推送（前端 onRowsChange 后调用）。"""
    try:
        result = bitable_sync_service.push_rows(body.list_gid, body.rows)
        return {"success": True, "data": result}
    except Exception as e:
        _log.error("push_rows failed list_gid=%s: %s", body.list_gid, e)
        return {"success": False, "error": str(e)}

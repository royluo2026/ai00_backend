"""Private per-user self annotations stored in Base-owned OceanBase tables."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from backend.db.connection import get_conn
from backend.routers.deps import get_current_user

router = APIRouter(prefix="/api/self_ann", tags=["self_annotations"])


class SelfAnnotationBody(BaseModel):
    module: str = Field(default="", max_length=128)
    item_title: str = Field(default="", max_length=512)
    self_status: str = Field(default="", max_length=64)
    self_schedule: str = Field(default="", max_length=128)
    self_note: str = Field(default="", max_length=20000)
    self_attachments: list = Field(default_factory=list, max_length=100)


def _decode(value) -> list:
    if isinstance(value, list):
        return value
    try:
        return json.loads(value or "[]")
    except (TypeError, ValueError):
        return []


def _empty(item_gid: str) -> dict:
    return {"item_gid": item_gid, "module": "", "item_title": "", "self_status": "", "self_schedule": "", "self_note": "", "self_attachments": [], "updated_at": ""}


def _row(row: dict) -> dict:
    result = dict(row)
    result["self_attachments"] = _decode(result.get("self_attachments"))
    if result.get("updated_at") is not None:
        result["updated_at"] = str(result["updated_at"])
    result.pop("user_gid", None)
    return result


@router.get("/batch")
def get_batch(gids: str = Query(""), user: dict = Depends(get_current_user)):
    gid_list = [value.strip() for value in gids.split(",") if value.strip()][:500]
    if not gid_list:
        return {}
    placeholders = ",".join(["%s"] * len(gid_list))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT item_gid,self_status,self_schedule,self_note,self_attachments "
                f"FROM workmanship_base_self_annotations WHERE item_gid IN ({placeholders}) AND user_gid=%s",
                [*gid_list, user["gid"]],
            )
            rows = cur.fetchall()
    return {
        row["item_gid"]: {
            "status": row.get("self_status") or "", "schedule": row.get("self_schedule") or "",
            "has_note": bool(row.get("self_note")), "attach_count": len(_decode(row.get("self_attachments"))),
        }
        for row in rows
    }


@router.get("/list")
def get_list(module: str = Query(""), user: dict = Depends(get_current_user)):
    sql = "SELECT * FROM workmanship_base_self_annotations WHERE user_gid=%s"
    params: list = [user["gid"]]
    if module:
        sql += " AND module=%s"; params.append(module)
    sql += " ORDER BY updated_at DESC LIMIT 1000"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return [_row(row) for row in cur.fetchall()]


@router.get("/{item_gid}")
def get_annotation(item_gid: str, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM workmanship_base_self_annotations WHERE item_gid=%s AND user_gid=%s", (item_gid, user["gid"]))
            row = cur.fetchone()
    return _row(row) if row else _empty(item_gid)


@router.put("/{item_gid}")
def upsert_annotation(item_gid: str, body: SelfAnnotationBody, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO workmanship_base_self_annotations
                   (item_gid,user_gid,module,item_title,self_status,self_schedule,self_note,self_attachments,updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                   ON DUPLICATE KEY UPDATE module=VALUES(module),item_title=VALUES(item_title),
                   self_status=VALUES(self_status),self_schedule=VALUES(self_schedule),
                   self_note=VALUES(self_note),self_attachments=VALUES(self_attachments),updated_at=NOW()""",
                (item_gid, user["gid"], body.module, body.item_title, body.self_status,
                 body.self_schedule, body.self_note, json.dumps(body.self_attachments, ensure_ascii=False)),
            )
        conn.commit()
    return {"success": True}


@router.delete("/{item_gid}")
def delete_annotation(item_gid: str, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_base_self_annotations WHERE item_gid=%s AND user_gid=%s", (item_gid, user["gid"]))
        conn.commit()
    return {"success": True}

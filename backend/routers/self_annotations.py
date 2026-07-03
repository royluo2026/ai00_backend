"""
backend/routers/self_annotations.py
─────────────────────────────────────
自我标注 CRUD — 数据存于本地 SQLite，不上传云端。

GET  /api/self_ann/batch       ?gids=g1,g2,...         → 批量摘要字典
GET  /api/self_ann/list        ?module=xxx             → 当前用户全部标注列表
GET  /api/self_ann/{item_gid}                          → 单条（无记录返回空结构）
PUT  /api/self_ann/{item_gid}                          → upsert
DEL  /api/self_ann/{item_gid}                          → 删除

SQLite 不可用时返回 HTTP 503，前端静默忽略。
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from backend.routers.deps import get_current_user_optional

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/self_ann", tags=["self_annotations"])

_DEP = Depends(get_current_user_optional)


class SelfAnnotationBody(BaseModel):
    module: str = ""
    item_title: str = ""
    self_status: str = ""
    self_schedule: str = ""
    self_note: str = ""
    self_attachments: list = []


def _get_db():
    try:
        from backend.db.local_sqlite import get_local_db
        return get_local_db()
    except Exception as e:
        _log.warning("local SQLite unavailable: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="本地 SQLite 不可用",
        )


def _user_gid(current_user: dict) -> str:
    return current_user.get("gid") or current_user.get("sub") or ""


def _empty_record(item_gid: str) -> dict:
    return {
        "item_gid": item_gid,
        "module": "",
        "item_title": "",
        "self_status": "",
        "self_schedule": "",
        "self_note": "",
        "self_attachments": [],
        "updated_at": "",
    }


def _row_to_dict(row) -> dict:
    try:
        attachments = json.loads(row["self_attachments"] or "[]")
    except Exception:
        attachments = []
    return {
        "item_gid":       row["item_gid"],
        "module":         row["module"]      or "",
        "item_title":     row["item_title"]  or "",
        "self_status":    row["self_status"] or "",
        "self_schedule":  row["self_schedule"] or "",
        "self_note":      row["self_note"]   or "",
        "self_attachments": attachments,
        "updated_at":     row["updated_at"]  or "",
    }


# ── GET /batch（必须在 /{item_gid} 前声明）──────────────────────────────────
@router.get("/batch")
def get_batch(gids: str = Query(""), current_user: dict = _DEP):
    if not gids:
        return {}
    gid_list = [g.strip() for g in gids.split(",") if g.strip()]
    if not gid_list:
        return {}
    db  = _get_db()
    uid = _user_gid(current_user)
    placeholders = ",".join("?" * len(gid_list))
    rows = db.execute(
        f"SELECT item_gid, self_status, self_schedule, self_note, self_attachments "
        f"FROM self_annotations "
        f"WHERE item_gid IN ({placeholders}) AND user_gid = ?",
        (*gid_list, uid),
    ).fetchall()
    result = {}
    for row in rows:
        try:
            attachments = json.loads(row["self_attachments"] or "[]")
        except Exception:
            attachments = []
        result[row["item_gid"]] = {
            "status":       row["self_status"]   or "",
            "schedule":     row["self_schedule"] or "",
            "has_note":     bool(row["self_note"]),
            "attach_count": len(attachments),
        }
    return result


# ── GET /list（必须在 /{item_gid} 前声明）────────────────────────────────────
@router.get("/list")
def get_list(module: str = Query(""), current_user: dict = _DEP):
    """返回当前用户的全部标注，按 updated_at 倒序。可选 ?module=xxx 过滤模块。"""
    db  = _get_db()
    uid = _user_gid(current_user)
    if module:
        rows = db.execute(
            "SELECT * FROM self_annotations "
            "WHERE user_gid = ? AND module = ? "
            "ORDER BY updated_at DESC",
            (uid, module),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM self_annotations "
            "WHERE user_gid = ? "
            "ORDER BY updated_at DESC",
            (uid,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


# ── GET /{item_gid} ────────────────────────────────────────────────────────
@router.get("/{item_gid}")
def get_annotation(item_gid: str, current_user: dict = _DEP):
    db  = _get_db()
    uid = _user_gid(current_user)
    row = db.execute(
        "SELECT * FROM self_annotations WHERE item_gid = ? AND user_gid = ?",
        (item_gid, uid),
    ).fetchone()
    return _row_to_dict(row) if row else _empty_record(item_gid)


# ── PUT /{item_gid} ────────────────────────────────────────────────────────
@router.put("/{item_gid}")
def upsert_annotation(
    item_gid: str,
    body: SelfAnnotationBody,
    current_user: dict = _DEP,
):
    db  = _get_db()
    uid = _user_gid(current_user)
    db.execute(
        """
        INSERT INTO self_annotations
            (item_gid, user_gid, module, item_title, self_status, self_schedule,
             self_note, self_attachments, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT (item_gid, user_gid) DO UPDATE SET
            module           = excluded.module,
            item_title       = excluded.item_title,
            self_status      = excluded.self_status,
            self_schedule    = excluded.self_schedule,
            self_note        = excluded.self_note,
            self_attachments = excluded.self_attachments,
            updated_at       = datetime('now')
        """,
        (
            item_gid, uid, body.module, body.item_title,
            body.self_status, body.self_schedule, body.self_note,
            json.dumps(body.self_attachments, ensure_ascii=False),
        ),
    )
    db.commit()
    return {"success": True}


# ── DELETE /{item_gid} ────────────────────────────────────────────────────
@router.delete("/{item_gid}")
def delete_annotation(item_gid: str, current_user: dict = _DEP):
    db  = _get_db()
    uid = _user_gid(current_user)
    db.execute(
        "DELETE FROM self_annotations WHERE item_gid = ? AND user_gid = ?",
        (item_gid, uid),
    )
    db.commit()
    return {"success": True}

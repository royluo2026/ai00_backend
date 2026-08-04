"""
backend/routers/canvases.py
────────────────────────────
WFC（工作流画布）存档管理 REST API

GET    /api/canvases          — 列出当前用户的画布（含共享）
POST   /api/canvases          — 创建或更新画布
GET    /api/canvases/{gid}    — 获取单个画布（含 data 字段）
DELETE /api/canvases/{gid}    — 删除画布
PATCH  /api/canvases/{gid}/shared — 切换共享状态
"""
from fastapi import APIRouter, Depends, Query
from ..data.connection import get_conn
from backend.platform_sdk.auth import get_current_user
from backend.platform_sdk.ids import next_gid

router = APIRouter(prefix="/api/canvases", tags=["canvases"])


@router.get("")
def list_canvases(
    _user: dict = Depends(get_current_user),
):
    user_gid = _user.get("gid", "")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT gid, owner_gid, title, is_shared, updated_at
                FROM workmanship_app_wfc_canvases
                WHERE owner_gid = %s OR is_shared = TRUE
                ORDER BY updated_at DESC
            """, (user_gid,))
            rows = cur.fetchall()
    return {
        "canvases": [
            {
                "gid":       r["gid"],
                "title":     r["title"],
                "is_shared": r["is_shared"],
                "owner_gid": r["owner_gid"],
                "updated_at": r["updated_at"].isoformat() if r["updated_at"] else "",
            }
            for r in rows
        ]
    }


@router.post("")
def save_canvas(
    body: dict,
    _user: dict = Depends(get_current_user),
):
    gid       = body.get("gid") or ""
    title     = body.get("title") or "未命名画布"
    data      = body.get("data") or {}
    is_shared = bool(body.get("is_shared", False))
    owner_gid = _user.get("gid", "")

    import json as _json
    data_json = _json.dumps(data) if not isinstance(data, str) else data

    with get_conn() as conn:
        with conn.cursor() as cur:
            if gid:
                cur.execute("SELECT gid FROM workmanship_app_wfc_canvases WHERE gid = %s", (gid,))
                existing = cur.fetchone()
                if existing:
                    cur.execute("""
                        UPDATE workmanship_app_wfc_canvases
                        SET title=%s, data=%s, is_shared=%s, updated_at=NOW()
                        WHERE gid=%s
                    """, (title, data_json, is_shared, gid))
                    cur.execute(
                        "SELECT gid, title, updated_at FROM workmanship_app_wfc_canvases WHERE gid = %s",
                        (gid,),
                    )
                    row = cur.fetchone()
                    return {"gid": row["gid"], "title": row["title"],
                            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else ""}
            new_gid = gid or str(next_gid())
            cur.execute("""
                INSERT INTO workmanship_app_wfc_canvases (gid, owner_gid, title, data, is_shared)
                VALUES (%s, %s, %s, %s, %s)
            """, (new_gid, owner_gid, title, data_json, is_shared))
            cur.execute(
                "SELECT gid, title, updated_at FROM workmanship_app_wfc_canvases WHERE gid = %s",
                (new_gid,),
            )
            row = cur.fetchone()
            return {"gid": row["gid"], "title": row["title"],
                    "updated_at": row["updated_at"].isoformat() if row["updated_at"] else ""}


@router.get("/{gid}")
def load_canvas(
    gid: str,
    _user: dict = Depends(get_current_user),
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT gid, owner_gid, title, data, is_shared, updated_at
                FROM workmanship_app_wfc_canvases WHERE gid = %s
            """, (gid,))
            row = cur.fetchone()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="画布不存在")
    return {
        "gid":       row["gid"],
        "title":     row["title"],
        "is_shared": row["is_shared"],
        "owner_gid": row["owner_gid"],
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else "",
        "data":      row["data"] or {},
    }


@router.delete("/{gid}")
def delete_canvas(
    gid: str,
    _user: dict = Depends(get_current_user),
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT gid FROM workmanship_app_wfc_canvases WHERE gid = %s", (gid,))
            row = cur.fetchone()
            if not row:
                from fastapi import HTTPException
                raise HTTPException(status_code=404, detail="画布不存在")
            cur.execute("DELETE FROM workmanship_app_wfc_canvases WHERE gid = %s", (gid,))
    return {"success": True}


@router.patch("/{gid}/shared")
def toggle_shared(
    gid: str,
    body: dict,
    _user: dict = Depends(get_current_user),
):
    is_shared = bool(body.get("is_shared", False))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE workmanship_app_wfc_canvases SET is_shared=%s, updated_at=NOW()
                WHERE gid=%s
            """, (is_shared, gid))
            cur.execute(
                "SELECT gid, is_shared FROM workmanship_app_wfc_canvases WHERE gid = %s",
                (gid,),
            )
            row = cur.fetchone()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="画布不存在")
    return {"gid": row["gid"], "is_shared": row["is_shared"]}

"""
backend/routers/knowledge_hub.py
──────────────────────────────────
知识库 Hub 云端 API（公共/团队知识库，需飞书登录）

prefix: /api/knowledge_hub
"""
import json
from typing import Optional, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from backend.db.connection import get_conn
from backend.routers.deps import get_current_user
from backend.utils.gid import next_gid

router = APIRouter(prefix="/api/knowledge_hub", tags=["knowledge_hub"])


# ── Pydantic Models ────────────────────────────────────────────────────────────

class FolderCreate(BaseModel):
    parent_gid: Optional[str] = None
    scope_type: str = 'public'   # public | team
    team_gid:   Optional[str] = None
    name:       str = '新建文件夹'
    sort_order: int = 0


class FolderPatch(BaseModel):
    name:       Optional[str] = None
    sort_order: Optional[int] = None
    parent_gid: Optional[str] = None


class ItemCreate(BaseModel):
    folder_gid:   Optional[str] = None
    scope_type:   str = 'public'
    team_gid:     Optional[str] = None
    item_type:    str = 'richtext'
    title:        str = '未命名文档'
    status:       str = 'draft'
    content_body: Optional[Any] = None
    content_md:   str = ''
    file_path:    str = ''
    url:          str = ''
    site_ref:     Optional[Any] = None
    tags:         list = []


class ItemPatch(BaseModel):
    folder_gid:          Optional[str]  = None
    title:               Optional[str]  = None
    status:              Optional[str]  = None
    scope_type:          Optional[str]  = None
    team_gid:            Optional[str]  = None
    content_body:        Optional[Any]  = None
    content_md:          Optional[str]  = None
    file_path:           Optional[str]  = None
    url:                 Optional[str]  = None
    site_ref:            Optional[Any]  = None
    tags:                Optional[list] = None
    is_pinned:           Optional[bool] = None
    is_hidden:           Optional[bool] = None


# ── 文件夹 ─────────────────────────────────────────────────────────────────────

@router.get("/folders")
def list_folders(
    scope_type: Optional[str] = Query(None),
    team_gid:   Optional[str] = Query(None),
    current_user = Depends(get_current_user),
):
    with get_conn() as conn:
        cur = conn.cursor()
        conditions = ["1=1"]
        params = []
        if scope_type:
            conditions.append("scope_type = %s")
            params.append(scope_type)
        if team_gid:
            conditions.append("team_gid = %s")
            params.append(team_gid)
        cur.execute(
            f"SELECT * FROM workmanship_know_folders WHERE {' AND '.join(conditions)} ORDER BY sort_order, created_at",
            params
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]


@router.post("/folders")
def create_folder(body: FolderCreate, current_user = Depends(get_current_user)):
    from backend.utils.gid import next_gid
    gid = str(next_gid())
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO workmanship_know_folders
               (gid, parent_gid, scope_type, team_gid, name, sort_order, creator_gid, created_at, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())""",
            (gid, body.parent_gid, body.scope_type, body.team_gid,
             body.name, body.sort_order, current_user["gid"])
        )
        conn.commit()
        cur.execute("SELECT * FROM workmanship_know_folders WHERE gid = %s", (gid,))
        row = cur.fetchone()
        return dict(row)


@router.patch("/folders/{gid}")
def patch_folder(gid: str, body: FolderPatch, current_user = Depends(get_current_user)):
    sets = []
    params = []
    if body.name is not None:
        sets.append("name = %s"); params.append(body.name)
    if body.sort_order is not None:
        sets.append("sort_order = %s"); params.append(body.sort_order)
    if body.parent_gid is not None:
        sets.append("parent_gid = %s"); params.append(body.parent_gid)
    if not sets:
        return {"success": True}
    sets.append("updated_at = NOW()")
    params.append(gid)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE workmanship_know_folders SET {', '.join(sets)} WHERE gid = %s", params)
        conn.commit()
    return {"success": True}


@router.delete("/folders/{gid}")
def delete_folder(gid: str, current_user = Depends(get_current_user)):
    with get_conn() as conn:
        cur = conn.cursor()
        # 递归删除子文件夹（PostgreSQL 不支持直接递归 DELETE，用 CTE）
        cur.execute("""
            WITH RECURSIVE sub AS (
              SELECT gid FROM workmanship_know_folders WHERE gid = %s
              UNION ALL
              SELECT f.gid FROM workmanship_know_folders f INNER JOIN sub s ON f.parent_gid = s.gid
            )
            DELETE FROM workmanship_know_items WHERE folder_gid IN (SELECT gid FROM sub)
        """, (gid,))
        cur.execute("""
            WITH RECURSIVE sub AS (
              SELECT gid FROM workmanship_know_folders WHERE gid = %s
              UNION ALL
              SELECT f.gid FROM workmanship_know_folders f INNER JOIN sub s ON f.parent_gid = s.gid
            )
            DELETE FROM workmanship_know_folders WHERE gid IN (SELECT gid FROM sub)
        """, (gid,))
        conn.commit()
    return {"success": True}


# ── 条目 ───────────────────────────────────────────────────────────────────────

@router.get("/items")
def list_items(
    folder_gid: Optional[str] = Query(None),
    scope_type: Optional[str] = Query(None),
    team_gid:   Optional[str] = Query(None),
    show_hidden: Optional[bool] = Query(False),
    q: Optional[str] = Query(None),
    current_user = Depends(get_current_user),
):
    with get_conn() as conn:
        cur = conn.cursor()
        conditions = ["1=1"]
        params = []
        if folder_gid:
            conditions.append("ki.folder_gid = %s"); params.append(folder_gid)
        if scope_type:
            conditions.append("ki.scope_type = %s"); params.append(scope_type)
        if team_gid:
            conditions.append("ki.team_gid = %s"); params.append(team_gid)
        if q:
            conditions.append("ki.title LIKE %s"); params.append(f"%{q}%")
        # personal 条目仅创建者可见
        uid = current_user["gid"]
        conditions.append("(ki.scope_type != 'personal' OR ki.creator_gid = %s)")
        params.append(uid)
        # 非超管不显示隐藏条目
        is_admin = current_user.get("system_role") == "super_admin" or current_user.get("role") == "super_admin"
        if not (show_hidden and is_admin):
            conditions.append("(ki.is_hidden = FALSE OR ki.is_hidden IS NULL)")
        cur.execute(
            f"SELECT ki.gid, ki.folder_gid, ki.scope_type, ki.team_gid, "
            f"ki.item_type, ki.title, ki.status, "
            f"ki.file_path, ki.url, ki.site_ref, ki.tags, ki.is_system, ki.is_pinned, ki.is_hidden, "
            f"ki.creator_gid, ki.created_at, ki.updated_at "
            f"FROM workmanship_know_items ki WHERE {' AND '.join(conditions)} "
            f"ORDER BY ki.is_pinned DESC , ki.is_system DESC, ki.updated_at DESC",
            params
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]


@router.get("/items/{gid}")
def get_item(gid: str, current_user = Depends(get_current_user)):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM workmanship_know_items WHERE gid = %s", (gid,))
        row = cur.fetchone()
        if not row:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="not_found")
        return dict(row)


@router.post("/items")
def create_item(body: ItemCreate, current_user = Depends(get_current_user)):
    from backend.utils.gid import next_gid
    gid = str(next_gid())
    content_body_str = json.dumps(body.content_body) if body.content_body is not None else None
    site_ref_str     = json.dumps(body.site_ref) if body.site_ref is not None else None
    tags_str         = json.dumps(body.tags or [])
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO workmanship_know_items
               (gid, folder_gid, scope_type, team_gid, item_type, title, status,
                content_body, content_md, file_path, url, site_ref, tags,
                creator_gid, created_at, updated_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())""",
            (gid, body.folder_gid, body.scope_type, body.team_gid,
             body.item_type, body.title, body.status,
             content_body_str, body.content_md, body.file_path,
             body.url, site_ref_str, tags_str, current_user["gid"])
        )
        conn.commit()
        cur.execute("SELECT * FROM workmanship_know_items WHERE gid = %s", (gid,))
        row = cur.fetchone()
        return dict(row)


@router.patch("/items/{gid}")
def patch_item(gid: str, body: ItemPatch, current_user = Depends(get_current_user)):
    sets = []
    params = []
    mapping = {
        "folder_gid": body.folder_gid,
        "title":      body.title,
        "status":     body.status,
        "content_md": body.content_md,
        "file_path":  body.file_path,
        "url":        body.url,
    }
    for col, val in mapping.items():
        if val is not None:
            sets.append(f"{col} = %s"); params.append(val)
    if body.content_body is not None:
        sets.append("content_body = %s"); params.append(json.dumps(body.content_body))
    if body.site_ref is not None:
        sets.append("site_ref = %s"); params.append(json.dumps(body.site_ref))
    if body.tags is not None:
        sets.append("tags = %s"); params.append(json.dumps(body.tags))
    if body.is_pinned is not None:
        sets.append("is_pinned = %s"); params.append(body.is_pinned)
    if body.is_hidden is not None:
        sets.append("is_hidden = %s"); params.append(body.is_hidden)
    if not sets:
        return {"success": True}
    sets.append("updated_at = NOW()")
    params.append(gid)

    # 记录变更字段描述
    _FIELD_LABELS = {
        "title": "标题", "status": "状态", "content_md": "内容",
        "folder_gid": "所在文件夹", "file_path": "文件路径",
        "url": "URL", "content_body": "正文", "site_ref": "站点引用",
        "tags": "标签", "is_pinned": "置顶", "is_hidden": "隐藏",
    }
    changed_fields = [_FIELD_LABELS.get(k, k) for k in
                      ([c.split(' = ')[0] for c in sets if ' = ' in c] or []) if k not in ('updated_at',)]

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE workmanship_know_items SET {', '.join(sets)} WHERE gid = %s", params)
        # 写入变更历史
        if changed_fields:
            h_gid = str(next_gid())
            h_id  = str(next_gid())
            author_name = current_user.get("display_name") or current_user.get("name") or current_user.get("gid", "")
            author_gid  = current_user.get("gid", "")
            content = "更新了：" + "、".join(changed_fields)
            cur.execute(
                """INSERT INTO workmanship_work_item_entries
                   (gid, id, item_type, item_gid, section, author, author_name, author_gid,
                    content, sort_order, read_by_human, resolved, created_at, updated_at)
                   VALUES (%s,%s,'knowledge_item',%s,'history','human',%s,%s,%s,
                           UNIX_TIMESTAMP(),TRUE,FALSE,NOW(),NOW())""",
                (h_gid, h_id, gid, author_name, author_gid, content)
            )
        conn.commit()
    return {"success": True}


@router.get("/items/{gid}/history")
def get_item_history(gid: str, current_user = Depends(get_current_user)):
    """返回某知识库条目的变更历史（section='history'），按时间降序（新在上）。"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT gid, id, section, author, author_name, author_gid, content, "
            "sort_order, created_at "
            "FROM workmanship_work_item_entries "
            "WHERE item_type='knowledge_item' AND item_gid=%s AND section='history' "
            "ORDER BY created_at DESC",
            (gid,)
        )
        rows = cur.fetchall()
    return {"success": True, "data": [
        {"gid": r["gid"], "id": r["id"], "author_name": r["author_name"],
         "content": r["content"], "created_at": str(r["created_at"])}
        for r in rows
    ]}


@router.delete("/items/{gid}")
def delete_item(gid: str, current_user = Depends(get_current_user)):
    with get_conn() as conn:
        cur = conn.cursor()
        # 系统内置条目只有 super_admin 可以删除
        cur.execute("SELECT is_system FROM workmanship_know_items WHERE gid = %s", (gid,))
        row = cur.fetchone()
        if not row:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="not_found")
        if row["is_system"] and current_user.get("system_role") != "super_admin":
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="系统内置条目仅超管可删除")
        cur.execute("DELETE FROM workmanship_know_favorites WHERE item_gid = %s", (gid,))
        cur.execute("DELETE FROM workmanship_know_recent WHERE item_gid = %s", (gid,))
        cur.execute("DELETE FROM workmanship_know_items WHERE gid = %s", (gid,))
        conn.commit()
    return {"success": True}


# ── 收藏 ───────────────────────────────────────────────────────────────────────

@router.post("/items/{gid}/favorite")
def toggle_favorite(gid: str, current_user = Depends(get_current_user)):
    user_gid = current_user["gid"]
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM workmanship_know_favorites WHERE user_gid = %s AND item_gid = %s",
            (user_gid, gid)
        )
        exists = cur.fetchone()
        if exists:
            cur.execute(
                "DELETE FROM workmanship_know_favorites WHERE user_gid = %s AND item_gid = %s",
                (user_gid, gid)
            )
            is_fav = False
        else:
            cur.execute(
                "INSERT INTO workmanship_know_favorites (user_gid, item_gid) VALUES (%s, %s)",
                (user_gid, gid)
            )
            is_fav = True
        conn.commit()
    return {"is_favorite": is_fav}


@router.get("/favorites")
def list_favorites(current_user = Depends(get_current_user)):
    user_gid = current_user["gid"]
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT ki.* FROM workmanship_know_items ki
               JOIN workmanship_know_favorites kf ON kf.item_gid = ki.gid
               WHERE kf.user_gid = %s ORDER BY kf.created_at DESC""",
            (user_gid,)
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]


# ── 最近访问 ───────────────────────────────────────────────────────────────────

@router.post("/items/{gid}/recent")
def record_recent(gid: str, current_user = Depends(get_current_user)):
    user_gid = current_user["gid"]
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO workmanship_know_recent (user_gid, item_gid, accessed_at)
               VALUES (%s, %s, NOW())
               ON DUPLICATE KEY UPDATE accessed_at = NOW()""",
            (user_gid, gid)
        )
        conn.commit()
    return {"success": True}


@router.get("/recent")
def list_recent(
    limit: int = Query(20, le=100),
    current_user = Depends(get_current_user),
):
    user_gid = current_user["gid"]
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT ki.* FROM workmanship_know_items ki
               JOIN workmanship_know_recent kr ON kr.item_gid = ki.gid
               WHERE kr.user_gid = %s ORDER BY kr.accessed_at DESC LIMIT %s""",
            (user_gid, limit)
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]

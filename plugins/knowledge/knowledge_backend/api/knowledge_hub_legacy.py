"""
Knowledge-owned compatibility routes for the historical knowledge-hub API.
──────────────────────────────────
知识库 Hub 云端 API（公共/团队知识库，需飞书登录）

prefix: /api/knowledge_hub
"""
import json
from typing import Optional, Any

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel

from ..data.connection import get_knowledge_conn as get_conn
from backend.platform_sdk.auth import build_profile, get_current_user
from backend.platform_sdk.ids import next_gid

router = APIRouter(prefix="/api/knowledge_hub", tags=["knowledge_hub"])


def _append_item_history(item_gid: str, author_name: str, author_gid: str, content: str) -> dict:
    gid, entry_id = str(next_gid()), str(next_gid())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_know_item_history "
                "(gid,id,item_gid,author_name,author_gid,content) VALUES (%s,%s,%s,%s,%s,%s)",
                (gid, entry_id, item_gid, author_name, author_gid, content),
            )
        conn.commit()
    return {"gid": gid, "id": entry_id}


def _list_item_history(item_gid: str) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid,id,author_name,content,created_at FROM workmanship_know_item_history "
                "WHERE item_gid=%s ORDER BY created_at DESC", (item_gid,),
            )
            return [dict(row) for row in cur.fetchall()]

def _permissions(user: dict) -> set[str]:
    return set(build_profile(user).get("permissions", []))


def _current_team(user: dict) -> str:
    return str(user.get("team_id") or "")


def _normalize_scope(scope_type: str, requested_team: str | None, user: dict) -> tuple[str, str | None]:
    scope = str(scope_type or "personal")
    if scope not in {"personal", "team", "public"}:
        raise HTTPException(status_code=400, detail="invalid knowledge scope")
    if scope == "team":
        team = _current_team(user)
        if not team or (requested_team and requested_team != team):
            raise HTTPException(status_code=403, detail="cannot access another team knowledge scope")
        return scope, team
    return scope, None


def _assert_mutable(row: dict, user: dict) -> None:
    scope = str(row.get("scope_type") or "personal")
    uid = str(user.get("gid") or "")
    if scope == "personal" and str(row.get("creator_gid") or "") == uid:
        return
    if scope == "team" and str(row.get("team_gid") or "") == _current_team(user):
        if str(row.get("creator_gid") or "") == uid or "knowledge.manage" in _permissions(user):
            return
    if scope == "public" and "knowledge.manage" in _permissions(user):
        return
    raise HTTPException(status_code=403, detail="knowledge item is not writable by current user")


def _visible_predicate(alias: str, user: dict) -> tuple[str, list[str]]:
    return (
        f"({alias}.scope_type='public' OR ({alias}.scope_type='personal' AND {alias}.creator_gid=%s) "
        f"OR ({alias}.scope_type='team' AND {alias}.team_gid=%s AND {alias}.team_gid<>''))",
        [str(user.get("gid") or ""), _current_team(user)],
    )


# ── Pydantic Models ────────────────────────────────────────────────────────────
def _field_was_set(model: BaseModel, name: str) -> bool:
    fields = getattr(model, "model_fields_set", getattr(model, "__fields_set__", set()))
    return name in fields

class FolderCreate(BaseModel):
    parent_gid: Optional[str] = None
    scope_type: str = 'personal'   # personal | public | team
    team_gid:   Optional[str] = None
    name:       str = '新建文件夹'
    sort_order: int = 0


class FolderPatch(BaseModel):
    name:       Optional[str] = None
    sort_order: Optional[int] = None
    parent_gid: Optional[str] = None


class ItemCreate(BaseModel):
    folder_gid:   Optional[str] = None
    scope_type:   str = 'personal'
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
    team_gid: Optional[str] = Query(None),
    current_user=Depends(get_current_user),
):
    with get_conn() as conn:
        cur = conn.cursor()
        visible, params = _visible_predicate("f", current_user)
        conditions = [visible]
        if scope_type:
            normalized_scope, normalized_team = _normalize_scope(scope_type, team_gid, current_user)
            conditions.append("f.scope_type=%s")
            params.append(normalized_scope)
            if normalized_scope == "team":
                conditions.append("f.team_gid=%s")
                params.append(normalized_team or "")
        cur.execute(
            f"SELECT * FROM workmanship_know_folders f WHERE {' AND '.join(conditions)} "
            "ORDER BY sort_order,created_at",
            params,
        )
        return [dict(row) for row in cur.fetchall()]

@router.post("/folders")
def create_folder(body: FolderCreate, current_user=Depends(get_current_user)):
    scope, team_gid = _normalize_scope(body.scope_type, body.team_gid, current_user)
    if scope == "public" and "knowledge.manage" not in _permissions(current_user):
        raise HTTPException(status_code=403, detail="public knowledge requires knowledge.manage")
    gid = str(next_gid())
    with get_conn() as conn:
        cur = conn.cursor()
        if body.parent_gid:
            cur.execute("SELECT * FROM workmanship_know_folders WHERE gid=%s", (body.parent_gid,))
            parent = cur.fetchone()
            if not parent:
                raise HTTPException(status_code=404, detail="parent folder not found")
            _assert_mutable(dict(parent), current_user)
            if parent["scope_type"] != scope or str(parent.get("team_gid") or "") != str(team_gid or ""):
                raise HTTPException(status_code=400, detail="parent folder scope mismatch")
        cur.execute(
            "INSERT INTO workmanship_know_folders "
            "(gid,parent_gid,scope_type,team_gid,name,sort_order,creator_gid,created_at,updated_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())",
            (gid, body.parent_gid, scope, team_gid, body.name, body.sort_order, current_user["gid"]),
        )
        conn.commit()
        cur.execute("SELECT * FROM workmanship_know_folders WHERE gid=%s", (gid,))
        return dict(cur.fetchone())

@router.patch("/folders/{gid}")
def patch_folder(gid: str, body: FolderPatch, current_user = Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM workmanship_know_folders WHERE gid=%s", (gid,))
            existing = cur.fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="folder not found")
    _assert_mutable(dict(existing), current_user)
    if _field_was_set(body, "parent_gid") and body.parent_gid is not None:
        if body.parent_gid == gid:
            raise HTTPException(status_code=400, detail="folder cannot be its own parent")
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM workmanship_know_folders WHERE gid=%s", (body.parent_gid,))
                parent = cur.fetchone()
        if not parent:
            raise HTTPException(status_code=404, detail="parent folder not found")
        _assert_mutable(dict(parent), current_user)
        if parent["scope_type"] != existing["scope_type"] or str(parent.get("team_gid") or "") != str(existing.get("team_gid") or ""):
            raise HTTPException(status_code=400, detail="parent folder scope mismatch")
    sets = []
    params = []
    if body.name is not None:
        sets.append("name = %s"); params.append(body.name)
    if body.sort_order is not None:
        sets.append("sort_order = %s"); params.append(body.sort_order)
    if _field_was_set(body, "parent_gid"):
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
def delete_folder(gid: str, current_user=Depends(get_current_user)):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM workmanship_know_folders WHERE gid=%s", (gid,))
        root = cur.fetchone()
        if not root:
            raise HTTPException(status_code=404, detail="folder not found")
        _assert_mutable(dict(root), current_user)
        folder_gids = [gid]
        frontier = [gid]
        while frontier:
            placeholders = ",".join(["%s"] * len(frontier))
            cur.execute(
                f"SELECT * FROM workmanship_know_folders WHERE parent_gid IN ({placeholders})",
                frontier,
            )
            children = [dict(row) for row in cur.fetchall()]
            for child in children:
                _assert_mutable(child, current_user)
            frontier = [str(child["gid"]) for child in children if str(child["gid"]) not in folder_gids]
            folder_gids.extend(frontier)
        placeholders = ",".join(["%s"] * len(folder_gids))
        cur.execute(
            f"SELECT * FROM workmanship_know_items WHERE folder_gid IN ({placeholders})",
            folder_gids,
        )
        for item in cur.fetchall():
            _assert_mutable(dict(item), current_user)
        cur.execute(
            f"DELETE FROM workmanship_know_items WHERE folder_gid IN ({placeholders})",
            folder_gids,
        )
        cur.execute(
            f"DELETE FROM workmanship_know_folders WHERE gid IN ({placeholders})",
            folder_gids,
        )
        conn.commit()
    return {"success": True, "deleted_folders": len(folder_gids)}

# ── 条目 ───────────────────────────────────────────────────────────────────────

@router.get("/items")
def list_items(
    folder_gid: Optional[str] = Query(None),
    scope_type: Optional[str] = Query(None),
    team_gid: Optional[str] = Query(None),
    show_hidden: Optional[bool] = Query(False),
    q: Optional[str] = Query(None),
    current_user=Depends(get_current_user),
):
    with get_conn() as conn:
        cur = conn.cursor()
        visible, params = _visible_predicate("ki", current_user)
        conditions = [visible]
        if folder_gid:
            conditions.append("ki.folder_gid=%s")
            params.append(folder_gid)
        if scope_type:
            normalized_scope, normalized_team = _normalize_scope(scope_type, team_gid, current_user)
            conditions.append("ki.scope_type=%s")
            params.append(normalized_scope)
            if normalized_scope == "team":
                conditions.append("ki.team_gid=%s")
                params.append(normalized_team or "")
        if q:
            conditions.append("ki.title LIKE %s")
            params.append(f"%{q}%")
        is_admin = "knowledge.manage" in _permissions(current_user)
        if not (show_hidden and is_admin):
            conditions.append("(ki.is_hidden=FALSE OR ki.is_hidden IS NULL)")
        cur.execute(
            "SELECT ki.gid,ki.folder_gid,ki.scope_type,ki.team_gid,ki.item_type,ki.title,ki.status,"
            "ki.file_path,ki.url,ki.site_ref,ki.tags,ki.is_system,ki.is_pinned,ki.is_hidden,"
            "ki.creator_gid,ki.created_at,ki.updated_at FROM workmanship_know_items ki WHERE "
            + " AND ".join(conditions)
            + " ORDER BY ki.is_pinned DESC,ki.is_system DESC,ki.updated_at DESC",
            params,
        )
        return [dict(row) for row in cur.fetchall()]

@router.get("/items/{gid}")
def get_item(gid: str, current_user=Depends(get_current_user)):
    visible, params = _visible_predicate("ki", current_user)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT * FROM workmanship_know_items ki WHERE ki.gid=%s AND {visible}",
            [gid, *params],
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="not_found")
    return dict(row)

@router.post("/items")
def create_item(body: ItemCreate, current_user=Depends(get_current_user)):
    scope, team_gid = _normalize_scope(body.scope_type, body.team_gid, current_user)
    if scope == "public" and "knowledge.manage" not in _permissions(current_user):
        raise HTTPException(status_code=403, detail="public knowledge requires knowledge.manage")
    gid = str(next_gid())
    content_body_str = json.dumps(body.content_body) if body.content_body is not None else None
    site_ref_str = json.dumps(body.site_ref) if body.site_ref is not None else None
    tags_str = json.dumps(body.tags or [])
    with get_conn() as conn:
        cur = conn.cursor()
        if body.folder_gid:
            cur.execute("SELECT * FROM workmanship_know_folders WHERE gid=%s", (body.folder_gid,))
            folder = cur.fetchone()
            if not folder:
                raise HTTPException(status_code=404, detail="folder not found")
            _assert_mutable(dict(folder), current_user)
            if folder["scope_type"] != scope or str(folder.get("team_gid") or "") != str(team_gid or ""):
                raise HTTPException(status_code=400, detail="folder scope mismatch")
        cur.execute(
            "INSERT INTO workmanship_know_items "
            "(gid,folder_gid,scope_type,team_gid,item_type,title,status,content_body,content_md,file_path,url,site_ref,tags,creator_gid,created_at,updated_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())",
            (gid, body.folder_gid, scope, team_gid, body.item_type, body.title, body.status,
             content_body_str, body.content_md, body.file_path, body.url, site_ref_str,
             tags_str, current_user["gid"]),
        )
        conn.commit()
        cur.execute("SELECT * FROM workmanship_know_items WHERE gid=%s", (gid,))
        return dict(cur.fetchone())

@router.patch("/items/{gid}")
def patch_item(gid: str, body: ItemPatch, current_user = Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM workmanship_know_items WHERE gid=%s", (gid,))
            existing = cur.fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="not_found")
    _assert_mutable(dict(existing), current_user)
    if _field_was_set(body, "scope_type") or _field_was_set(body, "team_gid"):
        raise HTTPException(status_code=400, detail="knowledge item scope is immutable; copy into the target scope instead")
    if _field_was_set(body, "folder_gid") and body.folder_gid is not None:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM workmanship_know_folders WHERE gid=%s", (body.folder_gid,))
                folder = cur.fetchone()
        if not folder:
            raise HTTPException(status_code=404, detail="folder not found")
        _assert_mutable(dict(folder), current_user)
        if folder["scope_type"] != existing["scope_type"] or str(folder.get("team_gid") or "") != str(existing.get("team_gid") or ""):
            raise HTTPException(status_code=400, detail="folder scope mismatch")
    sets = []
    params = []
    if _field_was_set(body, "folder_gid"):
        sets.append("folder_gid = %s")
        params.append(body.folder_gid)
    mapping = {
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
        conn.commit()
    if changed_fields:
        author_name = current_user.get("display_name") or current_user.get("name") or current_user.get("gid", "")
        author_gid = current_user.get("gid", "")
        _append_item_history(gid, author_name, author_gid, "更新了：" + "、".join(changed_fields))
    return {"success": True}


@router.get("/items/{gid}/history")
def get_item_history(gid: str, current_user = Depends(get_current_user)):
    """返回某知识库条目的变更历史（section='history'），按时间降序（新在上）。"""
    visible, params = _visible_predicate("ki", current_user)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT 1 FROM workmanship_know_items ki WHERE ki.gid=%s AND {visible}",
                [gid, *params],
            )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="not_found")
    rows = _list_item_history(gid)

    return {"success": True, "data": [
        {"gid": r["gid"], "id": r["id"], "author_name": r["author_name"],
         "content": r["content"], "created_at": str(r["created_at"])}
        for r in rows
    ]}


@router.delete("/items/{gid}")
def delete_item(gid: str, current_user = Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM workmanship_know_items WHERE gid=%s", (gid,))
            existing = cur.fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="not_found")
    _assert_mutable(dict(existing), current_user)
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
def toggle_favorite(gid: str, current_user=Depends(get_current_user)):
    user_gid = current_user["gid"]
    visible, visible_params = _visible_predicate("ki", current_user)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT 1 FROM workmanship_know_items ki WHERE ki.gid=%s AND {visible}", [gid, *visible_params])
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="not_found")
        cur.execute("SELECT 1 FROM workmanship_know_favorites WHERE user_gid=%s AND item_gid=%s", (user_gid, gid))
        if cur.fetchone():
            cur.execute("DELETE FROM workmanship_know_favorites WHERE user_gid=%s AND item_gid=%s", (user_gid, gid))
            is_fav = False
        else:
            cur.execute("INSERT INTO workmanship_know_favorites (user_gid,item_gid) VALUES (%s,%s)", (user_gid, gid))
            is_fav = True
        conn.commit()
    return {"is_favorite": is_fav}


@router.get("/favorites")
def list_favorites(current_user=Depends(get_current_user)):
    user_gid = current_user["gid"]
    visible, params = _visible_predicate("ki", current_user)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT ki.* FROM workmanship_know_items ki JOIN workmanship_know_favorites kf ON kf.item_gid=ki.gid "
            f"WHERE kf.user_gid=%s AND {visible} ORDER BY kf.created_at DESC",
            [user_gid, *params],
        )
        return [dict(row) for row in cur.fetchall()]

# ── 最近访问 ───────────────────────────────────────────────────────────────────

@router.post("/items/{gid}/recent")
def record_recent(gid: str, current_user=Depends(get_current_user)):
    user_gid = current_user["gid"]
    visible, params = _visible_predicate("ki", current_user)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT 1 FROM workmanship_know_items ki WHERE ki.gid=%s AND {visible}", [gid, *params])
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="not_found")
        cur.execute(
            "INSERT INTO workmanship_know_recent (user_gid,item_gid,accessed_at) VALUES (%s,%s,NOW()) "
            "ON DUPLICATE KEY UPDATE accessed_at=NOW()",
            (user_gid, gid),
        )
        conn.commit()
    return {"success": True}

@router.get("/recent")
def list_recent(limit: int = Query(20, le=100), current_user=Depends(get_current_user)):
    user_gid = current_user["gid"]
    visible, params = _visible_predicate("ki", current_user)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT ki.* FROM workmanship_know_items ki JOIN workmanship_know_recent kr ON kr.item_gid=ki.gid "
            f"WHERE kr.user_gid=%s AND {visible} ORDER BY kr.accessed_at DESC LIMIT %s",
            [user_gid, *params, limit],
        )
        return [dict(row) for row in cur.fetchall()]

"""
Knowledge-owned compatibility routes for historical entry APIs.
─────────────────────────────
知识条目 CRUD API（云端 PG）

端点：
  GET    /api/knowledge_entries          → 列表
  POST   /api/knowledge_entries          → 创建
  GET    /api/knowledge_entries/{gid}    → 获取单条
  PATCH  /api/knowledge_entries/{gid}    → 更新
  DELETE /api/knowledge_entries/{gid}    → 删除
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..data.connection import get_knowledge_conn as get_conn
from backend.routers.deps import build_profile, get_current_user
from backend.platform_sdk.identity import get_active_team_member_gids
from backend.utils.gid import next_gid

router = APIRouter(tags=["knowledge"])


def next_display_id(seq_name: str) -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_know_display_counters (seq_name,val) VALUES (%s,1) "
                "ON DUPLICATE KEY UPDATE val=LAST_INSERT_ID(val+1)", (seq_name,),
            )
            cur.execute("SELECT val FROM workmanship_know_display_counters WHERE seq_name=%s", (seq_name,))
            value = int(cur.fetchone()["val"])
        conn.commit()
    return value


def _permissions(user: dict) -> set[str]:
    return set(build_profile(user).get("permissions", []))


def _visible_sql(user: dict, alias: str = "") -> tuple[str, list]:
    if "knowledge.view" not in _permissions(user) and "knowledge.manage" not in _permissions(user):
        raise HTTPException(status_code=403, detail="缺少知识查看权限")
    prefix = f"{alias}." if alias else ""
    if (user.get("org_role") or user.get("system_role")) == "super_admin":
        return "1=1", []
    uid = str(user.get("gid") or "")
    members = get_active_team_member_gids(str(user.get("team_id") or ""))
    clauses = [f"{prefix}share_scope='global'", f"{prefix}creator_gid=%s"]
    params: list = [uid]
    if members:
        placeholders = ",".join(["%s"] * len(members))
        clauses.append(f"({prefix}share_scope='team' AND {prefix}creator_gid IN ({placeholders}))")
        params.extend(members)
    return "(" + " OR ".join(clauses) + ")", params


def _assert_writable(row: dict, user: dict) -> None:
    if str(row.get("creator_gid") or "") == str(user.get("gid") or ""):
        return
    if str(row.get("share_scope") or "team") in {"team", "global"} and "knowledge.manage" in _permissions(user):
        return
    raise HTTPException(status_code=403, detail="无权修改该知识条目")


class KnowledgeBody(BaseModel):
    title: str
    entry_type: str = "guide"
    status: str = "draft"
    share_scope: str = "team"
    list_gid: Optional[str] = None
    source_gid: Optional[str] = None
    source_label: str = ""
    maintainer_gid: str = ""
    contributors: list = []
    attachments: list = []
    tags: list = []
    content_ref: dict = {}
    related_part_nos: list = []
    related_operation_gids: list = []


def _row_to_dict(r: dict) -> dict:
    return {
        "gid":                    r["gid"],
        "display_id":             r.get("display_id") or "",
        "title":                  r["title"],
        "entry_type":             r["entry_type"],
        "status":                 r["status"],
        "share_scope":            r["share_scope"],
        "list_gid":               r.get("list_gid"),
        "source_gid":             r.get("source_gid"),
        "source_label":           r.get("source_label") or "",
        "maintainer_gid":         r.get("maintainer_gid") or "",
        "contributors":           r.get("contributors") or [],
        "attachments":            r.get("attachments") or [],
        "tags":                   r.get("tags") or [],
        "content_ref":            r.get("content_ref") or {},
        "related_part_nos":       r.get("related_part_nos") or [],
        "related_operation_gids": r.get("related_operation_gids") or [],
        "creator_gid":            r.get("creator_gid") or "",
        "source_project_gid":     r.get("source_project_gid"),
        "created_at":             str(r["created_at"]),
        "updated_at":             str(r["updated_at"]),
    }


@router.get("/api/knowledge_entries")
def list_knowledge_entries(
    entry_type: Optional[str] = Query(None),
    list_gid: Optional[str] = Query(None),
    context_class_gid: Optional[str] = Query(None),
    limit: int = Query(200, le=500),
    current_user: dict = Depends(get_current_user),
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            visible, params = _visible_sql(current_user)
            clauses = [visible]
            if entry_type:
                clauses.append("entry_type = %s"); params.append(entry_type)
            if list_gid:
                clauses.append("list_gid = %s"); params.append(list_gid)
            if context_class_gid:
                clauses.append("context_class_gid = %s"); params.append(context_class_gid)
            where = " AND ".join(clauses)
            cur.execute(
                f"SELECT * FROM workmanship_know_entries WHERE {where} ORDER BY created_at DESC LIMIT %s",
                params + [limit],
            )
            rows = cur.fetchall()
    return {"success": True, "data": [_row_to_dict(dict(r)) for r in rows]}


@router.post("/api/knowledge_entries", status_code=201)
def create_knowledge_entry(body: KnowledgeBody, current_user: dict = Depends(get_current_user)):
    if "knowledge.view" not in _permissions(current_user) and "knowledge.manage" not in _permissions(current_user):
        raise HTTPException(status_code=403, detail="缺少知识创建权限")
    if body.share_scope not in {"local", "team", "global"}:
        raise HTTPException(status_code=400, detail="不支持的知识可见范围")
    if body.share_scope == "global" and "knowledge.manage" not in _permissions(current_user):
        raise HTTPException(status_code=403, detail="公开知识需要knowledge.manage权限")
    gid = str(next_gid())
    display_id = f"K-C{next_display_id('knowledge_display_seq'):08d}"
    uid = current_user["gid"]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO workmanship_know_entries (
                    gid, display_id, title, entry_type, status, share_scope, list_gid,
                    source_gid, source_label, maintainer_gid, contributors, attachments,
                    tags, content_ref, content_md, related_part_nos, related_operation_gids, creator_gid
                ) VALUES (
                    %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    gid, display_id, body.title, body.entry_type, body.status, body.share_scope, body.list_gid,
                    body.source_gid, body.source_label, body.maintainer_gid,
                    json.dumps(body.contributors), json.dumps(body.attachments),
                    json.dumps(body.tags), json.dumps(body.content_ref), '',
                    json.dumps(body.related_part_nos), json.dumps(body.related_operation_gids), uid,
                ),
            )
        conn.commit()
    return {"success": True, "data": {"gid": gid}}


@router.get("/api/knowledge_entries/{gid}")
def get_knowledge_entry(gid: str, current_user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            visible, params = _visible_sql(current_user, "k")
            cur.execute(f"SELECT * FROM workmanship_know_entries k WHERE k.gid = %s AND {visible}", [gid, *params])
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    return {"success": True, "data": _row_to_dict(dict(row))}


@router.patch("/api/knowledge_entries/{gid}")
def update_knowledge_entry(gid: str, body: dict, current_user: dict = Depends(get_current_user)):
    visible, visibility_params = _visible_sql(current_user, "k")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM workmanship_know_entries k WHERE k.gid=%s AND {visible}", [gid, *visibility_params])
            existing = cur.fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    _assert_writable(dict(existing), current_user)
    if "share_scope" in body:
        if body["share_scope"] not in {"local", "team", "global"}:
            raise HTTPException(status_code=400, detail="不支持的知识可见范围")
        if body["share_scope"] == "global" and "knowledge.manage" not in _permissions(current_user):
            raise HTTPException(status_code=403, detail="公开知识需要knowledge.manage权限")
    allowed = {
        "title", "entry_type", "status", "share_scope", "list_gid",
        "source_gid", "source_label", "maintainer_gid", "contributors",
        "attachments", "tags", "content_ref", "related_part_nos",
        "related_operation_gids", "context_class_gid",
    }
    json_fields = {"contributors", "attachments", "tags", "content_ref", "related_part_nos", "related_operation_gids"}
    updates = {}
    for k, v in body.items():
        if k in allowed:
            updates[k] = json.dumps(v) if k in json_fields else v
    if not updates:
        raise HTTPException(status_code=400, detail="没有可更新的字段")
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    set_clause += ", updated_at = NOW()"
    params = list(updates.values()) + [gid]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE workmanship_know_entries SET {set_clause} WHERE gid = %s", params)
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="知识条目不存在")
        conn.commit()
    return {"success": True}


@router.delete("/api/knowledge_entries/{gid}")
def delete_knowledge_entry(gid: str, current_user: dict = Depends(get_current_user)):
    visible, params = _visible_sql(current_user, "k")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM workmanship_know_entries k WHERE k.gid=%s AND {visible}", [gid, *params])
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="知识条目不存在")
            _assert_writable(dict(row), current_user)
            cur.execute("DELETE FROM workmanship_know_entries WHERE gid=%s", (gid,))
        conn.commit()
    return {"success": True}

class VectorSearchBody(BaseModel):
    query_vector: list
    top_k: int = 10
    min_similarity: float = 0.0   # cosine distance < (1 - min_similarity)


@router.post("/api/knowledge_entries/vector-search")
def vector_search_knowledge(
    body: VectorSearchBody,
    current_user: dict = Depends(get_current_user),
):
    """Fail closed until an OceanBase-compatible vector index adapter is configured."""
    if not body.query_vector:
        raise HTTPException(status_code=400, detail="query_vector 不能为空")
    raise HTTPException(
        status_code=501,
        detail=(
            "当前 OceanBase 部署未配置向量检索适配器；"
            "已禁用遗留 pgvector SQL，避免在生产库执行不兼容语句"
        ),
    )

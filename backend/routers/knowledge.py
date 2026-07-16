"""
backend/routers/knowledge.py
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

from backend.db.connection import get_conn
from backend.db.sequences import next_display_id
from backend.routers.deps import get_current_user, get_current_user_optional
from backend.utils.gid import next_gid

router = APIRouter(tags=["knowledge"])


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
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            clauses, params = ["1=1"], []
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
def get_knowledge_entry(gid: str, current_user: Optional[dict] = Depends(get_current_user_optional)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM workmanship_know_entries WHERE gid = %s", (gid,))
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    return {"success": True, "data": _row_to_dict(dict(row))}


@router.patch("/api/knowledge_entries/{gid}")
def update_knowledge_entry(gid: str, body: dict, current_user: dict = Depends(get_current_user)):
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
    uid = current_user["gid"]
    with get_conn() as conn:
        with conn.cursor() as cur:
            # 允许创建者或管理员删除
            cur.execute(
                "DELETE FROM workmanship_know_entries WHERE gid = %s AND (creator_gid = %s OR %s IN (SELECT gid FROM workmanship_auth_users WHERE system_role IN ('super_admin','team_admin','knowledge_admin')))",
                (gid, uid, uid),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="知识条目不存在或无权限")
        conn.commit()
    return {"success": True}


class VectorSearchBody(BaseModel):
    query_vector: list
    top_k: int = 10
    min_similarity: float = 0.0   # cosine distance < (1 - min_similarity)


@router.post("/api/knowledge_entries/vector-search")
def vector_search_knowledge(
    body: VectorSearchBody,
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    """
    pgvector 语义相似搜索。
    需先执行 backend/db/schema.sql 中的 pgvector 建索引语句，
    并通过 PATCH /api/knowledge_entries/{gid} 写入 embedding 字段。
    """
    if not body.query_vector:
        raise HTTPException(status_code=400, detail="query_vector 不能为空")
    vec_str = "[" + ",".join(str(float(v)) for v in body.query_vector) + "]"
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT gid, title, entry_type, tags, content_ref,
                           (embedding <=> %s::vector) AS distance
                    FROM workmanship_know_entries
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (vec_str, vec_str, body.top_k),
                )
                rows = cur.fetchall()
        results = [
            {
                "gid":        r["gid"],
                "title":      r["title"],
                "entry_type": r["entry_type"],
                "tags":       r["tags"] or [],
                "distance":   round(float(r["distance"]), 4),
            }
            for r in rows
        ]
        return {"success": True, "data": results, "total": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

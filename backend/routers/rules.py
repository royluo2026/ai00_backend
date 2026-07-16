"""
backend/routers/rules.py
─────────────────────────
规则 CRUD API（云端 PG）

端点：
  GET    /api/rules          → 列表
  POST   /api/rules          → 创建
  GET    /api/rules/{gid}    → 获取单条
  PATCH  /api/rules/{gid}    → 更新
  DELETE /api/rules/{gid}    → 删除
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.db.connection import get_conn
from backend.db.sequences import next_display_id
from backend.routers.deps import get_current_user, get_current_user_optional
from backend.utils.gid import next_gid

router = APIRouter(tags=["rules"])


class RuleBody(BaseModel):
    code: str = ""
    name: str
    rule_type: str = "process"
    enforcement_level: str = "advisory"
    status: str = "draft"
    share_scope: str = "team"
    list_gid: Optional[str] = None
    context_class_gid: Optional[str] = None
    rule_definition: dict = {}


def _row_to_dict(r: dict) -> dict:
    return {
        "gid":               r["gid"],
        "display_id":        r.get("display_id") or "",
        "code":              r.get("code") or "",
        "name":              r["name"],
        "rule_type":         r.get("rule_type") or "process",
        "enforcement_level": r.get("enforcement_level") or "advisory",
        "status":            r.get("status") or "draft",
        "share_scope":       r.get("share_scope") or "team",
        "list_gid":          r.get("list_gid"),
        "context_class_gid": r.get("context_class_gid"),
        "rule_definition":   r.get("rule_definition") or {},
        "deviation_count":   r.get("deviation_count") or 0,
        "created_at":        str(r["created_at"]),
        "updated_at":        str(r["updated_at"]),
    }


@router.get("/api/rules")
def list_rules(
    status: Optional[str] = Query(None),
    list_gid: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: Optional[int] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    uid = current_user["gid"]
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                scope_clause = """(
                    r.share_scope IN ('global', 'team')
                    OR (r.share_scope = 'project' AND r.list_gid IN (
                            SELECT l.gid FROM workmanship_work_lists l
                            JOIN workmanship_auth_project_members pm ON pm.project_gid = l.project_gid
                            WHERE pm.user_gid = %s))
                )"""
                clauses = [scope_clause]
                params: list = [uid]
                if status:
                    clauses.append("r.status = %s"); params.append(status)
                if list_gid:
                    clauses.append("r.list_gid = %s"); params.append(list_gid)
                if q:
                    clauses.append("(r.name LIKE %s OR r.code LIKE %s)")
                    params.extend([f"%{q}%", f"%{q}%"])
                where = " AND ".join(clauses)
                limit_clause = f" LIMIT {int(limit)}" if limit else ""
                sql = f"SELECT r.* FROM workmanship_know_craft_rules r WHERE {where} ORDER BY r.created_at DESC{limit_clause}"
                cur.execute(sql, params)
                rows = cur.fetchall()
        return {"success": True, "data": [_row_to_dict(dict(r)) for r in rows]}
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("list_rules error: %s", e)
        return {"success": True, "data": []}


@router.post("/api/rules", status_code=201)
def create_rule(body: RuleBody, current_user: dict = Depends(get_current_user)):
    gid = str(next_gid())
    display_id = f"R-C{next_display_id('rules_display_seq'):08d}"
    uid = current_user["gid"]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO workmanship_know_craft_rules (
                    gid, display_id, code, name, rule_type, enforcement_level, status,
                    share_scope, list_gid, context_class_gid, rule_definition,
                    applicable_scope, attachments, creator_gid
                ) VALUES (%s, %s,
                          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    gid, display_id, body.code, body.name, body.rule_type, body.enforcement_level,
                    body.status, body.share_scope, body.list_gid, body.context_class_gid,
                    json.dumps(body.rule_definition),
                    json.dumps(getattr(body, 'applicable_scope', {})), json.dumps(getattr(body, 'attachments', [])), uid,
                ),
            )
        conn.commit()
    return {"success": True, "data": {"gid": gid}}


@router.get("/api/rules/{gid}")
def get_rule(gid: str, current_user: Optional[dict] = Depends(get_current_user_optional)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM workmanship_know_craft_rules WHERE gid = %s", (gid,))
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="规则不存在")
    return {"success": True, "data": _row_to_dict(dict(row))}


@router.patch("/api/rules/{gid}")
def update_rule(gid: str, body: dict, current_user: dict = Depends(get_current_user)):
    allowed = {
        "code", "name", "rule_type", "enforcement_level", "status",
        "share_scope", "list_gid", "context_class_gid", "rule_definition", "expression",
    }
    json_fields = {"rule_definition"}
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
            cur.execute(f"UPDATE workmanship_know_craft_rules SET {set_clause} WHERE gid = %s", params)
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="规则不存在")
        conn.commit()
    return {"success": True}


@router.delete("/api/rules/{gid}")
def delete_rule(gid: str, current_user: dict = Depends(get_current_user)):
    uid = current_user["gid"]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """DELETE FROM workmanship_know_craft_rules WHERE gid = %s
                   AND (creator_gid = %s
                        OR %s IN (
                            SELECT gid FROM workmanship_auth_users
                            WHERE system_role IN ('super_admin','team_admin','rule_admin')
                        ))""",
                (gid, uid, uid),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="规则不存在或无权限")
        conn.commit()
    return {"success": True}

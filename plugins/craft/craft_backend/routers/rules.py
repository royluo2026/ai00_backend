"""Craft-owned rule CRUD API."""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.platform_sdk.auth import build_profile, get_current_user
from backend.platform_sdk.ids import next_display_id, next_gid
from ..data.connection import get_conn

router = APIRouter(tags=["rules"])
_log = logging.getLogger(__name__)


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


def _row_to_dict(row: dict) -> dict:
    return {
        "gid": row["gid"], "display_id": row.get("display_id") or "",
        "code": row.get("code") or "", "name": row["name"],
        "rule_type": row.get("rule_type") or "process",
        "enforcement_level": row.get("enforcement_level") or "advisory",
        "status": row.get("status") or "draft",
        "share_scope": row.get("share_scope") or "team",
        "list_gid": row.get("list_gid"), "context_class_gid": row.get("context_class_gid"),
        "rule_definition": row.get("rule_definition") or {},
        "deviation_count": row.get("deviation_count") or 0,
        "created_at": str(row["created_at"]), "updated_at": str(row["updated_at"]),
    }


def _visible_projects(user: dict) -> tuple[bool, list[str]]:
    role = user.get("org_role") or user.get("system_role", "external")
    if role in {"super_admin", "team_admin", "rule_admin"}:
        return True, []
    profile = build_profile(user)
    project_gids = sorted({
        str(grant.get("scope_gid")) for grant in profile.get("grants", [])
        if grant.get("scope_gid") and str(grant.get("scope_type") or "project") == "project"
    })
    return False, project_gids


@router.get("/api/rules")
def list_rules(
    status: Optional[str] = Query(None), list_gid: Optional[str] = Query(None),
    q: Optional[str] = Query(None), limit: Optional[int] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    uid = current_user["gid"]
    is_admin, projects = _visible_projects(current_user)
    clauses = ["(r.share_scope IN ('global','team') OR r.creator_gid=%s"]
    params: list = [uid]
    if is_admin:
        clauses[0] += " OR r.share_scope='project')"
    else:
        # Non-admin project visibility cannot be inferred by joining the
        # Project database. Project-scoped rule composition uses capabilities.
        clauses[0] += ")"
    if status:
        clauses.append("r.status=%s"); params.append(status)
    if list_gid:
        clauses.append("r.list_gid=%s"); params.append(list_gid)
    if q:
        clauses.append("(r.name LIKE %s OR r.code LIKE %s)"); params.extend([f"%{q}%", f"%{q}%"])
    bounded_limit = max(1, min(int(limit or 200), 500))
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT r.* FROM workmanship_know_craft_rules r WHERE {' AND '.join(clauses)} "
                    f"ORDER BY r.created_at DESC LIMIT {bounded_limit}", params,
                )
                rows = cur.fetchall()
        return {"success": True, "data": [_row_to_dict(dict(row)) for row in rows]}
    except Exception as exc:
        _log.warning("list_rules error: %s", exc)
        return {"success": True, "data": []}


@router.post("/api/rules", status_code=201)
def create_rule(body: RuleBody, current_user: dict = Depends(get_current_user)):
    gid = str(next_gid())
    display_id = f"R-C{next_display_id('rules_display_seq'):08d}"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO workmanship_know_craft_rules
                   (gid,display_id,code,name,rule_type,enforcement_level,status,share_scope,
                    list_gid,context_class_gid,rule_definition,applicable_scope,attachments,creator_gid)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (gid, display_id, body.code, body.name, body.rule_type, body.enforcement_level,
                 body.status, body.share_scope, body.list_gid, body.context_class_gid,
                 json.dumps(body.rule_definition), "{}", "[]", current_user["gid"]),
            )
        conn.commit()
    return {"success": True, "data": {"gid": gid}}


@router.get("/api/rules/{gid}")
def get_rule(gid: str, _user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM workmanship_know_craft_rules WHERE gid=%s", (gid,))
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="规则不存在")
    return {"success": True, "data": _row_to_dict(dict(row))}


@router.patch("/api/rules/{gid}")
def update_rule(gid: str, body: dict, _user: dict = Depends(get_current_user)):
    allowed = {"code", "name", "rule_type", "enforcement_level", "status", "share_scope", "list_gid", "context_class_gid", "rule_definition", "expression"}
    updates = {key: (json.dumps(value) if key == "rule_definition" else value) for key, value in body.items() if key in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="没有可更新的字段")
    params = list(updates.values()) + [gid]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE workmanship_know_craft_rules SET {','.join(f'{key}=%s' for key in updates)},updated_at=NOW() WHERE gid=%s", params)
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="规则不存在")
        conn.commit()
    return {"success": True}


@router.delete("/api/rules/{gid}")
def delete_rule(gid: str, current_user: dict = Depends(get_current_user)):
    role = current_user.get("org_role") or current_user.get("system_role", "external")
    admin = role in {"super_admin", "team_admin", "rule_admin"}
    sql = "DELETE FROM workmanship_know_craft_rules WHERE gid=%s"
    params: list = [gid]
    if not admin:
        sql += " AND creator_gid=%s"; params.append(current_user["gid"])
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="规则不存在或无权限")
        conn.commit()
    return {"success": True}

"""
backend/routers/rule_engine.py
───────────────────────────────
CEL 规则引擎 API。

端点：
  POST /api/rule-engine/check                         — 单条规则检验
  POST /api/rule-engine/audit/bop-version/{gid}       — BOP 版本批量审计
"""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..data.connection import get_conn
from ..rule_engine.checker import check_entry_rules
from ..rule_engine.executor import RuleResult, check_rule
from backend.platform_sdk.auth import get_current_user

router = APIRouter(tags=["rule-engine"])
_log = logging.getLogger(__name__)


# ── 单条规则检验 ───────────────────────────────────────────────────────────────

class CheckBody(BaseModel):
    rule_gid: str
    context: dict[str, Any] = {}


@router.post("/api/rule-engine/check")
def check_single_rule(body: CheckBody, _u=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid, name, expression, enforcement_level"
                " FROM workmanship_know_craft_rules WHERE gid = %s",
                (body.rule_gid,),
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(404, "规则不存在")
    if not row["expression"]:
        return {"rule_gid": body.rule_gid, "result": RuleResult.SKIP, "message": "规则无 CEL 表达式"}

    result, msg = check_rule(row["expression"], body.context)
    return {
        "rule_gid":         body.rule_gid,
        "rule_name":        row["name"],
        "result":           result.value,
        "message":          msg,
        "enforcement_level": row["enforcement_level"],
    }


# ── BOP 版本批量审计 ───────────────────────────────────────────────────────────

@router.post("/api/rule-engine/audit/bop-version/{version_gid}")
def audit_bop_version(
    version_gid: str,
    dry_run: bool = Query(True, description="True=只返回结果，False=同时创建 Issue"),
    _u=Depends(get_current_user),
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid, node_type, title FROM workmanship_bop_bop_entries"
                " WHERE version_gid = %s AND is_deleted = FALSE",
                (version_gid,),
            )
            entries = [dict(r) for r in cur.fetchall()]

    if not entries:
        return {"version_gid": version_gid, "total_entries": 0, "violation_count": 0, "violations": []}

    violations: list[dict] = []
    for entry in entries:
        warnings = check_entry_rules(entry["node_type"], entry["gid"])
        if warnings:
            violations.append({
                "entry_gid":   entry["gid"],
                "entry_title": entry.get("title", ""),
                "node_type":   entry["node_type"],
                "warnings":    warnings,
            })

    return {
        "version_gid":     version_gid,
        "total_entries":   len(entries),
        "violation_count": len(violations),
        "violations":      violations,
    }

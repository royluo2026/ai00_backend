"""
backend/routers/ai_audit.py
────────────────────────────
AI 工具调用审计日志端点

POST /api/ai/audit          — 内部调用（Python 端 fire-and-forget），写入 app.ai_audit_logs
GET  /api/ai/audit-logs     — 超管查询，支持 session_gid / user_gid / tool_name / limit / offset
"""
from fastapi import APIRouter, Depends, Query

from backend.db.connection import get_conn
from backend.routers.deps import get_current_user, require_role
from backend.utils.gid import next_gid

router = APIRouter(prefix="/api/ai", tags=["ai_audit"])

_SUPER_ONLY = require_role("super_admin")


# ── 内部写入（无需鉴权，仅 Python 内网调用）────────────────────────────────────

@router.post("/audit", include_in_schema=False)
def record_audit(body: dict):
    """
    由 ai_tool_logger.push_cloud_audit() 调用，写入 app.ai_audit_logs。
    不校验 token（内网调用），仅限本地 uvicorn 可达。
    """
    gid = body.get("gid") or str(next_gid())
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO app.ai_audit_logs
                        (gid, session_gid, user_gid, tool_name, is_write, is_confirmed,
                         inputs_json, result_json, resource_gid, resource_type, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (gid) DO NOTHING
                """, (
                    gid,
                    body.get("session_gid", ""),
                    body.get("user_gid", ""),
                    body.get("tool_name", ""),
                    body.get("is_write", False),
                    body.get("is_confirmed", False),
                    body.get("inputs_json", "{}"),
                    body.get("result_json", "{}"),
                    body.get("resource_gid", ""),
                    body.get("resource_type", ""),
                    body.get("status", "ok"),
                ))
        return {"success": True, "gid": gid}
    except Exception as e:
        # 审计失败不影响主流程，返回 200 但记录错误
        return {"success": False, "error": str(e)}


# ── 超管查询 ──────────────────────────────────────────────────────────────────

@router.get("/balance")
def get_ai_balance(
    user_gid: str = Query(default=""),
    _user:    dict = Depends(get_current_user),
):
    """返回用户 AI 使用余额。当前未实现计费，返回 supported=false。"""
    return {"supported": False, "balance": 0.0}


@router.get("/audit-logs")
def list_audit_logs(
    session_gid: str = Query(default=""),
    user_gid:    str = Query(default=""),
    tool_name:   str = Query(default=""),
    is_write:    str = Query(default=""),   # "true" | "false" | ""
    limit:       int = Query(default=50, ge=1, le=500),
    offset:      int = Query(default=0,  ge=0),
    _user:       dict = Depends(_SUPER_ONLY),
):
    """超管专用：查询 AI 工具调用审计日志（支持按会话/用户/工具过滤）。"""
    conditions = ["1=1"]
    params: list = []

    if session_gid:
        conditions.append("session_gid = %s")
        params.append(session_gid)
    if user_gid:
        conditions.append("user_gid = %s")
        params.append(user_gid)
    if tool_name:
        conditions.append("tool_name ILIKE %s")
        params.append(f"%{tool_name}%")
    if is_write == "true":
        conditions.append("is_write = TRUE")
    elif is_write == "false":
        conditions.append("is_write = FALSE")

    where = " AND ".join(conditions)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM app.ai_audit_logs WHERE {where}",
                params,
            )
            total = cur.fetchone()["count"]

            cur.execute(
                f"""
                SELECT id, gid, session_gid, user_gid, tool_name, is_write, is_confirmed,
                       inputs_json, result_json, resource_gid, resource_type, status, created_at
                FROM app.ai_audit_logs
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            rows = cur.fetchall()

    logs = [
        {
            "id":            r["id"],
            "gid":           r["gid"],
            "session_gid":   r["session_gid"],
            "user_gid":      r["user_gid"],
            "tool_name":     r["tool_name"],
            "is_write":      r["is_write"],
            "is_confirmed":  r["is_confirmed"],
            "inputs_json":   r["inputs_json"],
            "result_json":   r["result_json"],
            "resource_gid":  r["resource_gid"],
            "resource_type": r["resource_type"],
            "status":        r["status"],
            "created_at":    r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]
    return {"logs": logs, "total": total, "limit": limit, "offset": offset}

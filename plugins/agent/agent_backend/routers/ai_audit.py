"""
backend/routers/ai_audit.py
────────────────────────────
AI 工具调用审计日志端点

POST /api/ai/audit          — 内部调用（Python 端 fire-and-forget），写入 workmanship_app_ai_audit_logs
GET  /api/ai/audit-logs     — 超管查询，支持 session_gid / user_gid / tool_name / limit / offset
"""
from fastapi import APIRouter, Depends, Query

from backend.db.connection import get_conn
from backend.routers.deps import get_current_user, require_role
from backend.utils.gid import next_gid

router = APIRouter(prefix="/api/ai", tags=["ai_audit"])

_SUPER_ONLY = require_role("super_admin")


def _ensure_ai_audit_table() -> None:
    """幂等建表：AI 审计日志（MySQL/OceanBase 兼容）。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS workmanship_app_ai_audit_logs (
                    id            BIGINT NOT NULL AUTO_INCREMENT,
                    gid           CHAR(36)     NOT NULL,
                    session_gid   VARCHAR(128) NOT NULL DEFAULT '',
                    user_gid      VARCHAR(128) NOT NULL DEFAULT '',
                    tool_name     VARCHAR(128) NOT NULL DEFAULT '',
                    is_write      BOOLEAN      NOT NULL DEFAULT FALSE,
                    is_confirmed  BOOLEAN      NOT NULL DEFAULT FALSE,
                    inputs_json   LONGTEXT,
                    result_json   LONGTEXT,
                    resource_gid  VARCHAR(128) NOT NULL DEFAULT '',
                    resource_type VARCHAR(64)  NOT NULL DEFAULT '',
                    status        VARCHAR(32)  NOT NULL DEFAULT 'ok',
                    created_at    DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                    updated_at    DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
                    PRIMARY KEY (id),
                    UNIQUE KEY uk_ai_audit_gid (gid),
                    KEY idx_ai_audit_created (created_at),
                    KEY idx_ai_audit_session (session_gid),
                    KEY idx_ai_audit_user (user_gid),
                    KEY idx_ai_audit_tool (tool_name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        conn.commit()


# ── 内部写入（无需鉴权，仅 Python 内网调用）────────────────────────────────────

@router.post("/audit", include_in_schema=False)
def record_audit(body: dict):
    """
    由 ai_tool_logger.push_cloud_audit() 调用，写入 workmanship_app_ai_audit_logs。
    不校验 token（内网调用），仅限本地 uvicorn 可达。
    """
    gid = body.get("gid") or str(next_gid())
    try:
        _ensure_ai_audit_table()
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO workmanship_app_ai_audit_logs
                        (gid, session_gid, user_gid, tool_name, is_write, is_confirmed,
                         inputs_json, result_json, resource_gid, resource_type, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE updated_at = updated_at
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
    _ensure_ai_audit_table()

    conditions = ["1=1"]
    params: list = []

    if session_gid:
        conditions.append("session_gid = %s")
        params.append(session_gid)
    if user_gid:
        conditions.append("user_gid = %s")
        params.append(user_gid)
    if tool_name:
        conditions.append("tool_name LIKE %s")
        params.append(f"%{tool_name}%")
    if is_write == "true":
        conditions.append("is_write = 1")
    elif is_write == "false":
        conditions.append("is_write = 0")

    where = " AND ".join(conditions)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) AS total FROM workmanship_app_ai_audit_logs WHERE {where}",
                params,
            )
            total = cur.fetchone()["total"]

            cur.execute(
                f"""
                SELECT id, gid, session_gid, user_gid, tool_name, is_write, is_confirmed,
                       inputs_json, result_json, resource_gid, resource_type, status, created_at
                  FROM workmanship_app_ai_audit_logs
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

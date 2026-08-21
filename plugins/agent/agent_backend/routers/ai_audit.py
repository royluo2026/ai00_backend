from fastapi import APIRouter, Depends, Query

from backend.platform_sdk.auth import get_current_user, require_role
from ..api.compatibility import invoke_agent_capability

router = APIRouter(prefix="/api/ai", tags=["ai_audit"])
_SUPER_ONLY = require_role("super_admin")


@router.post("/audit", include_in_schema=False)
async def record_audit(body: dict, user: dict = Depends(get_current_user)):
    """Authenticated audit ingestion; callers cannot forge another user's identity."""
    data = await invoke_agent_capability("agent.audit.record", dict(body), user)
    payload = data.get("data", data) if isinstance(data, dict) else {}
    return {"success": True, "gid": payload.get("gid")}


@router.get("/balance", status_code=410)
def get_ai_balance(user_gid: str = Query(default=""), _user: dict = Depends(get_current_user)):
    return {
        "supported": False,
        "balance": 0.0,
        "error": "AI balance is not an Agent capability; this legacy endpoint is retired",
    }


@router.get("/audit-logs")
async def list_audit_logs(
    session_gid: str = Query(default=""),
    user_gid: str = Query(default=""),
    tool_name: str = Query(default=""),
    is_write: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _user: dict = Depends(_SUPER_ONLY),
):
    data = await invoke_agent_capability(
        "agent.audit.read",
        {
            "session_gid": session_gid,
            "user_gid": user_gid,
            "tool_name": tool_name,
            "is_write": is_write,
            "limit": limit,
            "offset": offset,
        },
        _user,
    )
    return data.get("data", data) if isinstance(data, dict) else data

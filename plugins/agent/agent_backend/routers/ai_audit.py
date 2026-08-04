from fastapi import APIRouter, Depends, Query

from backend.platform_sdk.auth import get_current_user, require_role
from ..data.audit_repository import AuditRepository

router = APIRouter(prefix="/api/ai", tags=["ai_audit"])
_SUPER_ONLY = require_role("super_admin")
_repository = AuditRepository()


@router.post("/audit", include_in_schema=False)
def record_audit(body: dict, user: dict = Depends(get_current_user)):
    """Authenticated audit ingestion; callers cannot forge another user's identity."""
    event = dict(body)
    event["user_gid"] = user.get("gid", "")
    try:
        gid = _repository.record(event)
        return {"success": True, "gid": gid}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@router.get("/balance")
def get_ai_balance(user_gid: str = Query(default=""), _user: dict = Depends(get_current_user)):
    return {"supported": False, "balance": 0.0}


@router.get("/audit-logs")
def list_audit_logs(
    session_gid: str = Query(default=""),
    user_gid: str = Query(default=""),
    tool_name: str = Query(default=""),
    is_write: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _user: dict = Depends(_SUPER_ONLY),
):
    total, rows = _repository.list(
        session_gid=session_gid,
        user_gid=user_gid,
        tool_name=tool_name,
        is_write=is_write,
        limit=limit,
        offset=offset,
    )
    logs = []
    for row in rows:
        item = dict(row)
        if hasattr(item.get("created_at"), "isoformat"):
            item["created_at"] = item["created_at"].isoformat()
        logs.append(item)
    return {"logs": logs, "total": total, "limit": limit, "offset": offset}

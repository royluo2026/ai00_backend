"""Versioned public projections for trusted in-process domain composition."""
from __future__ import annotations

from .infrastructure.repository import ProjectManagementRepository


def list_recent_follows(user_gid: str, limit: int = 20) -> list[dict]:
    safe_limit = max(1, min(int(limit), 100))
    return ProjectManagementRepository().fetch_all(
        "SELECT gid,item_type,item_gid,item_title,notify_on FROM workmanship_work_follows "
        f"WHERE user_gid=%s ORDER BY created_at DESC LIMIT {safe_limit}", (user_gid,)
    )


__all__ = ["list_recent_follows"]

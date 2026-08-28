"""Closed browser-visible current-actor identity projection."""
from __future__ import annotations

from typing import Any


class IdentityProfileService:
    def get_current(self, *, actor: dict[str, Any]) -> dict:
        actor_gid = str(actor.get("gid") or "").strip()
        if not actor_gid:
            raise ValueError("actor.gid 无效")
        permissions = actor.get("permission_ids", actor.get("permissions", []))
        if not isinstance(permissions, (list, tuple, set)) or not all(isinstance(item, str) for item in permissions):
            raise ValueError("permission_ids 无效")
        teams = actor.get("team_gids", [])
        if not isinstance(teams, (list, tuple)) or not all(isinstance(item, str) for item in teams):
            raise ValueError("team_gids 无效")
        return {"profile": {
            "actor_gid": actor_gid,
            "display_name": str(actor.get("display_name", actor.get("name", "")) or ""),
            "tenant_gid": str(actor.get("tenant_gid") or ""),
            "team_gids": [str(item) for item in teams],
            "locale": str(actor.get("locale") or ""),
            "timezone": str(actor.get("timezone") or ""),
            "permission_ids": sorted(set(permissions)),
        }}


__all__ = ["IdentityProfileService"]

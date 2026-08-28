"""Closed browser-visible projection from one trusted effective identity."""
from __future__ import annotations

from typing import Any, Protocol

from backend.db.connection import get_conn
from backend.platform_sdk.effective_identity import build_effective_profile


class IdentityProfileError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class EffectiveIdentityPort(Protocol):
    def resolve(self, *, actor_gid: str, tenant_gid: str) -> dict[str, Any]: ...


class SqlEffectiveIdentityPort:
    def resolve(self, *, actor_gid: str, tenant_gid: str) -> dict[str, Any]:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM workmanship_auth_users WHERE gid=%s AND is_active=TRUE",
                    (actor_gid,),
                )
                row = cur.fetchone()
                user = dict(row) if row else None
                if not user:
                    raise IdentityProfileError("identity_not_found", "身份不存在")
                effective_tenant = str(user.get("team_id") or f"user:{actor_gid}")
                if effective_tenant != tenant_gid:
                    raise IdentityProfileError("tenant_mismatch", "身份不属于请求租户")
                cur.execute(
                    "SELECT gid,grant_type,scope_gid,granted_at,expires_at,note FROM workmanship_auth_permission_grants "
                    "WHERE grantee_gid=%s AND (expires_at IS NULL OR expires_at>NOW())",
                    (actor_gid,),
                )
                grants = [dict(row) for row in cur.fetchall()]
        return build_effective_profile(user, grants)


class IdentityProfileService:
    def __init__(self, *, identity_port: EffectiveIdentityPort | None = None) -> None:
        self.identity_port = identity_port or SqlEffectiveIdentityPort()

    def get_current(self, *, actor: dict[str, Any]) -> dict:
        actor_gid = str(actor.get("gid") or "").strip()
        if not actor_gid:
            raise IdentityProfileError("invalid_input", "actor.gid 无效")
        tenant_gid = str(actor.get("tenant_gid") or actor.get("team_id") or f"user:{actor_gid}").strip()
        if not tenant_gid:
            raise IdentityProfileError("invalid_input", "actor.tenant_gid 无效")
        effective = self.identity_port.resolve(actor_gid=actor_gid, tenant_gid=tenant_gid)
        permissions = effective.get("permission_ids", effective.get("permissions", []))
        if not isinstance(permissions, (list, tuple, set)) or not all(isinstance(item, str) for item in permissions):
            raise IdentityProfileError("invalid_input", "permission_ids 无效")
        teams = effective.get("team_gids") or ([tenant_gid] if not tenant_gid.startswith("user:") else [])
        if not isinstance(teams, (list, tuple)) or not all(isinstance(item, str) for item in teams):
            raise IdentityProfileError("invalid_input", "team_gids 无效")
        return {"profile": {
            "actor_gid": actor_gid,
            "display_name": str(effective.get("display_name", effective.get("name", "")) or ""),
            "tenant_gid": tenant_gid,
            "team_gids": [str(item) for item in teams],
            "locale": str(effective.get("locale") or ""),
            "timezone": str(effective.get("timezone") or ""),
            "permission_ids": sorted(set(permissions)),
        }}


__all__ = ["EffectiveIdentityPort", "IdentityProfileError", "IdentityProfileService", "SqlEffectiveIdentityPort"]

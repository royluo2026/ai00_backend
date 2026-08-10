"""
backend/routers/deps.py
────────────────────────
FastAPI 依赖项：JWT 验证、权限门控。
"""
import logging
from datetime import UTC, datetime
from typing import Optional
import jwt as pyjwt

from fastapi import Header, HTTPException, status

from backend.services import jwt_service, user_service
from backend.capability_v2.identity import AuthenticatedPrincipal

_log = logging.getLogger(__name__)

# 从客户端代码同步的权限常量（不依赖客户端模块，独立定义）
_ROLE_PERMISSIONS = {
    "super_admin":    {"system.tech_config", "system.app_config", "system.user.manage", "system.plugin.manage",
                       "project.create", "project.manage_any", "project.view",
                       "craft.write_direct", "craft.write_draft", "craft.view",
                       "rule.manage", "rule.view", "template.manage", "template.view",
                       "knowledge.manage", "knowledge.view",
                       "approval.submit", "approval.approve", "feishu.view"},
    "team_admin":     {"system.app_config", "system.user.manage",
                       "project.create", "project.manage_any", "project.view",
                       "craft.write_direct", "craft.write_draft", "craft.view",
                       "rule.manage", "rule.view", "template.manage", "template.view",
                       "knowledge.manage", "knowledge.view",
                       "approval.submit", "approval.approve", "feishu.view"},
    "project_admin":  {"project.manage_assigned", "project.view",
                       "craft.write_direct", "craft.write_draft", "craft.view",
                       "rule.view", "template.view", "knowledge.view",
                       "approval.submit", "approval.approve", "feishu.view"},
    "rule_admin":     {"project.view", "craft.view",
                       "rule.manage", "rule.view", "template.view", "knowledge.view",
                       "approval.submit", "feishu.view"},
    # knowledge_admin 兼管模板/标准工序（原 template_admin 职责合并）
    "knowledge_admin":{"project.view", "craft.view",
                       "rule.view",
                       "template.manage", "template.view",
                       "knowledge.manage", "knowledge.view",
                       "approval.submit", "feishu.view"},
    "member":         {"project.view", "craft.write_direct", "craft.write_draft", "craft.view",
                       "rule.view", "template.view", "knowledge.view",
                       "approval.submit", "feishu.view"},
    "external":       {"external.view"},
}

# 新四层模型：org_role 基线权限（3值）
_ORG_ROLE_PERMISSIONS = {
    "super_admin": {"system.tech_config", "system.app_config", "system.user.manage", "system.plugin.manage",
                    "project.create", "project.manage_any", "project.view",
                    "craft.write_direct", "craft.write_draft", "craft.view",
                    "rule.manage", "rule.view", "template.manage", "template.view",
                    "knowledge.manage", "knowledge.view",
                    "approval.submit", "approval.approve", "feishu.view"},
    "member":      {"project.view", "craft.write_direct", "craft.write_draft", "craft.view",
                    "rule.view", "template.view", "knowledge.view",
                    "approval.submit", "feishu.view"},
    "external":    {"external.view"},
}

# grant 增量权限（叠加到 org_role 基线）
_GRANT_PERMISSIONS = {
    "team_admin":    {"system.app_config", "system.user.manage", "system.plugin.manage",
                      "project.create", "project.manage_any",
                      "rule.manage", "knowledge.manage", "template.manage",
                      "approval.approve"},
    "project_owner": {"project.manage_assigned", "craft.write_direct",
                      "ebom.import", "approval.approve"},
    "section_lead":  {"craft.write_direct"},
}

_SETTINGS_VISIBILITY = {
    "super_admin":    ["appearance","shortcuts","general","database",
                       "file-store","feishu","plugin-market","user-management"],
    "team_admin":     ["appearance","shortcuts","general",
                       "file-store","feishu","plugin-market","user-management"],
    "project_admin":  ["appearance","shortcuts","general","feishu"],
    "rule_admin":     ["appearance","shortcuts","general","feishu"],
    "knowledge_admin":["appearance","shortcuts","general","feishu"],
    "member":         ["appearance","shortcuts","general","feishu"],
    "external":       ["appearance"],
}


def _get_user_grants(user_gid: str) -> list:
    """查询用户的 permission_grants 列表。DB 不可达时返回空列表。"""
    from backend.db.connection import get_conn
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT gid, grant_type, scope_gid, granted_at, expires_at, note "
                    "FROM workmanship_auth_permission_grants "
                    "WHERE grantee_gid = %s "
                    "  AND (expires_at IS NULL OR expires_at > NOW())",
                    (user_gid,),
                )
                return [dict(r) for r in cur.fetchall()]
    except Exception:
        _log.warning("get_user_grants: DB 查询失败 user_gid=%s", user_gid, exc_info=True)
        return []


def get_current_user(x_ai00_token: str = Header(alias="X-AI00-Token")) -> dict:
    """
    验证客户端携带的 JWT，返回用户 dict。
    无效/过期 → 401。
    """
    try:
        payload = jwt_service.verify(x_ai00_token)
    except pyjwt.InvalidTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=f"Invalid token: {e}")

    try:
        user = user_service.get_by_gid(payload["sub"])
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"User lookup failed: {e}")

    if not user or not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="User not found or inactive")
    # 注入 org_role（JWT payload 优先，DB 字段 fallback）
    user["org_role"] = (
        payload.get("org_role")
        or user.get("org_role")
        or _derive_org_role(user.get("system_role", "external"))
    )
    return user


def get_authenticated_principal(
    x_ai00_token: str = Header(alias="X-AI00-Token"),
) -> AuthenticatedPrincipal:
    """Build a trusted Web principal without accepting client source or permission headers."""
    try:
        payload = jwt_service.verify(x_ai00_token)
    except pyjwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {exc}") from exc
    try:
        user = user_service.get_by_gid(payload["sub"])
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"User lookup failed: {exc}") from exc
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    authenticated_at = _authentication_time(payload)
    return AuthenticatedPrincipal(
        user_id=str(user["gid"]),
        authentication_method="jwt",
        authenticated_at=authenticated_at,
    )


def _authentication_time(payload: dict) -> datetime:
    value = payload.get("auth_time", payload.get("iat"))
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Invalid authentication time") from exc
        if parsed.tzinfo is not None and parsed.utcoffset() is not None:
            return parsed
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Authentication time is required")


def _derive_org_role(system_role: str) -> str:
    if system_role == "super_admin":
        return "super_admin"
    if system_role == "external":
        return "external"
    return "member"


def get_current_user_claims_only(x_ai00_token: str = Header(alias="X-AI00-Token")) -> dict:
    """
    仅验证 JWT 签名并返回 payload 派生的用户信息，不依赖数据库。
    用于数据库配置等需要在 DB 不可用时仍可操作的管理端点。
    """
    try:
        payload = jwt_service.verify(x_ai00_token)
    except pyjwt.InvalidTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=f"Invalid token: {e}")

    system_role = payload.get("system_role", "external")
    org_role = payload.get("org_role") or _derive_org_role(system_role)
    return {
        "gid": payload.get("sub", ""),
        "system_role": system_role,
        "org_role": org_role,
        "team_id": payload.get("team_id") or "",
        "name": payload.get("name", ""),
        "email": payload.get("email", ""),
        "avatar_url": payload.get("avatar_url", ""),
        "is_active": True,
    }


_LOCAL_USER = {
    "gid": "local",
    "system_role": "member",
    "org_role": "member",
    "team_id": "",
}


def get_current_user_optional(
    x_ai00_token: Optional[str] = Header(default=None, alias="X-AI00-Token"),
) -> dict:
    """
    与 get_current_user 相同，但 token 缺失或无效时降级为 local_user（本地模式兼容）。
    仅用于不需要严格身份验证的端点（如清单 CRUD）。
    """
    if x_ai00_token:
        try:
            payload = jwt_service.verify(x_ai00_token)
            user = user_service.get_by_gid(payload["sub"])
            if user and user["is_active"]:
                user["org_role"] = (
                    payload.get("org_role")
                    or user.get("org_role")
                    or _derive_org_role(user.get("system_role", "external"))
                )
                return user
        except Exception:
            _log.debug("get_current_user_optional: token 验证失败，降级为 local_user", exc_info=True)
    return _LOCAL_USER


def require_role(*roles: str):
    """工厂函数：生成要求特定角色的 Depends（优先读 org_role，fallback system_role）"""
    def _dep(current_user: dict = __import__('fastapi').Depends(get_current_user)):
        user_role = current_user.get("org_role") or current_user.get("system_role", "external")
        # 兼容旧角色：team_admin/project_admin/rule_admin/knowledge_admin 均映射 member
        if user_role not in roles:
            # fallback：旧 system_role 直接匹配
            if current_user.get("system_role") not in roles:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                    detail="权限不足")
        return current_user
    return _dep


def require_grant(grant_type: str, scope_gid: str = None):
    """工厂函数：生成要求特定 grant 的 Depends。super_admin 直接通过。"""
    def _dep(current_user: dict = __import__('fastapi').Depends(get_current_user)):
        org_role = current_user.get("org_role") or _derive_org_role(current_user.get("system_role","external"))
        if org_role == "super_admin":
            return current_user
        grants = _get_user_grants(current_user["gid"])
        for g in grants:
            if g["grant_type"] == grant_type:
                if scope_gid is None or g.get("scope_gid") == scope_gid or g.get("scope_gid") is None:
                    return current_user
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"需要 {grant_type} 授权")
    return _dep


def scope_visible_clause(current_user: dict,
                          owner_col: str = "owner_gid",
                          team_col: str = "team_id",
                          pk_col: str = None) -> tuple:
    """Build a consumer-table-only visibility clause from a Base projection."""
    from backend.platform_sdk.access import build_access_scope

    scope = build_access_scope(current_user)
    if scope["is_admin"]:
        return "1=1", []
    if pk_col is None:
        prefix = owner_col.split(".")[0] + "." if "." in owner_col else ""
        pk_col = f"{prefix}gid"

    clauses = ["share_scope = 'global'", f"(share_scope = 'local' AND {owner_col} = %s)"]
    params: list[str] = [scope["user_gid"]]
    if scope["team_gids"]:
        placeholders = ",".join(["%s"] * len(scope["team_gids"]))
        clauses.append(f"(share_scope = 'team' AND {team_col} IN ({placeholders}))")
        params.extend(scope["team_gids"])
    if scope["project_gids"]:
        placeholders = ",".join(["%s"] * len(scope["project_gids"]))
        clauses.append(f"(share_scope = 'project' AND {pk_col} IN ({placeholders}))")
        params.extend(scope["project_gids"])
    return "(" + " OR ".join(clauses) + ")", params



def build_profile(user: dict) -> dict:
    """构建前端用的用户 profile（含权限列表 + grants 数组）"""
    role     = user.get("system_role", "external")
    org_role = user.get("org_role") or _derive_org_role(role)
    ext      = user.get("external_subtype")

    # 基线权限（优先用 org_role，fallback 旧 system_role）
    base_perms = set(_ORG_ROLE_PERMISSIONS.get(org_role)
                     or _ROLE_PERMISSIONS.get(role, set()))
    # 外包权限同 member
    if role == "external" and ext == "outsource":
        base_perms = set(_ROLE_PERMISSIONS["member"])

    # 叠加 grants
    grants = _get_user_grants(user["gid"])
    grant_perms = set()
    for g in grants:
        grant_perms |= set(_GRANT_PERMISSIONS.get(g["grant_type"], set()))

    perms = list(base_perms | grant_perms)

    return {
        **{k: v for k, v in user.items() if k != "feishu_open_id"},
        "org_role":       org_role,
        "permissions":    perms,
        "grants":         grants,
        "visible_panels": _SETTINGS_VISIBILITY.get(role, ["appearance"]),
    }


def build_capability_authorization_grants(
    user: dict, tenant_id: str, consumer_type: str = "web", identity=None,
):
    """Translate reviewed legacy roles into explicit V2 resource/data grants."""
    from backend.capability_v2.authorization import AuthorizationGrants

    profile = build_profile(user)
    if consumer_type == "plugin":
        if identity is None or not identity.consumer.mount_session_id:
            raise PermissionError("plugin mount identity is required")
        from backend.db.connection import get_conn
        from backend.plugin_platform.mounts import SqlMountSessionStore
        session = SqlMountSessionStore(get_conn).get_live_by_id(
            identity.consumer.mount_session_id
        )
        actor_id = identity.actor.user_id or identity.actor.service_id
        if (
            session.user_id != str(user.get("gid"))
            or session.user_id != actor_id
            or session.tenant_id != tenant_id
            or session.plugin_id != identity.consumer.consumer_id
            or session.plugin_version != identity.consumer.consumer_version
            or session.installation_id != identity.consumer.installation_id
        ):
            raise PermissionError("plugin mount identity binding mismatch")
        return AuthorizationGrants(
            permissions=tuple(sorted(profile.get("permissions", ()))),
            capability_scopes=tuple(sorted(
                value.rsplit("@", 1)[0] for value in session.capability_grants
            )),
            resource_scopes=session.resource_scopes,
            data_scopes=session.data_scopes,
            policy_version=f"plugin-mount-v2:{session.revocation_version}",
            tenant_id=tenant_id,
        )
    resource_scopes = {f"tenant:{tenant_id}"}
    for grant in profile.get("grants", ()):
        scope_gid = str(grant.get("scope_gid") or "").strip()
        if not scope_gid:
            continue
        if grant.get("grant_type") == "project_owner":
            resource_scopes.add(f"project:{scope_gid}")
        elif grant.get("grant_type") == "team_admin":
            resource_scopes.add(f"team:{scope_gid}")
    data_scopes = {"internal"}
    if set(profile.get("permissions", ())) & {
        "craft.view", "craft.write_direct", "knowledge.view", "knowledge.manage"
    }:
        data_scopes.add("confidential")
    if profile.get("org_role") == "super_admin":
        resource_scopes.add("*")
        data_scopes.add("*")
    return AuthorizationGrants(
        permissions=tuple(sorted(profile.get("permissions", ()))),
        capability_scopes=("*",) if consumer_type in {"web", "api"} else (),
        resource_scopes=tuple(sorted(resource_scopes)),
        data_scopes=tuple(sorted(data_scopes)),
        policy_version="legacy-rbac-to-abac-v1",
        tenant_id=tenant_id,
    )

"""
backend/routers/deps.py
────────────────────────
FastAPI 依赖项：JWT 验证、权限门控。
"""
import logging
from typing import Optional
import jwt as pyjwt

from fastapi import Header, HTTPException, status

from backend.services import jwt_service, user_service

_log = logging.getLogger(__name__)

# 从客户端代码同步的权限常量（不依赖客户端模块，独立定义）
_ROLE_PERMISSIONS = {
    "super_admin":    {"system.tech_config", "system.app_config", "system.user.manage",
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
    "member":         {"project.view", "craft.write_draft", "craft.view",
                       "rule.view", "template.view", "knowledge.view",
                       "approval.submit", "feishu.view"},
    "external":       {"external.view"},
}

# 新四层模型：org_role 基线权限（3值）
_ORG_ROLE_PERMISSIONS = {
    "super_admin": {"system.tech_config", "system.app_config", "system.user.manage",
                    "project.create", "project.manage_any", "project.view",
                    "craft.write_direct", "craft.write_draft", "craft.view",
                    "rule.manage", "rule.view", "template.manage", "template.view",
                    "knowledge.manage", "knowledge.view",
                    "approval.submit", "approval.approve", "feishu.view"},
    "member":      {"project.view", "craft.write_draft", "craft.view",
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
    """
    返回 (where_fragment, params_list) 用于拼入 SQL WHERE 子句。
    super_admin 不过滤；其他角色按 share_scope 四级可见规则过滤。
    pk_col: 主键列名（带表别名），默认从 owner_col 提取表前缀 + 'gid'
    """
    role = current_user.get("org_role") or current_user.get("system_role", "external")
    if role == "super_admin":
        return "1=1", []
    uid = current_user["gid"]
    tid = current_user.get("team_id") or ""
    # 自动从 owner_col 推导 pk_col，如 "p.owner_gid" → "p.gid"
    if pk_col is None:
        prefix = owner_col.split('.')[0] + '.' if '.' in owner_col else ''
        pk_col = f"{prefix}gid"
    sql = (
        f"(share_scope = 'global' "
        f"OR (share_scope IN ('team','project') AND {pk_col} IN "
        f"  (SELECT project_gid FROM workmanship_auth_project_members WHERE user_gid = %s)) "
        f"OR (share_scope = 'team' AND {team_col} = %s) "
        f"OR (share_scope = 'local' AND {owner_col} = %s))"
    )
    return sql, [uid, tid, uid]


def task_scope_clauses(uid: str, team_id: str, alias: str = "t") -> tuple[str, list]:
    """
    返回 tasks/issues 表的可见性 WHERE 子句。
    规则：
      - share_scope='local'   → 仅 owner_user_gid = uid
      - share_scope='team'    → 同团队（owner_user_gid 属于同 team_id 的用户）
      - share_scope='project' → 当前用户是该任务所属项目的成员
      - share_scope='global'  → 全部可见
    超管不得特殊绕过。
    """
    a = alias
    if team_id:
        clause = f"""(
            {a}.owner_user_gid = %s
            OR {a}.share_scope = 'global'
            OR ({a}.share_scope = 'team' AND {a}.owner_user_gid IN (
                    SELECT gid FROM workmanship_auth_users WHERE team_id = %s))
            OR ({a}.share_scope = 'project' AND {a}.project_gid IS NOT NULL AND EXISTS(
                    SELECT 1 FROM workmanship_auth_project_members pm
                    WHERE pm.project_gid = {a}.project_gid AND pm.user_gid = %s))
        )"""
        params: list = [uid, team_id, uid]
    else:
        clause = f"""(
            {a}.owner_user_gid = %s
            OR {a}.share_scope = 'global'
            OR ({a}.share_scope = 'project' AND {a}.project_gid IS NOT NULL AND EXISTS(
                    SELECT 1 FROM workmanship_auth_project_members pm
                    WHERE pm.project_gid = {a}.project_gid AND pm.user_gid = %s))
        )"""
        params = [uid, uid]
    return clause, params


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


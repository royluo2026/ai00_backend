"""
backend/services/user_service.py
──────────────────────────────────
用户 CRUD，操作 users_db PostgreSQL。
"""
from datetime import datetime, timezone
from typing import Optional

from backend.db.connection import get_conn, new_gid

SYSTEM_ROLES = [
    "super_admin", "team_admin", "project_admin",
    "rule_admin", "knowledge_admin",
    "member", "external",
]


def _role_to_org_role(system_role: str) -> str:
    """将旧7角色映射到新3值 org_role。"""
    if system_role == "super_admin":
        return "super_admin"
    if system_role == "external":
        return "external"
    return "member"


def get_or_create(
    open_id: str, name: str, email: str, avatar_url: str,
    access_token: str = "", refresh_token: str = "", expires_in: int = 7200,
) -> dict:
    """飞书登录后调用：查找已有用户或自动注册。同时更新飞书 token。

    新用户默认 member 角色。
    例外：若 DB 中尚无超管，且该用户邮箱 == FIRST_SUPER_ADMIN_EMAIL，则直接注册为 super_admin。
    """
    from datetime import timedelta
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        if access_token else None
    )
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM workmanship_auth_users WHERE feishu_open_id = %s", (open_id,)
            )
            row = cur.fetchone()
            if row:
                # 更新头像/姓名 + token，同时同步 org_role
                cur.execute(
                    "UPDATE workmanship_auth_users SET name=%s, avatar_url=%s, "
                    "feishu_access_token=%s, feishu_refresh_token=%s, "
                    "feishu_token_expires_at=%s, org_role=%s, updated_at=NOW() "
                    "WHERE feishu_open_id=%s",
                    (name, avatar_url, access_token, refresh_token, expires_at,
                     _role_to_org_role(dict(row).get("system_role","member")), open_id),
                )
                cur.execute("SELECT * FROM workmanship_auth_users WHERE feishu_open_id=%s", (open_id,))
                updated = cur.fetchone()
                return dict(updated) if updated else dict(row)

            # 新用户：判断是否触发超管自举
            role = _resolve_initial_role(email)
            gid = new_gid()
            cur.execute(
                """INSERT INTO workmanship_auth_users
                   (gid, feishu_open_id, name, email, avatar_url, system_role, org_role,
                    feishu_access_token, feishu_refresh_token, feishu_token_expires_at,
                    notification_prefs)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (gid, open_id, name, email, avatar_url, role, _role_to_org_role(role),
                 access_token, refresh_token, expires_at, '{}'),
            )
            cur.execute("SELECT * FROM workmanship_auth_users WHERE gid=%s", (gid,))
            return dict(cur.fetchone())


def _resolve_initial_role(email: str) -> str:
    """决定新用户初始角色：超管自举条件满足时返回 super_admin，否则 external。"""
    from backend.config import get_settings
    cfg = get_settings()
    if not cfg.first_super_admin_email:
        return "external"
    if email.strip().lower() != cfg.first_super_admin_email:
        return "external"
    # 邮箱匹配，但只有 DB 里还没有超管时才生效（一次性自举，不可反复提权）
    if count_super_admins() > 0:
        return "external"
    return "super_admin"


def get_by_gid(gid: str) -> Optional[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM workmanship_auth_users WHERE gid = %s", (gid,))
            row = cur.fetchone()
            return dict(row) if row else None


def list_users(active_only: bool = True) -> list:
    with get_conn() as conn:
        with conn.cursor() as cur:
            q = "SELECT * FROM workmanship_auth_users"
            if active_only:
                q += " WHERE is_active = TRUE"
            q += " ORDER BY created_at"
            cur.execute(q)
            return [dict(r) for r in cur.fetchall()]


def assign_role(
    operator_gid: str,
    target_gid: str,
    new_role: str,
    external_subtype: Optional[str] = None,
) -> dict:
    """分配系统角色，含权限校验"""
    if new_role not in SYSTEM_ROLES:
        raise ValueError(f"未知角色: {new_role}")

    operator = get_by_gid(operator_gid)
    if not operator:
        raise PermissionError("操作者不存在")
    if operator["system_role"] not in ("super_admin", "team_admin"):
        raise PermissionError("权限不足")
    if new_role == "super_admin" and operator["system_role"] != "super_admin":
        raise PermissionError("只有超管才能授予超管角色")

    # 最后一个超管保护
    if new_role != "super_admin":
        target = get_by_gid(target_gid)
        if target and target["system_role"] == "super_admin":
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM workmanship_auth_users "
                        "WHERE system_role='super_admin' AND is_active=TRUE"
                    )
                    count = cur.fetchone()["count"]
            if count <= 1:
                raise ValueError("系统中至少保留一名超级管理员")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_auth_users SET system_role=%s, external_subtype=%s, "
                "org_role=%s, updated_at=NOW() WHERE gid=%s",
                (new_role, external_subtype, _role_to_org_role(new_role), target_gid),
            )
            conn.commit()
            cur.execute("SELECT * FROM workmanship_auth_users WHERE gid=%s", (target_gid,))
            row = cur.fetchone()
            if not row:
                raise ValueError("目标用户不存在")
            return dict(row)


def count_super_admins() -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM workmanship_auth_users "
                "WHERE system_role='super_admin' AND is_active=TRUE"
            )
            return cur.fetchone()["count"]


def get_feishu_token(user_gid: str) -> str:
    """
    返回该用户的有效 feishu_access_token。
    若已过期，尝试用 refresh_token 刷新后返回；刷新失败或无 token 则返回空字符串。
    """
    user = get_by_gid(user_gid)
    if not user:
        return ""
    access_token   = user.get("feishu_access_token", "")
    refresh_token  = user.get("feishu_refresh_token", "")
    expires_at     = user.get("feishu_token_expires_at")
    if not access_token:
        return ""
    # 检查是否过期（提前 5 分钟视为过期）
    now = datetime.now(timezone.utc)
    if expires_at:
        # expires_at 可能是 datetime 或 str
        if isinstance(expires_at, str):
            from datetime import datetime as _dt
            expires_at = _dt.fromisoformat(expires_at.replace("Z", "+00:00"))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        from datetime import timedelta
        if now >= expires_at - timedelta(minutes=5):
            # 尝试刷新
            if not refresh_token:
                return ""
            try:
                from backend.services.feishu_service import feishu_service
                refreshed = feishu_service.refresh_user_token(refresh_token)
                new_expires = now + timedelta(seconds=refreshed["expires_in"])
                with get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE workmanship_auth_users SET feishu_access_token=%s, "
                            "feishu_refresh_token=%s, feishu_token_expires_at=%s "
                            "WHERE gid=%s",
                            (refreshed["access_token"], refreshed["refresh_token"],
                             new_expires, user_gid),
                        )
                return refreshed["access_token"]
            except Exception:
                return ""
    return access_token


def search_users(q: str, limit: int = 10) -> list:
    """模糊搜索活跃用户（按姓名或邮箱），用于 @mention 候选人列表。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            pattern = f"%{q}%"
            cur.execute(
                "SELECT gid, name, email, avatar_url FROM workmanship_auth_users "
                "WHERE is_active = TRUE AND (name LIKE %s OR email LIKE %s) "
                "ORDER BY name LIMIT %s",
                (pattern, pattern, limit),
            )
            return [dict(r) for r in cur.fetchall()]

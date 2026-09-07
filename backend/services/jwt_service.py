"""
backend/services/jwt_service.py
─────────────────────────────────
JWT 签发与验证。
Payload: {sub: user_gid, system_role, team_id, name, email, avatar_url, exp: ...}
"""
from datetime import datetime, timezone, timedelta
from typing import Optional

import jwt

from backend.config import get_settings

ALGORITHM = "HS256"


def sign(
    user_gid: str,
    system_role: str,
    external_subtype: Optional[str] = None,
    team_id: Optional[str] = None,
    name: str = "",
    email: str = "",
    avatar_url: str = "",
    org_role: Optional[str] = None,
) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    # org_role 推导：若未显式传入，则从 system_role 映射
    if org_role is None:
        if system_role == "super_admin":
            org_role = "super_admin"
        elif system_role == "external":
            org_role = "external"
        else:
            org_role = "member"
    payload = {
        "sub":              user_gid,
        "system_role":      system_role,
        "org_role":         org_role,
        "external_subtype": external_subtype,
        "team_id":          team_id,
        "name":             name,
        "email":            email,
        "avatar_url":       avatar_url,
        "iat":              now,
        "exp":              now + timedelta(hours=s.jwt_expire_hours),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=ALGORITHM)


def verify(token: str) -> dict:
    """
    验证并解码 JWT。
    过期或签名错误 → 抛出 jwt.InvalidTokenError。
    返回 payload dict。
    """
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[ALGORITHM])
        if "desktop_consumer" in payload:
            # Older browser sessions retain their compatibility contract; new
            # desktop sessions always require signed actor and time bounds.
            payload = jwt.decode(token, s.jwt_secret, algorithms=[ALGORITHM], options={"require": ["sub", "iat", "exp"]})
        return payload
    except (TypeError, ValueError) as exc:
        raise jwt.InvalidTokenError("Invalid authentication claims") from exc


def sign_desktop_session(principal, *, tenant_id: str, installation_id: str, consumer_version: str) -> str:
    """Server-only completion of a verified desktop OAuth PKCE authentication.

    The OAuth adapter owns verification of state, redirect and PKCE before
    creating this principal. There is deliberately no browser-token exchange
    endpoint or caller-selected consumer identity.
    """
    from backend.capability_v2.identity import DesktopConsumerClaim, DESKTOP_CONSUMER_ID, IdentityError
    if not principal.user_id or principal.authentication_method != "oauth2_pkce":
        raise IdentityError("desktop_pkce_authentication_required")
    claim = DesktopConsumerClaim(consumer_id=DESKTOP_CONSUMER_ID, tenant_id=tenant_id,
        installation_id=installation_id, consumer_version=consumer_version)
    now = datetime.now(timezone.utc)
    if principal.authenticated_at > now:
        raise IdentityError("desktop_authentication_time_invalid")
    settings = get_settings()
    return jwt.encode(dict(sub=principal.user_id, team_id=tenant_id,
        auth_time=principal.authenticated_at.timestamp(), iat=now,
        exp=now + timedelta(minutes=15),
        desktop_consumer=claim.model_dump()), settings.jwt_secret, algorithm=ALGORITHM)


def decode_unverified(token: str) -> dict:
    """不验证签名，仅解码（调试用）"""
    return jwt.decode(token, options={"verify_signature": False})

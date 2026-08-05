"""Public authentication and authorization surface for official domains."""

from backend.routers.deps import (
    _derive_org_role as derive_org_role,
    _get_user_grants as get_user_grants,
    build_profile,
    get_current_user,
    get_current_user_optional,
    require_role,
    scope_visible_clause,
)

__all__ = [
    "build_profile", "derive_org_role", "get_current_user", "get_user_grants",
    "require_role", "scope_visible_clause", "get_current_user_optional",
]

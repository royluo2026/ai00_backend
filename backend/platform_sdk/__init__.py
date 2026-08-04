"""Stable in-process SDK used by official domains during service extraction."""

from .auth import build_profile, get_current_user, require_role
from .capabilities import invoke_capability_for_user
from .ids import next_gid

__all__ = ["build_profile", "get_current_user", "require_role", "invoke_capability_for_user", "next_gid"]

"""Explicit plugin installation state machine."""
from __future__ import annotations

from dataclasses import dataclass


class LifecycleError(ValueError):
    pass


TRANSITIONS = {
    "disabled": frozenset({"enabled", "upgrading", "uninstalled", "revoked"}),
    "enabled": frozenset({"disabled", "upgrading", "revoked"}),
    "upgrading": frozenset({"enabled", "failed", "rolled_back", "revoked"}),
    "failed": frozenset({"disabled", "rolled_back", "revoked"}),
    "rolled_back": frozenset({"enabled", "disabled", "upgrading", "revoked"}),
    "revoked": frozenset({"uninstalled"}),
    "uninstalled": frozenset(),
}


def require_transition(current: str, target: str) -> None:
    if target not in TRANSITIONS.get(current, frozenset()):
        raise LifecycleError(f"invalid plugin transition: {current} -> {target}")


@dataclass(frozen=True)
class UpgradeResult:
    current_version: str
    previous_version: str | None
    state: str


def begin_upgrade(current_version: str, target_version: str) -> UpgradeResult:
    if current_version == target_version:
        raise LifecycleError("target version is already installed")
    return UpgradeResult(target_version, current_version, "upgrading")


def rollback(current_version: str, previous_version: str | None) -> UpgradeResult:
    if not previous_version:
        raise LifecycleError("no previous version is available")
    return UpgradeResult(previous_version, current_version, "rolled_back")

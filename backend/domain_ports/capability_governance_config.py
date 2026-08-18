"""Shared, fail-closed configuration contract for capability governance.

The application configuration may expose this type without importing the
test-only governance implementation.  Runtime activation remains guarded by
``AI00_DEPLOYMENT_PROFILE=test-governance``.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final


_ALLOWLISTED_RELATIVE_ROOTS: Final[tuple[str, ...]] = (
    "backend/capabilities",
    "backend/capability_v2",
    "backend/domain",
    "backend/domain_ports",
    "backend/migrations",
    "backend/routers",
    "backend/tests",
    "docs/capabilities",
    "plugins",
)


def _repository_root() -> Path:
    """Find the repository from this trusted module location, not user input."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".git").exists():
            return candidate
    raise RuntimeError("governance_repository_root_not_found")


@dataclass(frozen=True)
class GovernanceSettings:
    """Validated settings for the explicitly selected test-governance profile."""

    deployment_profile: str
    repository_root: Path
    allowlisted_relative_roots: tuple[str, ...] = _ALLOWLISTED_RELATIVE_ROOTS

    @property
    def allowed_relative_roots(self) -> tuple[str, ...]:
        """Compatibility name for consumers that prefer a shorter spelling."""
        return self.allowlisted_relative_roots

    @classmethod
    def from_environ(cls, environ: Mapping[str, str]) -> "GovernanceSettings":
        profile = str(environ.get("AI00_DEPLOYMENT_PROFILE", "")).strip()
        if profile != "test-governance":
            raise RuntimeError("AI00_DEPLOYMENT_PROFILE=test-governance is required")
        return cls(deployment_profile=profile, repository_root=_repository_root())


__all__ = ["GovernanceSettings"]

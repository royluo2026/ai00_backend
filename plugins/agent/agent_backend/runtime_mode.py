"""Single source of truth for Agent runtime selection."""
from __future__ import annotations

import os


def runtime_mode() -> str:
    return os.getenv("AI00_AGENT_RUNTIME_MODE", "legacy").strip().lower() or "legacy"


def pi_enabled() -> bool:
    return runtime_mode() == "pi"


__all__ = ["pi_enabled", "runtime_mode"]

"""Craft-owned Capability provider entry point."""
from __future__ import annotations

from typing import Any


def register_capabilities(registry: Any) -> None:
    """Register Craft-owned handlers; never mount routers or start workers."""
    # Domain capabilities are added incrementally by the agreed implementation plan.
    # Keeping the provider callable while empty establishes the ownership boundary.
    del registry

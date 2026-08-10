"""Project Management-owned Capability provider entry point."""
from __future__ import annotations

from typing import Any

from .projects import register_project_capabilities


def register_capabilities(registry: Any) -> None:
    register_project_capabilities(registry)

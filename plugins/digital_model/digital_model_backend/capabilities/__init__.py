"""Official Digital Model Capability provider."""
from __future__ import annotations

from typing import Any

from .models import specs
from .provider import register


def register_capabilities(registry: Any) -> None:
    for spec, handler in specs():
        register(registry, spec, handler)


__all__ = ["register_capabilities"]

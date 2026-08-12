"""Capability Kernel public exports for v3."""
from __future__ import annotations

from .models_next import CapabilityBusinessError, CapabilityContext, CapabilitySpec, CapabilityResult
from .registry_next import CapabilityPermissionError, CapabilityConfirmationError


class _LazyCapabilityRegistry:
    def __getattr__(self, name):
        from backend.capability_v2.bootstrap import get_capability_registry

        return getattr(get_capability_registry(), name)


capability_registry = _LazyCapabilityRegistry()

__all__ = ["CapabilityBusinessError", "CapabilityContext", "CapabilitySpec", "CapabilityResult", "capability_registry", "CapabilityPermissionError", "CapabilityConfirmationError"]

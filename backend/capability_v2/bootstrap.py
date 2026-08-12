"""Atomic construction and publication of the official Capability registry."""
from __future__ import annotations

import sys
import threading
from pathlib import Path

from backend.capabilities.registry_next import CapabilityRegistry

from .domain_manifest import load_domain_manifests
from .provider_loader import DomainProviderLoader


_registry: CapabilityRegistry | None = None
_registry_lock = threading.Lock()


def build_capability_registry(
    root: Path | None = None,
    manifest_path: Path | None = None,
) -> CapabilityRegistry:
    repository_root = (root or Path(__file__).resolve().parents[2]).resolve()
    path = manifest_path or Path(__file__).with_name("official_domains.json")
    registry = CapabilityRegistry()
    DomainProviderLoader(
        repository_root,
        load_domain_manifests(path),
    ).register_all(registry)
    return registry


def get_capability_registry() -> CapabilityRegistry:
    global _registry
    if _registry is not None:
        return _registry
    with _registry_lock:
        if _registry is None:
            complete_registry = build_capability_registry()
            _registry = complete_registry
    return _registry


def reset_capability_registry_for_tests() -> None:
    if "pytest" not in sys.modules:
        raise RuntimeError("capability registry reset is test-only")
    global _registry
    with _registry_lock:
        _registry = None


__all__ = [
    "build_capability_registry",
    "get_capability_registry",
    "reset_capability_registry_for_tests",
]

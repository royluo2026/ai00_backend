"""Atomic construction and publication of the official Capability registry."""
from __future__ import annotations

import sys
import threading
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from backend.capabilities.registry_next import CapabilityRegistry

from .domain_manifest import load_domain_manifests
from .provider_loader import DomainProviderLoader


_registry: CapabilityRegistry | None = None
_registry_lock = threading.Lock()
_test_governance_store_factory: Callable[[], Any] | None = None
_test_governance_service_factory: Callable[[Any], Any] | None = None


def build_capability_registry(
    root: Path | None = None,
    manifest_path: Path | None = None,
    *,
    include_test_governance: bool = False,
) -> CapabilityRegistry:
    if include_test_governance:
        return build_test_governance_capability_registry(root, manifest_path)
    return _build_official_capability_registry(root, manifest_path)


def build_test_governance_capability_registry(
    root: Path | None = None,
    manifest_path: Path | None = None,
    *,
    service_port: Any | None = None,
    store: Any | None = None,
    seed_document: Any | None = None,
    store_factory: Callable[[], Any] | None = None,
    service_factory: Callable[[Any], Any] | None = None,
) -> CapabilityRegistry:
    """Build the explicit test-only governance profile with injectable authority.

    The official registry never imports this extension.  Tests, local tooling,
    and the explicitly selected ``test-governance`` profile may inject a
    service, an in-memory store, and an immutable seed document.  Keeping those
    ports explicit prevents a test bootstrap from silently using production
    persistence while still making the profile useful for end-to-end tests.
    """
    registry = _build_official_capability_registry(root, manifest_path)
    from backend.capability_governance_test.provider import register_governance_capabilities
    from backend.capability_governance_test.service import CapabilityGovernanceService
    from backend.capability_governance_test.store import MemoryGovernanceStore

    governance_store = store or (store_factory() if store_factory is not None else MemoryGovernanceStore())
    if seed_document is not None:
        importer = getattr(governance_store, "import_snapshot", None)
        if not callable(importer):
            raise TypeError("test_governance_store_requires_import_snapshot")
        importer(seed_document)
    service = service_port or (
        service_factory(governance_store) if service_factory is not None
        else CapabilityGovernanceService(store=governance_store)
    )
    register_governance_capabilities(registry, service_port=service)
    return registry


def _build_official_capability_registry(
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
            # Production and ordinary development bootstraps remain strictly
            # official.  Loading the extension requires an explicit profile;
            # an accidental environment variable cannot alter the artifact
            # because the extension itself is test-only and separately built.
            profile = os.environ.get("AI00_DEPLOYMENT_PROFILE", "").strip()
            complete_registry = (
                build_test_governance_capability_registry(
                    store_factory=_test_governance_store_factory,
                    service_factory=_test_governance_service_factory,
                )
                if profile == "test-governance" else build_capability_registry()
            )
            _registry = complete_registry
    return _registry


def reset_capability_registry_for_tests() -> None:
    if "pytest" not in sys.modules:
        raise RuntimeError("capability registry reset is test-only")
    global _registry
    with _registry_lock:
        _registry = None


def configure_test_governance_runtime(
    *,
    store_factory: Callable[[], Any] | None = None,
    service_factory: Callable[[Any], Any] | None = None,
) -> None:
    """Inject persistent test-profile ports before the HTTP app is imported.

    The production bootstrap has no call site for this hook.  A test-governance
    launcher can provide ``SqlGovernanceStore`` (and a workflow-aware service)
    without changing the official registry or placing credentials in module
    globals.  The hook is intentionally test-profile-only and may be reset
    between isolated acceptance runs.
    """
    if str(os.environ.get("AI00_DEPLOYMENT_PROFILE", "")).strip() != "test-governance":
        raise RuntimeError("AI00_DEPLOYMENT_PROFILE=test-governance is required")
    global _test_governance_store_factory, _test_governance_service_factory
    with _registry_lock:
        _test_governance_store_factory = store_factory
        _test_governance_service_factory = service_factory
    with _registry_lock:
        global _registry
        _registry = None


__all__ = [
    "build_capability_registry",
    "build_test_governance_capability_registry",
    "get_capability_registry",
    "reset_capability_registry_for_tests",
    "configure_test_governance_runtime",
]

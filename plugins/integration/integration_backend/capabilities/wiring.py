"""Fail-closed production composition for the Integration provider."""
from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from typing import Any, Callable

from ..application import IntegrationApplication
from ..infrastructure import IntegrationRepository


@dataclass(frozen=True)
class IntegrationProviderAdapters:
    credential_enrollment: Any
    catalog: Any
    connector_runtime: Any
    repository: Any | None = None
    operation_identity: Any | None = None
    network_policy: Any | None = None


AdapterFactory = Callable[[], IntegrationProviderAdapters]


def _configured_factory() -> AdapterFactory:
    target = os.getenv("AI00_INTEGRATION_ADAPTER_FACTORY", "").strip()
    if not target:
        raise RuntimeError(
            "AI00_INTEGRATION_ADAPTER_FACTORY is required to wire the Integration vault, "
            "immutable Catalog, and bounded connector runtime"
        )
    module_name, separator, attribute = target.partition(":")
    if not separator or not module_name or not attribute:
        raise RuntimeError("AI00_INTEGRATION_ADAPTER_FACTORY must use module:factory syntax")
    try:
        factory = getattr(importlib.import_module(module_name), attribute)
    except (ImportError, AttributeError) as exc:
        raise RuntimeError("AI00_INTEGRATION_ADAPTER_FACTORY could not be loaded") from exc
    if not callable(factory):
        raise RuntimeError("AI00_INTEGRATION_ADAPTER_FACTORY must resolve to a callable")
    return factory


def build_application(adapter_factory: AdapterFactory | None = None) -> IntegrationApplication:
    adapters = (adapter_factory or _configured_factory())()
    if not isinstance(adapters, IntegrationProviderAdapters):
        raise RuntimeError("Integration adapter factory returned an invalid composition")
    repository = adapters.repository if adapters.repository is not None else IntegrationRepository()
    required = {
        "repository": repository,
        "credential_enrollment": adapters.credential_enrollment,
        "catalog": adapters.catalog,
        "connector_runtime": adapters.connector_runtime,
    }
    missing = sorted(name for name, value in required.items() if value is None)
    if missing:
        raise RuntimeError("Integration adapter factory omitted required adapters: " + ", ".join(missing))
    method_requirements = {
        "credential_enrollment": (adapters.credential_enrollment, ("consume",)),
        "catalog": (adapters.catalog, ("require_stable",)),
        "connector_runtime": (
            adapters.connector_runtime, ("test", "discover", "source_columns", "preview")
        ),
    }
    invalid = sorted(
        name
        for name, (adapter, methods) in method_requirements.items()
        if any(not callable(getattr(adapter, method, None)) for method in methods)
    )
    if invalid:
        raise RuntimeError("Integration adapter factory returned invalid adapters: " + ", ".join(invalid))
    return IntegrationApplication(
        repository,
        connector_runtime=adapters.connector_runtime,
        credential_enrollment=adapters.credential_enrollment,
        catalog=adapters.catalog,
        operation_identity=adapters.operation_identity,
        network_policy=adapters.network_policy,
    )


__all__ = ["AdapterFactory", "IntegrationProviderAdapters", "build_application"]

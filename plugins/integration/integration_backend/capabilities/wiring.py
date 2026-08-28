"""Fail-closed production composition for the Integration provider."""
from __future__ import annotations

import importlib
import inspect
import os
from dataclasses import asdict, dataclass
from typing import Any, Callable, Mapping

from backend.capability_v2.contracts import ConsumerIdentity
from backend.capability_v2.domain_client import DomainCapabilityClient

from ..application import ImportDispatcher, IntegrationApplication, IntegrationImportWorker, SyncService
from ..infrastructure import IntegrationRepository


@dataclass(frozen=True)
class IntegrationProviderAdapters:
    credential_enrollment: Any
    catalog: Any
    connector_runtime: Any
    repository: Any | None = None
    operation_identity: Any | None = None
    network_policy: Any | None = None
    target_client: DomainCapabilityClient | None = None
    worker_identity_factory: Callable[[Mapping[str, Any]], ConsumerIdentity] | None = None


AdapterFactory = Callable[[], IntegrationProviderAdapters]


def _requires_principal_scope(method: Any) -> bool:
    try:
        parameters = inspect.signature(method).parameters
    except (TypeError, ValueError):
        return False
    return all(
        name in parameters
        and parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
        and parameters[name].default is inspect.Parameter.empty
        for name in ("actor_gid", "team_gid")
    )


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
        "catalog": (adapters.catalog, (
            "project_mapping_targets_for_ontology_objects", "resolve_mapping_target", "require_stable",
            "validate_mapping_target",
        )),
        "connector_runtime": (
            adapters.connector_runtime, ("test", "discover", "source_columns", "preview")
        ),
    }
    invalid = {
        name
        for name, (adapter, methods) in method_requirements.items()
        if any(not callable(getattr(adapter, method, None)) for method in methods)
    }
    if any(
        not inspect.iscoroutinefunction(getattr(adapters.connector_runtime, method, None))
        for method in ("test", "discover", "source_columns", "preview")
    ):
        invalid.add("connector_runtime")
    if any(
        not _requires_principal_scope(getattr(adapters.catalog, method, None))
        for method in (
            "project_mapping_targets_for_ontology_objects", "resolve_mapping_target",
        )
    ):
        invalid.add("catalog")
    if invalid:
        raise RuntimeError("Integration adapter factory returned invalid adapters: " + ", ".join(sorted(invalid)))
    return IntegrationApplication(
        repository,
        connector_runtime=adapters.connector_runtime,
        credential_enrollment=adapters.credential_enrollment,
        catalog=adapters.catalog,
        operation_identity=adapters.operation_identity,
        network_policy=adapters.network_policy,
    )


def build_import_dispatcher(adapter_factory: AdapterFactory | None = None) -> ImportDispatcher:
    adapters = (adapter_factory or _configured_factory())()
    if not isinstance(adapters, IntegrationProviderAdapters):
        raise RuntimeError("Integration adapter factory returned an invalid composition")
    if not isinstance(adapters.target_client, DomainCapabilityClient):
        raise RuntimeError("Integration import dispatcher requires DomainCapabilityClient")
    if not callable(adapters.worker_identity_factory):
        raise RuntimeError("Integration import dispatcher requires a per-run worker identity factory")
    repository = adapters.repository if adapters.repository is not None else IntegrationRepository()
    if adapters.catalog is None or adapters.connector_runtime is None:
        raise RuntimeError("Integration import dispatcher requires Catalog and connector runtime")
    return ImportDispatcher(
        repository,
        adapters.connector_runtime,
        SyncService(adapters.target_client, adapters.catalog),
        adapters.worker_identity_factory,
    )


def register_import_worker_lifecycle(registry, adapter_factory: AdapterFactory | None = None) -> None:
    state: dict[str, Any] = {"last_health": {
        "status": "stopped", "consecutive_errors": 0, "last_error_code": None,
        "retry_delay_seconds": 0.0, "last_poll_at": None, "last_success_at": None,
        "next_retry_at": None,
    }}

    def health() -> Mapping[str, Any]:
        worker = state.get("worker")
        return asdict(worker.health) if worker is not None else dict(state["last_health"])

    def supervise(signal: Mapping[str, Any]) -> None:
        registry.publish_lifecycle_signal("integration.import-worker", signal)

    async def start() -> None:
        worker = IntegrationImportWorker(
            build_import_dispatcher(adapter_factory), supervision_signal=supervise,
        )
        state["worker"] = worker
        await worker.start()

    async def stop() -> None:
        worker = state.pop("worker", None)
        if worker is not None:
            await worker.stop()
            state["last_health"] = asdict(worker.health)

    registry.register_lifecycle("integration.import-worker", start, stop, health=health)


__all__ = ["AdapterFactory", "IntegrationProviderAdapters", "build_application", "build_import_dispatcher", "register_import_worker_lifecycle"]

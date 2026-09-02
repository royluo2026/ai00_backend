"""Capability registry for the next migration slice."""
from __future__ import annotations
import inspect
from collections import deque
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Awaitable, Callable, Mapping
from .models_next import CapabilityContext, CapabilityHandler, CapabilityOutput, CapabilityResult, CapabilitySpec
from .validation_next import validate_payload
from backend.plugin_platform.metrics import record_usage
from .confirmation_next import confirmation_manager
from .audit_next import audit_sink


class CapabilityPermissionError(PermissionError):
    pass

class CapabilityConfirmationError(PermissionError):
    pass

@dataclass(frozen=True)
class RegisteredCapability:
    spec: CapabilitySpec
    handler: CapabilityHandler
    descriptor: Any | None = None

@dataclass(frozen=True)
class ProviderArtifactBinding:
    plugin_id: str
    module: str
    version: str
    artifact_hash: str

class CapabilityRegistry:
    def __init__(self) -> None:
        self._items: dict[tuple[str, int], RegisteredCapability] = {}
        self._provider_artifacts: dict[str, ProviderArtifactBinding] = {}
        self._lifecycles: dict[str, tuple[Callable[[], Awaitable[None]], Callable[[], Awaitable[None]]]] = {}
        self._lifecycle_health: dict[str, Callable[[], Mapping[str, Any]]] = {}
        self._lifecycle_signals: dict[str, deque[dict[str, Any]]] = {}
    def register(self, spec: CapabilitySpec, handler: CapabilityHandler, *, descriptor: Any | None = None) -> None:
        key = (spec.id, spec.version)
        if key in self._items: raise ValueError(f"Capability already registered: {spec.id}@{spec.version}")
        if descriptor is not None and (
            getattr(descriptor, "id", None) != spec.id
            or getattr(descriptor, "major_version", None) != spec.version
            or getattr(descriptor, "owner_domain", None) != spec.owner
        ):
            raise ValueError("native_descriptor_identity_mismatch")
        self._items[key] = RegisteredCapability(spec, handler, descriptor)
    def get(self, capability_id: str, version: int | None = None) -> RegisteredCapability:
        if version is not None:
            item = self._items.get((capability_id, version))
            if item is None: raise KeyError(f"Unknown capability: {capability_id}@{version}")
            return item
        candidates = [item for (cid, _), item in self._items.items() if cid == capability_id]
        if not candidates: raise KeyError(f"Unknown capability: {capability_id}")
        return max(candidates, key=lambda item: item.spec.version)
    def list(self, *, execution: str | None = None, tag: str | None = None, plugin_callable: bool | None = None) -> list[CapabilitySpec]:
        result = [item.spec for item in self._items.values()]
        if execution: result = [spec for spec in result if spec.execution.value == execution]
        if tag: result = [spec for spec in result if tag in spec.tags]
        if plugin_callable is not None: result = [spec for spec in result if spec.plugin_callable is plugin_callable]
        return sorted(result, key=lambda spec: (spec.id, spec.version))
    def snapshot(self) -> tuple[RegisteredCapability, ...]:
        """Return an exact, deterministically ordered provider registration snapshot."""
        return tuple(self._items[key] for key in sorted(self._items))
    def keys(self) -> tuple[tuple[str, int], ...]:
        """Return stable public identities without exposing registry storage."""
        return tuple(sorted(self._items))
    def bind_provider_artifact(self, owner: str, artifact: Any) -> None:
        binding = ProviderArtifactBinding(
            plugin_id=str(artifact.plugin_id),
            module=str(artifact.module),
            version=str(artifact.version),
            artifact_hash=str(artifact.artifact_hash),
        )
        current = self._provider_artifacts.get(owner)
        if current is not None and current != binding:
            raise ValueError(f"Provider artifact already bound for owner: {owner}")
        self._provider_artifacts[owner] = binding
    def provider_artifact(self, owner: str) -> ProviderArtifactBinding | None:
        return self._provider_artifacts.get(owner)
    def register_lifecycle(
        self, name: str, start: Callable[[], Awaitable[None]], stop: Callable[[], Awaitable[None]],
        *, health: Callable[[], Mapping[str, Any]] | None = None,
    ) -> None:
        if name in self._lifecycles:
            raise ValueError(f"Capability lifecycle already registered: {name}")
        self._lifecycles[name] = (start, stop)
        if health is not None:
            self._lifecycle_health[name] = health
        self._lifecycle_signals[name] = deque(maxlen=100)
    def lifecycle_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._lifecycles))
    def lifecycle_health(self, name: str) -> Mapping[str, Any]:
        provider = self._lifecycle_health.get(name)
        if provider is None:
            raise KeyError(f"Lifecycle health is not registered: {name}")
        return MappingProxyType(dict(provider()))
    def publish_lifecycle_signal(self, name: str, signal: Mapping[str, Any]) -> None:
        if name not in self._lifecycles:
            raise KeyError(f"Unknown capability lifecycle: {name}")
        self._lifecycle_signals[name].append(dict(signal))
    def lifecycle_signals(self, name: str) -> tuple[Mapping[str, Any], ...]:
        if name not in self._lifecycles:
            raise KeyError(f"Unknown capability lifecycle: {name}")
        return tuple(MappingProxyType(dict(item)) for item in self._lifecycle_signals[name])
    async def start_lifecycles(self) -> None:
        for name in self.lifecycle_names():
            await self._lifecycles[name][0]()
    async def stop_lifecycles(self) -> None:
        for name in reversed(self.lifecycle_names()):
            await self._lifecycles[name][1]()
    async def invoke(self, capability_id: str, payload: dict[str, Any], context: CapabilityContext, *, version: int | None = None) -> CapabilityResult:
        item = self.get(capability_id, version)
        validate_payload(dict(item.spec.input_schema), payload)
        if item.spec.confirmation != "none":
            if not confirmation_manager.consume(context.confirmation_token or "", item.spec.id, item.spec.version, context.user_gid, payload):
                audit_sink.record(capability_id=item.spec.id, version=item.spec.version, context=context, payload=payload, status="confirmation_rejected", error="invalid_or_expired_confirmation")
                raise CapabilityConfirmationError(f"Confirmation required for {item.spec.id}")
        missing = sorted(set(item.spec.permissions) - set(context.permissions))
        if missing:
            audit_sink.record(capability_id=item.spec.id, version=item.spec.version, context=context, payload=payload, status="permission_denied", error=", ".join(missing))
            raise CapabilityPermissionError(f"Missing permissions for {item.spec.id}: {', '.join(missing)}")
        try:
            value = item.handler(payload, context)
            if inspect.isawaitable(value): value = await value
            evidence = ()
            if isinstance(value, CapabilityOutput):
                evidence = value.evidence
                value = value.data
            validate_payload(dict(item.spec.output_schema), value, label="output")
        except Exception as exc:
            audit_sink.record(capability_id=item.spec.id, version=item.spec.version, context=context, payload=payload, status="failed", error=str(exc))
            record_usage(context, item.spec.id, False)
            raise
        audit_sink.record(capability_id=item.spec.id, version=item.spec.version, context=context, payload=payload, status="succeeded")
        record_usage(context, item.spec.id, True)
        audit = {"source": context.source, "user_gid": context.user_gid, "request_id": context.request_id}
        if getattr(context, "plugin_id", None):
            audit["plugin_id"] = context.plugin_id
            audit["plugin_version"] = getattr(context, "plugin_version", None)
        return CapabilityResult(capability_id=item.spec.id, version=item.spec.version, data=value, evidence=evidence, audit=audit)

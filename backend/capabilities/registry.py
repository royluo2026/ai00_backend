"""In-process capability registry and execution boundary."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

from .models import (
    CapabilityContext,
    CapabilityHandler,
    CapabilityResult,
    CapabilitySpec,
)


@dataclass(frozen=True)
class RegisteredCapability:
    spec: CapabilitySpec
    handler: CapabilityHandler


class CapabilityRegistry:
    def __init__(self) -> None:
        self._items: dict[tuple[str, int], RegisteredCapability] = {}

    def register(self, spec: CapabilitySpec, handler: CapabilityHandler) -> None:
        key = (spec.id, spec.version)
        if key in self._items:
            raise ValueError(f"Capability already registered: {spec.id}@{spec.version}")
        self._items[key] = RegisteredCapability(spec=spec, handler=handler)

    def replace(self, spec: CapabilitySpec, handler: CapabilityHandler) -> None:
        self._items[(spec.id, spec.version)] = RegisteredCapability(spec=spec, handler=handler)

    def get(self, capability_id: str, version: int | None = None) -> RegisteredCapability:
        if version is not None:
            item = self._items.get((capability_id, version))
            if item is None:
                raise KeyError(f"Unknown capability: {capability_id}@{version}")
            return item
        candidates = [item for (cid, _), item in self._items.items() if cid == capability_id]
        if not candidates:
            raise KeyError(f"Unknown capability: {capability_id}")
        return max(candidates, key=lambda item: item.spec.version)

    def list(self, *, execution: str | None = None, tag: str | None = None) -> list[CapabilitySpec]:
        result = [item.spec for item in self._items.values()]
        if execution:
            result = [spec for spec in result if spec.execution.value == execution]
        if tag:
            result = [spec for spec in result if tag in spec.tags]
        return sorted(result, key=lambda spec: (spec.id, spec.version))

    async def invoke(
        self,
        capability_id: str,
        payload: dict[str, Any],
        context: CapabilityContext,
        *,
        version: int | None = None,
    ) -> CapabilityResult:
        item = self.get(capability_id, version)
        value = item.handler(payload, context)
        if inspect.isawaitable(value):
            value = await value
        return CapabilityResult(
            capability_id=item.spec.id,
            version=item.spec.version,
            data=value,
            audit={"source": context.source, "user_gid": context.user_gid},
        )


capability_registry = CapabilityRegistry()


def _register_builtin_capabilities() -> None:
    """Register only deterministic smoke-test capabilities at import time."""

    capability_registry.register(
        CapabilitySpec(
            id="system.echo",
            version=1,
            description="Return the supplied JSON payload; used to verify adapters.",
            permissions=(),
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            tags=("system", "diagnostic"),
        ),
        lambda payload, _context: payload,
    )


_register_builtin_capabilities()

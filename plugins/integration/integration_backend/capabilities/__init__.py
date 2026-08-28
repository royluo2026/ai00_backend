"""Official Integration Provider entry point."""
from __future__ import annotations

from .descriptors import specs
from .provider import descriptor_for
from .wiring import AdapterFactory, build_application


def register_capabilities(registry, *, adapter_factory: AdapterFactory | None = None) -> None:
    application = build_application(adapter_factory)
    for spec in specs():
        capability_id = spec.id

        async def handler(payload, context, *, _capability_id=capability_id):
            return await application.invoke(_capability_id, payload, context)

        governed = spec.model_copy(update={"plugin_callable": True})
        registry.register(governed, handler, descriptor=descriptor_for(governed))


__all__ = ["register_capabilities"]

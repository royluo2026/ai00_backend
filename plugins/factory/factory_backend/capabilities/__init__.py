"""Official Factory Provider entry point."""
from __future__ import annotations

from ..application import FactoryApplication
from ..infrastructure import FactoryRepository
from .descriptors import specs
from .provider import descriptor_for


application = FactoryApplication(FactoryRepository())


def register_capabilities(registry) -> None:
    for spec in specs():
        capability_id = spec.id

        def handler(payload, context, *, _capability_id=capability_id):
            return {"data": application.invoke(_capability_id, payload, context)}

        governed = spec.model_copy(update={"plugin_callable": True})
        registry.register(governed, handler, descriptor=descriptor_for(governed))


__all__ = ["register_capabilities"]


"""Official Factory Provider entry point."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from ..application import FactoryApplication
from ..infrastructure import FactoryRepository
from .descriptors import specs
from .provider import descriptor_for


application = FactoryApplication(FactoryRepository())


def _transport(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _transport(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_transport(item) for item in value]
    return value


def register_capabilities(registry) -> None:
    for spec in specs():
        capability_id = spec.id

        def handler(payload, context, *, _capability_id=capability_id):
            return {"data": _transport(application.invoke(_capability_id, payload, context))}

        governed = spec.model_copy(update={"plugin_callable": True})
        registry.register(governed, handler, descriptor=descriptor_for(governed))


__all__ = ["register_capabilities"]

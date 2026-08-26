"""Reserved exact Integration browser adapter.

Task 3B.3c found no provider-equivalent legacy endpoints.  The dispatch table
therefore remains empty until an owner-reviewed application outcome exists.
"""
from __future__ import annotations

import inspect
from typing import Any, Callable


HANDLERS: dict[str, Callable[..., Any]] = {}


def invoke_atomic(capability_id: str, payload: dict[str, Any], context: object) -> Any:
    handler = HANDLERS[capability_id]
    available = {**payload, "context": context, "user_gid": getattr(context, "user_gid", "")}
    parameters = inspect.signature(handler).parameters
    return handler(**{name: value for name, value in available.items() if name in parameters})


def register_atomic_web_capabilities(_registry: Any) -> None:
    return None


__all__ = ["HANDLERS", "invoke_atomic", "register_atomic_web_capabilities"]

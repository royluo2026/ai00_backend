"""Exact Craft browser outcomes backed by Craft application functions."""
from __future__ import annotations

import inspect
import json
from typing import Any, Callable

from backend.capability_v2.atomic_web_contracts import OUTPUT_SCHEMA, ROUTE_CAPABILITIES
from backend.capability_v2.provider_contracts import CapabilityRisk, CapabilitySpec

from . import contracts
from .provider import descriptor_for
from .rule_library import change_rule_library


def _update_rule(*, gid: str, changes_json: str, context: object) -> Any:
    try:
        changes = json.loads(changes_json)
    except (TypeError, ValueError) as exc:
        raise ValueError("changes_json must be valid JSON") from exc
    if not isinstance(changes, dict) or not changes or len(changes) > 30:
        raise ValueError("changes_json must encode a non-empty bounded object")
    output = change_rule_library({"operation": "update", "gid": gid, "record": changes}, context)
    return output.data


HANDLERS: dict[str, Callable[..., Any]] = {"craft.rule.definition.update": _update_rule}


def invoke_atomic(capability_id: str, payload: dict[str, Any], context: object) -> Any:
    handler = HANDLERS[capability_id]
    available = {**payload, "user_gid": getattr(context, "user_gid", ""), "context": context}
    parameters = inspect.signature(handler).parameters
    return handler(**{name: value for name, value in available.items() if name in parameters})


def register_atomic_web_capabilities(registry: Any) -> None:
    definition = next(value for value in ROUTE_CAPABILITIES.values() if value["id"] == "craft.rule.definition.update")
    contracts.INPUT_SCHEMAS[definition["id"]] = definition["schema"]
    contracts.OUTPUT_SCHEMAS[definition["id"]] = OUTPUT_SCHEMA
    spec = CapabilitySpec(
        id=definition["id"], owner="craft", description="Update one mutable Craft rule definition.",
        use_when="A browser consumer changes bounded fields on one mutable rule definition.",
        do_not_use_when="The request changes an immutable rule release or waiver.",
        risk=CapabilityRisk.WRITE, confirmation="user", idempotent=True,
        permissions=("craft.rule.write",), input_schema=definition["schema"], output_schema=OUTPUT_SCHEMA,
        tags=("craft", "rule", "atomic", "web"),
    )
    registry.register(spec, lambda payload, context: {"result_json": json.dumps(invoke_atomic(spec.id, payload, context), ensure_ascii=False, default=str)}, descriptor=descriptor_for(spec))


__all__ = ["HANDLERS", "invoke_atomic", "register_atomic_web_capabilities"]

"""Convert Provider specifications into closed Capability V2 descriptors."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from backend.capabilities.models_next import CapabilityExecution, CapabilityRisk, CapabilitySpec
from .contracts import AutomationLevel, CapabilityDescriptorV2, ExecutionBudget, ExecutionMode, ExposurePolicy, SideEffectLevel

_OWNER_ALIASES = {"plugin": "base", "runtime": "device", "vismockup": "device"}


def _closed_schema(
    value: Mapping[str, Any] | None,
) -> dict[str, Any]:
    schema = dict(value or {})
    if not schema:
        schema = {"type": "object", "properties": {}}
    properties = schema.get("properties")
    if isinstance(properties, Mapping):
        schema["properties"] = {
            name: _closed_schema(child) if isinstance(child, Mapping) else child
            for name, child in properties.items()
        }
    items = schema.get("items")
    if isinstance(items, Mapping):
        schema["items"] = _closed_schema(items)
    if schema.get("type") == "object":
        schema.setdefault("properties", {})
        for name in schema.get("required") or ():
            schema["properties"].setdefault(name, {})
        schema["additionalProperties"] = False
    return schema


def _schema_hash(input_schema: Mapping[str, Any], output_schema: Mapping[str, Any]) -> str:
    encoded = json.dumps({"input": input_schema, "output": output_schema}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def descriptor_from_provider_spec(spec: CapabilitySpec) -> CapabilityDescriptorV2:
    input_schema = _closed_schema(spec.input_schema)
    output_schema = _closed_schema(spec.output_schema)
    is_read = spec.risk is CapabilityRisk.READ
    execution_mode = ExecutionMode.LOCAL if spec.execution is CapabilityExecution.LOCAL else ExecutionMode.CLOUD_SYNC
    description = spec.description.strip() or f"Capability {spec.id}."
    permissions = ",".join(spec.permissions) or "authenticated"
    execution_budget = ExecutionBudget.model_validate(
        spec.execution_budget.model_dump(mode="json") if spec.execution_budget is not None else {}
    )
    return CapabilityDescriptorV2(
        id=spec.id, major_version=spec.version, owner_domain=_OWNER_ALIASES.get(spec.owner, spec.owner),
        lifecycle_status="experimental", title=spec.id, description=description,
        use_when=spec.use_when.strip() or description,
        do_not_use_when=spec.do_not_use_when.strip() or "Use the owning domain's governed Capability.",
        side_effect_level=SideEffectLevel(spec.risk.value), execution_mode=execution_mode,
        exposure=ExposurePolicy(web=True, api=True, plugin=bool(is_read and spec.plugin_callable),
            agent=bool(is_read and execution_mode is not ExecutionMode.LOCAL), mcp=bool(is_read and execution_mode is not ExecutionMode.LOCAL)),
        automation_level=AutomationLevel.A2 if is_read and spec.confirmation == "none" else AutomationLevel.A1,
        authorization_policy=f"legacy:{permissions}", input_schema=input_schema, output_schema=output_schema,
        agent_output_schema=output_schema if is_read and execution_mode is not ExecutionMode.LOCAL else None,
        schema_hash=_schema_hash(input_schema, output_schema),
        operation_policy="required" if execution_mode is ExecutionMode.LOCAL else "none",
        execution_budget=execution_budget,
        idempotency_policy="optional" if not is_read and spec.idempotent else "none",
        confirmation_policy=spec.confirmation,
        audit_policy="high_risk" if spec.risk is CapabilityRisk.DESTRUCTIVE else "standard",
    )


__all__ = ["descriptor_from_provider_spec"]

"""Native Capability V2 policy boundary owned by Local Integration."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.contracts import AutomationLevel, DomainErrorContract, ExecutionMode, ExposurePolicy, LifecycleStatus, ResourceSelector, SideEffectLevel
from backend.capability_v2.v1_adapter import adapt_v1_spec

from .contracts import INPUT_SCHEMAS, OUTPUT_SCHEMAS


_ERRORS = tuple(DomainErrorContract(code=code, meaning=meaning, retryable=retryable) for code, meaning, retryable in (
    ("device_not_found", "The workstation is unavailable or is not owned by the caller.", False),
    ("device_capability_unavailable", "The workstation does not advertise the requested capability.", True),
    ("local_operation_signing_key_unavailable", "The server cannot sign a local operation.", True),
    ("local_operation_failed", "The workstation returned a sanitized local execution error.", False),
    ("local_operation_outcome_unknown", "Execution may have occurred and must be reconciled before retry.", True),
))


def governed_spec(spec: Any) -> Any:
    return spec.model_copy(update={"plugin_callable": True, "input_schema": INPUT_SCHEMAS[spec.id], "output_schema": OUTPUT_SCHEMAS[spec.id]})


def descriptor_for(spec: Any):
    governed = governed_spec(spec)
    descriptor = adapt_v1_spec(governed)
    is_local = governed.id != "local.command.get"
    is_write = descriptor.side_effect_level is not SideEffectLevel.READ
    selectors = [ResourceSelector(resource_type="device", payload_path="device_id")] if is_local else [ResourceSelector(resource_type="local-operation", payload_path="command_id")]
    if governed.id == "vismockup.model.open":
        selectors.append(ResourceSelector(resource_type="artifact", payload_path="artifact_ref.artifact_id"))
    return descriptor.model_copy(update={
        "lifecycle_status": LifecycleStatus.STABLE,
        "exposure": ExposurePolicy(web=True, api=True, plugin=True, agent=True, mcp=True, local_runtime=is_local),
        "automation_level": AutomationLevel.A1 if is_write else AutomationLevel.A2,
        "authorization_policy": "local-integration.v2:agent.run",
        "resource_selectors": tuple(selectors), "data_classification": "confidential",
        "delegation_policy": "scoped", "agent_output_schema": descriptor.output_schema,
        "execution_mode": ExecutionMode.LOCAL if is_local else ExecutionMode.CLOUD_SYNC,
        "artifact_policy": "input" if governed.id == "vismockup.model.open" else ("output" if governed.id == "vismockup.capture" else "none"),
        "operation_policy": "required" if is_local else "none",
        "concurrency_policy": "none", "idempotency_policy": ("required" if is_write else "optional") if is_local else "none",
        "consistency_policy": "external" if is_local else "strong", "evidence_policy": "required",
        "domain_errors": _ERRORS, "domain_errors_complete": True,
    })


def register(registry: Any, spec: Any, handler: Any) -> None:
    governed = governed_spec(spec)
    registry.register(governed, handler, descriptor=descriptor_for(governed))


__all__ = ["descriptor_for", "register"]

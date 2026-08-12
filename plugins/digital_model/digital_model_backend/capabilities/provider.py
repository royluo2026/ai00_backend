"""Native Capability V2 registration boundary owned by Digital Model."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.contracts import (
    AutomationLevel, CapabilityDescriptorV2, DomainErrorContract, ExposurePolicy,
    LifecycleStatus, ResourceSelector, SideEffectLevel,
)
from backend.capability_v2.v1_adapter import adapt_v1_spec

from .contracts import INPUT_SCHEMAS, OUTPUT_SCHEMAS


_RESOURCES = {
    "digital_model.model.create": (("project", "project_ref"),),
    "digital_model.model.get": (("digital-model", "model_id"),),
    "digital_model.version.create": (("digital-model", "model_id"),),
    "digital_model.version.get": (("digital-model", "model_id"), ("digital-model-version", "version_id")),
    "digital_model.version.search": (("digital-model", "model_id"),),
    "digital_model.version.compare": (("digital-model", "model_id"), ("digital-model-version", "from_version_id"), ("digital-model-version", "to_version_id")),
    "digital_model.component.search": (("digital-model", "model_id"), ("digital-model-version", "version_id")),
}
_ERRORS = tuple(DomainErrorContract(code=code, meaning=meaning) for code, meaning in (
    ("model_not_found", "The Digital Model identity does not exist or is not visible."),
    ("snapshot_not_found", "The immutable Digital Model snapshot does not exist or is not visible."),
    ("version_conflict", "The Digital Model head differs from the expected version."),
    ("artifact_not_found", "The geometry artifact is unavailable or does not match its digest."),
    ("component_not_found", "A referenced component does not exist in the selected snapshot."),
    ("idempotency_conflict", "The idempotency key is already bound to another Digital Model request."),
))


def governed_spec(spec: Any) -> Any:
    return spec.model_copy(update={
        "plugin_callable": True,
        "input_schema": INPUT_SCHEMAS[spec.id],
        "output_schema": OUTPUT_SCHEMAS[spec.id],
    })


def descriptor_for(spec: Any) -> CapabilityDescriptorV2:
    governed = governed_spec(spec)
    descriptor = adapt_v1_spec(governed)
    is_write = descriptor.side_effect_level is not SideEffectLevel.READ
    expected_version = governed.id == "digital_model.version.create"
    updates = {
        "lifecycle_status": LifecycleStatus.STABLE,
        "exposure": ExposurePolicy(web=True, api=True, plugin=True, agent=True, mcp=True),
        "automation_level": AutomationLevel.A1 if is_write else AutomationLevel.A2,
        "authorization_policy": "digital_model.v2:" + ",".join(governed.permissions),
        "resource_selectors": tuple(
            ResourceSelector(resource_type=resource_type, payload_path=payload_path)
            for resource_type, payload_path in _RESOURCES.get(governed.id, ())
        ),
        "data_classification": "confidential",
        "delegation_policy": "scoped",
        "agent_output_schema": descriptor.output_schema,
        "artifact_policy": "input" if governed.id == "digital_model.version.create" else "none",
        "operation_policy": "optional" if is_write else "none",
        "concurrency_policy": "expected_version" if expected_version else "none",
        "expected_version_payload_path": "expected_head_version_id" if expected_version else None,
        "idempotency_policy": "required" if is_write else "none",
        "consistency_policy": "external" if is_write else "strong",
        "evidence_policy": "required" if governed.id in {"digital_model.version.create", "digital_model.version.get"} else "optional",
        "domain_errors": _ERRORS,
        "domain_errors_complete": True,
    }
    return CapabilityDescriptorV2.model_validate({**descriptor.model_dump(), **updates})


def register(registry: Any, spec: Any, handler: Any) -> None:
    governed = governed_spec(spec)
    registry.register(governed, handler, descriptor=descriptor_for(governed))


__all__ = ["descriptor_for", "register"]

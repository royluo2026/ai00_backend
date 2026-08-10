"""Native Capability V2 policy boundary owned by Simulation."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.contracts import AutomationLevel, CapabilityDescriptorV2, DomainErrorContract, ExecutionMode, ExposurePolicy, LifecycleStatus, ResourceSelector, SideEffectLevel
from backend.capability_v2.v1_adapter import adapt_v1_spec

from .contracts import INPUT_SCHEMAS, OUTPUT_SCHEMAS


_RESOURCES = {
    "simulation.parameter_set.get": (("simulation-parameter-set", "parameter_set_ref.parameter_set_id"),),
    "simulation.profile.get": (("simulation-profile", "simulation_profile_ref.profile_id"),),
    "simulation.environment.create": (
        ("craft-bop-version", "execution_plan_ref.version_gid"),
        ("digital-model", "model_snapshot_ref.model_id"),
        ("digital-model-version", "model_snapshot_ref.version_id"),
        ("simulation-parameter-set", "parameter_set_ref.parameter_set_id"),
        ("simulation-profile", "simulation_profile_ref.profile_id"),
    ),
    "simulation.environment.get": (("simulation-environment", "environment_id"),),
    "simulation.run.start": (("simulation-environment", "environment_id"),),
    "simulation.run.get": (("simulation-run", "run_id"),),
    "simulation.result.get": (("simulation-run", "run_id"),),
}
_ERRORS = tuple(DomainErrorContract(
    code=code, meaning=meaning,
    retryable=code in {"source_resolver_unavailable", "simulation_result_not_ready"},
) for code, meaning in (
    ("source_resolver_unavailable", "A required owning-domain resolver is unavailable."),
    ("source_version_mismatch", "A referenced source no longer matches its immutable hash or version."),
    ("parameter_set_not_found", "The immutable parameter set is unavailable or not visible."),
    ("simulation_profile_not_found", "The immutable Simulation profile is unavailable or not visible."),
    ("simulation_environment_not_found", "The Simulation environment is unavailable or not visible."),
    ("simulation_run_not_found", "The Simulation run is unavailable or not visible."),
    ("simulation_result_not_ready", "The Simulation run has no completed result artifacts."),
    ("idempotency_conflict", "The idempotency key is bound to a different Simulation request."),
))


def governed_spec(spec: Any) -> Any:
    return spec.model_copy(update={"plugin_callable": True, "input_schema": INPUT_SCHEMAS[spec.id], "output_schema": OUTPUT_SCHEMAS[spec.id]})


def descriptor_for(spec: Any) -> CapabilityDescriptorV2:
    governed = governed_spec(spec)
    descriptor = adapt_v1_spec(governed)
    is_write = descriptor.side_effect_level is not SideEffectLevel.READ
    updates = {
        "lifecycle_status": LifecycleStatus.STABLE,
        "exposure": ExposurePolicy(web=True, api=True, plugin=True, agent=True, mcp=True),
        "automation_level": AutomationLevel.A1 if is_write else AutomationLevel.A2,
        "authorization_policy": "simulation.v2:" + ",".join(governed.permissions),
        "resource_selectors": tuple(ResourceSelector(resource_type=t, payload_path=p) for t, p in _RESOURCES.get(governed.id, ())),
        "data_classification": "confidential", "delegation_policy": "scoped",
        "agent_output_schema": descriptor.output_schema,
        "execution_mode": ExecutionMode.CLOUD_ASYNC if governed.id == "simulation.run.start" else descriptor.execution_mode,
        "artifact_policy": "output" if governed.id == "simulation.result.get" else "none",
        "operation_policy": "required" if governed.id == "simulation.run.start" else ("optional" if is_write else "none"),
        "concurrency_policy": "none", "idempotency_policy": "required" if is_write else "none",
        "consistency_policy": "external" if is_write else "strong", "evidence_policy": "required",
        "domain_errors": _ERRORS, "domain_errors_complete": True,
    }
    return CapabilityDescriptorV2.model_validate({**descriptor.model_dump(), **updates})


def register(registry: Any, spec: Any, handler: Any) -> None:
    governed = governed_spec(spec)
    registry.register(governed, handler, descriptor=descriptor_for(governed))


__all__ = ["descriptor_for", "register"]

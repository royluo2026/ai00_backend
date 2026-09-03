from __future__ import annotations

from backend.capability_v2.contracts import AutomationLevel, CapabilityDescriptorV2, DomainErrorContract, ExecutionMode, ExposurePolicy, LifecycleStatus, SideEffectLevel
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec


ERRORS = tuple(DomainErrorContract(code=code, meaning=meaning, retryable=retryable) for code, meaning, retryable in (
    ("invalid_input", "The Agent request is invalid.", False),
    ("permission_denied", "The caller cannot access the Agent resource.", False),
    ("resource_not_found", "The Agent resource does not exist.", False),
    ("version_conflict", "The Agent resource changed concurrently.", False),
    ("catalog_release_unavailable", "The pinned Catalog release is unavailable.", True),
    ("delegation_expired", "The Agent delegation is missing or expired.", False),
    ("approval_required", "The delegated operation requires Base approval.", False),
    ("provider_unavailable", "The Agent canvas runtime adapter is unavailable.", True),
    ("runtime_timeout", "The bounded Agent canvas runtime timed out.", True),
    ("idempotency_conflict", "The Agent canvas invocation conflicts with an earlier request.", False),
    ("outcome_unknown", "The Agent canvas outcome must be reconciled.", True),
))

_CANVAS_COMMANDS = {"agent.canvas.execution.start", "agent.canvas.execution.resume"}
_CANVAS_SYNC = {"agent.workflow.node.test.execute", "agent.canvas.options.resolve"}
_MODEL_HIDDEN = {
    "agent.runtime.config.read",
}


def descriptor_for(spec) -> CapabilityDescriptorV2:
    base = descriptor_from_provider_spec(spec); write = base.side_effect_level is not SideEffectLevel.READ
    interaction = spec.id in {"agent.interaction.request", "agent.script.generate", *_CANVAS_COMMANDS}
    return CapabilityDescriptorV2.model_validate({
        **base.model_dump(), "owner_domain": "agent", "lifecycle_status": LifecycleStatus.STABLE,
        "exposure": ExposurePolicy(
            web=True, api=True, plugin=True,
            agent=spec.id not in _MODEL_HIDDEN,
            mcp=spec.id not in _MODEL_HIDDEN,
        ),
        "exposure_policy_source": "provider_explicit",
        "automation_level": AutomationLevel.A1 if write else AutomationLevel.A2,
        "authorization_policy": "agent.v2:" + ",".join(spec.permissions),
        "data_classification": "confidential", "delegation_policy": "scoped",
        "agent_output_schema": base.output_schema,
        "execution_mode": ExecutionMode.CLOUD_ASYNC if interaction else base.execution_mode,
        "operation_policy": "required" if interaction else ("optional" if write and spec.id not in _CANVAS_SYNC else "none"),
        "idempotency_policy": "required" if write else "none",
        "consistency_policy": "strong",
        "evidence_policy": "required" if write else "optional",
        "domain_errors": ERRORS, "domain_errors_complete": True,
    })

__all__ = ["descriptor_for"]

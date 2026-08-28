from __future__ import annotations

from backend.capability_v2.contracts import AutomationLevel, CapabilityDescriptorV2, DomainErrorContract, ExecutionMode, ExposurePolicy, LifecycleStatus, SideEffectLevel
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec


ERRORS = tuple(DomainErrorContract(code=code, meaning=meaning, retryable=retryable) for code, meaning, retryable in (
    ("invalid_input", "The Integration request is invalid.", False),
    ("permission_denied", "The caller cannot access the Integration resource.", False),
    ("resource_not_found", "The connector or mapping does not exist.", False),
    ("version_conflict", "The connector or mapping revision changed concurrently.", False),
    ("network_policy_rejected", "The connector target violates outbound network policy.", False),
    ("connector_runtime_unavailable", "The bounded external connector runtime is unavailable.", True),
    ("target_capability_unavailable", "The owning target-domain Capability is unavailable.", True),
    ("target_binding_unavailable", "The selected presentation object has no governed Integration target binding.", False),
    ("target_binding_incompatible", "The governed Integration target binding is incompatible.", False),
    ("credential_enrollment_unavailable", "The credential enrollment vault is unavailable.", True),
    ("credential_enrollment_invalid", "The one-time credential enrollment handle is invalid or consumed.", False),
    ("idempotency_conflict", "The Integration idempotency key is already bound to another request.", False),
))


_IDEMPOTENT_WRITES = {
    "integration.connector.create",
    "integration.connector.update",
    "integration.mapping.create",
    "integration.field_mapping.batch.update",
    "integration.mapping.import.start",
    "integration.mapping_target.upsert",
}

_DURABLE_OPERATIONS = {
    "integration.connector.schema.discover",
    "integration.mapping.source_columns.discover",
    "integration.mapping.preview",
    "integration.mapping.import.start",
    "integration.sync.start",
    *_IDEMPOTENT_WRITES,
}


def descriptor_for(spec) -> CapabilityDescriptorV2:
    base = descriptor_from_provider_spec(spec)
    write = base.side_effect_level is not SideEffectLevel.READ
    async_sync = spec.id in {"integration.mapping.import.start", "integration.sync.start"}
    external = spec.id in {
        "integration.connector.connection.test", "integration.connector.schema.discover",
        "integration.mapping.source_columns.discover", "integration.mapping.preview",
        "integration.mapping.import.start", "integration.sync.start",
    }
    return CapabilityDescriptorV2.model_validate({
        **base.model_dump(), "owner_domain": "integration",
        "lifecycle_status": LifecycleStatus.STABLE,
        "exposure": ExposurePolicy(web=True, api=True, plugin=True, agent=True, mcp=True),
        "exposure_policy_source": "provider_explicit",
        "automation_level": AutomationLevel.A1 if write else AutomationLevel.A2,
        "authorization_policy": "integration.v2:" + ",".join(spec.permissions),
        "data_classification": "confidential", "delegation_policy": "scoped",
        "agent_output_schema": base.output_schema,
        "execution_mode": ExecutionMode.CLOUD_ASYNC if async_sync else base.execution_mode,
        "operation_policy": "required" if spec.id in _DURABLE_OPERATIONS else "none",
        "idempotency_policy": "required" if write else "none",
        "replay_data_policy": (
            "projected" if spec.id == "integration.connector.connection.test" else "metadata_only"
        ),
        "consistency_policy": "external" if external else "strong",
        "evidence_policy": "required", "domain_errors": ERRORS, "domain_errors_complete": True,
    })

__all__ = ["descriptor_for"]

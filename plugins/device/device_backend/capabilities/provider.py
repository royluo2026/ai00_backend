"""Native Capability V2 policy boundary owned by Local Runtime."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.contracts import AutomationLevel, BusinessInvariantContract, DomainErrorContract, ExecutionMode, ExposurePolicy, LifecycleStatus, ResourceSelector, SideEffectLevel
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec

from .contracts import INPUT_SCHEMAS, OUTPUT_SCHEMAS

DEPRECATED_LOCAL_DEVICE_CAPABILITIES = frozenset({
    "local.device.change.apply", "local.device.read",
})


_ERRORS = tuple(DomainErrorContract(code=code, meaning=meaning, retryable=retryable) for code, meaning, retryable in (
    ("device_not_found", "The workstation is unavailable or is not owned by the caller.", False),
    ("device_capability_unavailable", "The workstation does not advertise the requested capability.", True),
    ("local_operation_signing_key_unavailable", "The server cannot sign a local operation.", True),
    ("local_operation_failed", "The workstation returned a sanitized local execution error.", False),
    ("local_operation_outcome_unknown", "Execution may have occurred and must be reconciled before retry.", True),
    ("provider_unavailable", "The Local Runtime application provider is unavailable.", True),
))


def governed_spec(spec: Any) -> Any:
    return spec.model_copy(update={"plugin_callable": True, "input_schema": INPUT_SCHEMAS[spec.id], "output_schema": OUTPUT_SCHEMAS[spec.id]})


def descriptor_for(spec: Any):
    governed = governed_spec(spec)
    descriptor = descriptor_from_provider_spec(governed)
    is_local = governed.id.startswith("vismockup.")
    is_write = descriptor.side_effect_level is not SideEffectLevel.READ
    selectors = [ResourceSelector(resource_type="device", payload_path="device_id")] if (is_local or governed.id == "device.connector.health.get") else ([ResourceSelector(resource_type="local-operation", payload_path="command_id")] if governed.id == "local.command.get" else [])
    if governed.id == "device.connector.plan.queue":
        selectors.append(ResourceSelector(resource_type="device", payload_path="plan.device_id"))
    if governed.id == "vismockup.model.open":
        selectors.append(ResourceSelector(resource_type="artifact", payload_path="artifact_ref.artifact_id"))
    updates = {
        "lifecycle_status": (
            LifecycleStatus.DEPRECATED
            if governed.id in DEPRECATED_LOCAL_DEVICE_CAPABILITIES
            else LifecycleStatus.STABLE
        ),
        "deprecation_message": (
            "Legacy device lifecycle identity retained for compatibility; no "
            "bound Local Runtime application outcome is currently registered."
            if governed.id in DEPRECATED_LOCAL_DEVICE_CAPABILITIES else None
        ),
        "exposure": ExposurePolicy(web=True, api=True, plugin=True, agent=True, mcp=True, local_runtime=is_local),
        "exposure_policy_source": "provider_explicit",
        "automation_level": AutomationLevel.A1 if is_write else AutomationLevel.A2,
        "authorization_policy": "local-runtime.v2:agent.run",
        "resource_selectors": tuple(selectors), "data_classification": "confidential",
        "delegation_policy": "scoped", "agent_output_schema": descriptor.output_schema,
        "execution_mode": ExecutionMode.LOCAL if is_local else ExecutionMode.CLOUD_SYNC,
        "artifact_policy": "input" if governed.id == "vismockup.model.open" else ("output" if governed.id == "vismockup.capture" else "none"),
        "operation_policy": "required" if is_local else ("optional" if is_write else "none"),
        "concurrency_policy": "none", "idempotency_policy": "required" if is_write else ("optional" if is_local else "none"),
        "consistency_policy": "external" if is_local else "strong", "evidence_policy": "required",
        "domain_errors": _ERRORS, "domain_errors_complete": True,
    }
    if governed.id == "device.connector.health.get":
        updates.update({
            "business_effect": "Return the authenticated workstation's bounded AI00 Connector, user-session, adapter and target-application health projection.",
            "business_acceptance_criteria": (
                "Health is returned only for the caller-owned device identity.",
                "The projection identifies the bound user, interactive session and advertised Adapter contracts.",
                "Reading health does not queue or execute local application work.",
            ),
            "business_invariants": (),
            "no_business_invariant_reason": "This read reports already-recorded, caller-scoped Connector health and does not decide or mutate domain state.",
        })
    elif governed.id == "device.connector.plan.queue":
        updates.update({
            "business_effect": "Authenticate, validate and durably queue one exact signed execution plan for the bound user's AI00 Connector.",
            "business_acceptance_criteria": (
                "The plan targets one caller-owned device and its bound user.",
                "The queued payload retains the exact protocol, Adapter operation contracts and idempotency identity.",
                "Rejected plans do not create executable local work.",
            ),
            "business_invariants": (
                BusinessInvariantContract(
                    rule_id="device.connector.plan.bound_identity", version=1,
                    statement="A Connector plan is queued only for the authenticated device and its single bound AI00 user.",
                    applies_when="a local Connector execution plan is queued",
                    enforcement_ref="plugins/device/device_backend/capabilities/connector_runtime.py:ConnectorControlPlane.queue_plan",
                    error_code="device_not_found",
                    test_refs=("backend/tests/test_connector_runtime_control_plane.py::test_queue_checks_protocol_adapter_operation_and_contract_hash",),
                ),
            ),
            "no_business_invariant_reason": None,
        })
    return descriptor.model_copy(update=updates)


def register(registry: Any, spec: Any, handler: Any) -> None:
    governed = governed_spec(spec)
    registry.register(governed, handler, descriptor=descriptor_for(governed))


__all__ = ["DEPRECATED_LOCAL_DEVICE_CAPABILITIES", "descriptor_for", "register"]

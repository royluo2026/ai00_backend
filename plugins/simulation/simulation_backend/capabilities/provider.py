"""Native Capability V2 policy boundary owned by Simulation."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.contracts import AutomationLevel, BusinessInvariantContract, CapabilityDescriptorV2, DomainErrorContract, ExecutionMode, ExposurePolicy, LifecycleStatus, ResourceSelector, SideEffectLevel
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec
from backend.capability_v2.business_definition import business_definition_hash

from .contracts import INPUT_SCHEMAS, OUTPUT_SCHEMAS


_RESOURCES = {
    "simulation.parameter_set.get": (("simulation-parameter-set", "parameter_set_ref.parameter_set_id"),),
    "simulation.solver_profile.get": (("simulation-profile", "simulation_profile_ref.profile_id"),),
    "simulation.environment.create": (
        ("craft-bop-version", "execution_plan_ref.version_gid"),
        ("digital-model", "model_snapshot_ref.model_id"),
        ("digital-model-version", "model_snapshot_ref.version_id"),
        ("simulation-parameter-set", "parameter_set_ref.parameter_set_id"),
        ("simulation-profile", "simulation_profile_ref.profile_id"),
    ),
    "simulation.environment.get": (("simulation-environment", "environment_id"),),
    "simulation.environment.archive": (("simulation-environment", "environment_id"),),
    "simulation.environment.compose": (
        ("craft-bop-version", "execution_plan_ref.version_gid"),
        ("device", "device_id"),
    ),
    "simulation.document_snapshot.request": (("device", "device_id"),),
    "simulation.document_snapshot.get": (("simulation-document-snapshot", "snapshot_request_id"),),
    "simulation.environment.manifest.get": (("simulation-environment", "environment_id"),),
    "simulation.environment.manifest.archive": (("simulation-environment", "environment_id"),),
    "simulation.environment.preflight": (
        ("simulation-environment", "environment_id"), ("device", "device_id"),
    ),
    "simulation.environment.materialize": (
        ("simulation-environment", "environment_id"), ("device", "device_id"),
    ),
    "simulation.capture_run.start": (
        ("simulation-environment", "environment_id"), ("device", "device_id"),
    ),
    "simulation.capture_run.get": (("simulation-capture-run", "capture_run_id"),),
    "simulation.capture_run.cancel": (("simulation-capture-run", "capture_run_id"),),
    "simulation.capture_step.retry": (("simulation-capture-run", "capture_run_id"),),
    "simulation.run.start": (("simulation-environment", "environment_id"),),
    "simulation.run.get": (("simulation-run", "run_id"),),
    "simulation.result.get": (("simulation-run", "run_id"),),
    "simulation.result.compare": (("simulation-run", "left_result_ref.run_id"), ("simulation-run", "right_result_ref.run_id")),
}
_ERROR_PAIRS = (
    ("source_resolver_unavailable", "A required owning-domain resolver is unavailable."),
    ("source_version_mismatch", "A referenced source no longer matches its immutable hash or version."),
    ("parameter_set_not_found", "The immutable parameter set is unavailable or not visible."),
    ("simulation_profile_not_found", "The immutable Simulation profile is unavailable or not visible."),
    ("solver_not_allowed", "The requested solver coordinate is not in the governed allowlist."),
    ("simulation_environment_not_found", "The Simulation environment is unavailable or not visible."),
    ("simulation_run_not_found", "The Simulation run is unavailable or not visible."),
    ("simulation_result_not_ready", "The Simulation run has no completed result artifacts."),
    ("idempotency_conflict", "The idempotency key is bound to a different Simulation request."),
    ("execution_plan_unavailable", "The pinned Craft execution plan is unavailable."),
    ("active_document_unavailable", "The Connector has no readable active document."),
    ("active_document_snapshot_required", "A confirmed asynchronous active-document snapshot is required."),
    ("document_snapshot_not_found", "The document snapshot request is unavailable or not visible."),
    ("bom_snapshot_invalid", "The Connector returned an invalid active BOM snapshot."),
    ("bom_identity_mismatch", "The active BOM identity does not match the requested source."),
    ("bom_snapshot_limit_exceeded", "The active BOM exceeds the governed snapshot limit."),
    ("product_binding_not_found", "A process product reference has no active BOM node."),
    ("product_binding_ambiguous", "A process product reference resolves to multiple BOM nodes."),
    ("resource_model_not_found", "A typed resource code has no model mapping."),
    ("resource_model_ambiguous", "A typed resource code has multiple active model mappings."),
    ("environment_source_changed", "A pinned environment source changed before composition."),
    ("connector_offline", "The bound Connector is offline or stale."),
    ("connector_version_incompatible", "The Connector protocol or target product version is incompatible."),
    ("adapter_unavailable", "The required Connector Adapter is unavailable."),
    ("adapter_contract_mismatch", "An Adapter operation contract hash does not match."),
    ("interactive_session_missing", "The bound user's interactive SessionHost is unavailable."),
    ("interactive_session_conflict", "More than one fresh SessionHost claims the bound user."),
    ("bound_user_mismatch", "The Connector is bound to a different AI00 user."),
    ("vismockup_unavailable", "VisMockup is unavailable to the bound SessionHost."),
    ("vismockup_document_changed", "The active VisMockup document changed during execution."),
    ("scene_verification_failed", "The actual VisMockup scene does not match the manifest."),
    ("capture_failed", "VisMockup internal view capture failed."),
    ("artifact_upload_unconfirmed", "A captured Artifact upload has not been reconciled."),
    ("craft_screenshot_attach_failed", "Craft rejected or failed the screenshot association."),
    ("local_execution_outcome_unknown", "The local side effect outcome requires reconciliation."),
)
_LEGACY_ERROR_CODES = frozenset(code for code, _ in _ERROR_PAIRS[:9])
_RETRYABLE_ERROR_CODES = frozenset({
    "source_resolver_unavailable", "simulation_result_not_ready",
    "execution_plan_unavailable", "active_document_unavailable",
    "connector_offline", "interactive_session_missing", "vismockup_unavailable",
    "capture_failed", "artifact_upload_unconfirmed", "craft_screenshot_attach_failed",
})

_CONNECTOR_BUSINESS_EFFECTS = {
    "simulation.document_snapshot.request": "Queue one bounded immutable snapshot of the bound user's currently active VisMockup BOM for later environment composition.",
    "simulation.document_snapshot.get": "Return authoritative status and the immutable confirmed BOM snapshot for one caller-visible request.",
    "simulation.environment.compose": "Create one immutable, reproducible simulation-environment manifest from the selected process version, active VisMockup BOM and governed resource-model mappings.",
    "simulation.environment.manifest.get": "Return one caller-visible immutable simulation-environment manifest with its exact source and Connector contract pins.",
    "simulation.environment.manifest.search": "Return a bounded caller-visible list of simulation-environment manifests for reuse and audit.",
    "simulation.environment.manifest.archive": "Archive a simulation-environment identity while retaining every immutable manifest and execution record for audit.",
    "simulation.environment.preflight": "Report every known incompatibility between an immutable environment manifest and the bound AI00 Connector session without starting local work.",
    "simulation.environment.materialize": "Queue construction and verification of the exact immutable simulation environment in the bound user's VisMockup session.",
    "simulation.capture_run.start": "Queue VisMockup-internal screenshots in reverse process order for an exact environment manifest and attach confirmed artifacts to their Craft operations.",
    "simulation.capture_run.get": "Return authoritative capture-run, step and artifact-association progress for the caller-visible run.",
    "simulation.capture_run.cancel": "Cancel only capture work that has not started while preserving active and completed outcomes for reconciliation.",
    "simulation.capture_step.retry": "Create a new attempt for one proven-failed capture step without replaying successful or outcome-unknown local effects.",
}

_CONNECTOR_READ_REASON = (
    "This capability returns a bounded projection or compatibility diagnosis and does not decide or mutate domain state."
)

_CONNECTOR_BUSINESS_INVARIANTS = {
    "simulation.document_snapshot.request": (
        BusinessInvariantContract(
            rule_id="simulation.document_snapshot.confirmed_only", version=1,
            statement="A document snapshot becomes completed only from a validated Connector outcome containing a bounded tree with product references.",
            applies_when="an active VisMockup document snapshot is requested",
            enforcement_ref="plugins/simulation/simulation_backend/application/document_snapshots.py:DocumentSnapshotWorkflow.apply_connector_outcome",
            error_code="bom_snapshot_invalid",
            test_refs=("backend/tests/test_simulation_document_snapshot_workflow.py::test_snapshot_request_is_idempotent_and_completes_only_from_connector_outcome",),
        ),
    ),
    "simulation.environment.compose": (
        BusinessInvariantContract(
            rule_id="simulation.environment.compose.atomic_manifest", version=1,
            statement="Composition persists no environment manifest unless every product and resource binding resolves to an exact immutable source.",
            applies_when="a Connector environment is composed",
            enforcement_ref="plugins/simulation/simulation_backend/capabilities/environment_composition.py:EnvironmentCompositionProvider.compose",
            error_code="environment_binding_invalid",
            test_refs=("backend/tests/test_simulation_environment_composition_capabilities.py::test_compose_returns_every_problem_and_persists_nothing",),
        ),
    ),
    "simulation.environment.manifest.archive": (
        BusinessInvariantContract(
            rule_id="simulation.environment.archive.preserve_manifests", version=1,
            statement="Archiving changes only the environment identity lifecycle and never mutates an immutable manifest.",
            applies_when="a Connector environment is archived",
            enforcement_ref="plugins/simulation/simulation_backend/data/environment_repository.py:archive",
            error_code="simulation_environment_not_found",
            test_refs=("backend/tests/test_simulation_environment_manifest.py::test_manifest_is_independent_of_input_collection_order",),
        ),
    ),
    "simulation.environment.materialize": (
        BusinessInvariantContract(
            rule_id="simulation.environment.materialize.exact_manifest", version=1,
            statement="Local materialization uses the pinned manifest and verifies the resulting VisMockup scene before completion.",
            applies_when="an immutable environment is materialized",
            enforcement_ref="plugins/simulation/simulation_backend/application/connector_plans.py:build_materialization_plan",
            error_code="scene_verification_failed",
            test_refs=("backend/tests/test_simulation_capture_workflow.py::test_materialization_plan_attaches_models_before_scene_verification",),
        ),
    ),
    "simulation.capture_run.start": (
        BusinessInvariantContract(
            rule_id="simulation.capture.reverse_process_order", version=1,
            statement="Capture steps execute in descending process sequence and use VisMockup internal capture for the verified scene.",
            applies_when="a process screenshot run is started",
            enforcement_ref="plugins/simulation/simulation_backend/application/connector_plans.py:build_capture_plan",
            error_code="capture_failed",
            test_refs=("backend/tests/test_simulation_capture_workflow.py::test_capture_plan_orders_operations_descending",),
        ),
    ),
    "simulation.capture_run.cancel": (
        BusinessInvariantContract(
            rule_id="simulation.capture.cancel.unstarted_only", version=1,
            statement="Cancellation stops only queued steps and preserves active, completed and uncertain local outcomes.",
            applies_when="a capture run is cancelled",
            enforcement_ref="plugins/simulation/simulation_backend/application/capture_worker.py:cancel",
            error_code="local_execution_outcome_unknown",
            test_refs=("backend/tests/test_simulation_capture_workflow.py::test_cancel_stops_only_unstarted_steps",),
        ),
    ),
    "simulation.capture_step.retry": (
        BusinessInvariantContract(
            rule_id="simulation.capture.retry.proven_failed_only", version=1,
            statement="Retry creates a new attempt only after failure is proven and never replays an outcome-unknown step.",
            applies_when="a capture step retry is requested",
            enforcement_ref="plugins/simulation/simulation_backend/application/capture_worker.py:retry",
            error_code="local_execution_outcome_unknown",
            test_refs=("backend/tests/test_simulation_capture_workflow.py::test_outcome_unknown_requires_reconciliation_before_retry",),
        ),
    ),
}


def _errors(*, connector_environment: bool) -> tuple[DomainErrorContract, ...]:
    return tuple(
        DomainErrorContract(
            code=code, meaning=meaning, retryable=code in _RETRYABLE_ERROR_CODES,
        )
        for code, meaning in _ERROR_PAIRS
        if connector_environment or code in _LEGACY_ERROR_CODES
    )


def governed_spec(spec: Any) -> Any:
    return spec.model_copy(update={"plugin_callable": True, "input_schema": INPUT_SCHEMAS[spec.id], "output_schema": OUTPUT_SCHEMAS[spec.id]})


def descriptor_for(spec: Any) -> CapabilityDescriptorV2:
    governed = governed_spec(spec)
    descriptor = descriptor_from_provider_spec(governed)
    is_write = descriptor.side_effect_level is not SideEffectLevel.READ
    updates = {
        "lifecycle_status": (
            LifecycleStatus.EXPERIMENTAL
            if governed.id.startswith("simulation.document_snapshot.")
            else LifecycleStatus.STABLE
        ),
        "exposure": ExposurePolicy(web=True, api=True, plugin=True, agent=True, mcp=True),
        "exposure_policy_source": "provider_explicit",
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
        "domain_errors": _errors(connector_environment="connector_environment" in governed.tags),
        "domain_errors_complete": True,
    }
    if "connector_environment" in governed.tags:
        invariants = _CONNECTOR_BUSINESS_INVARIANTS.get(governed.id, ())
        updates.update({
            "business_effect": _CONNECTOR_BUSINESS_EFFECTS[governed.id],
            "business_acceptance_criteria": (
                "The result is scoped to the caller-visible immutable environment or capture-run identity.",
                "Inputs and outputs satisfy the closed published contract and retain exact source version pins.",
                "Rejected or uncertain local outcomes return a governed error and durable reconciliation evidence.",
            ),
            "business_invariants": invariants,
            "no_business_invariant_reason": None if invariants else _CONNECTOR_READ_REASON,
        })
    return CapabilityDescriptorV2.model_validate({**descriptor.model_dump(), **updates})


def register(registry: Any, spec: Any, handler: Any) -> None:
    governed = governed_spec(spec)
    descriptor = descriptor_for(governed)
    definition_hash = business_definition_hash(descriptor)

    def governed_handler(payload, context):
        return handler(payload, context.model_copy(update={
            "capability_version_gid": descriptor.capability_version_gid,
            "business_definition_hash": definition_hash,
        }))

    registry.register(governed, governed_handler, descriptor=descriptor)


__all__ = ["descriptor_for", "register"]

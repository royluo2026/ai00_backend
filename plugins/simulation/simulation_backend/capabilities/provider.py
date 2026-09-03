"""Native Capability V2 policy boundary owned by Simulation."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.contracts import AutomationLevel, BusinessInvariantContract, CapabilityDescriptorV2, DomainErrorContract, ExecutionMode, ExposurePolicy, LifecycleStatus, ResourceSelector, SideEffectLevel
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec
from backend.capability_v2.business_definition import business_definition_hash

from .contracts import INPUT_SCHEMAS as DOMAIN_INPUT_SCHEMAS, OUTPUT_SCHEMAS as DOMAIN_OUTPUT_SCHEMAS
from .connector_contracts import (
    INPUT_SCHEMAS as CONNECTOR_INPUT_SCHEMAS,
    OUTPUT_SCHEMAS as CONNECTOR_OUTPUT_SCHEMAS,
)

INPUT_SCHEMAS = {**DOMAIN_INPUT_SCHEMAS, **CONNECTOR_INPUT_SCHEMAS}
OUTPUT_SCHEMAS = {**DOMAIN_OUTPUT_SCHEMAS, **CONNECTOR_OUTPUT_SCHEMAS}


_TWO_PHASE_ENTRYPOINTS = {
    "simulation.document_snapshot.request",
    "simulation.environment.materialize",
    "simulation.capture_run.start",
}

_RESOURCES = {
    "simulation.connector.health.get": (("simulation-connector", "connector_id"),),
    "simulation.connector.plan.queue": (("simulation-connector", "plan.device_id"),),
    "simulation.vismockup.status.get": (("simulation-connector", "connector_id"),),
    "simulation.vismockup.application.launch": (("simulation-connector", "connector_id"),),
    "simulation.vismockup.model.open": (
        ("simulation-connector", "connector_id"),
        ("artifact", "artifact_ref.artifact_id"),
    ),
    "simulation.vismockup.tree.get": (("simulation-connector", "connector_id"),),
    "simulation.vismockup.selection.highlight": (("simulation-connector", "connector_id"),),
    "simulation.vismockup.visibility.change.apply": (("simulation-connector", "connector_id"),),
    "simulation.vismockup.capture.create": (("simulation-connector", "connector_id"),),
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
        ("simulation-connector", "device_id"),
    ),
    "simulation.document_snapshot.request": (("simulation-connector", "device_id"),),
    "simulation.document_snapshot.get": (("simulation-document-snapshot", "snapshot_request_id"),),
    "simulation.document_snapshot.action.get": (("simulation-document-snapshot", "snapshot_request_id"),),
    "simulation.document_snapshot.dispatch": (("simulation-document-snapshot", "snapshot_request_id"),),
    "simulation.environment.manifest.get": (("simulation-environment", "environment_id"),),
    "simulation.environment.manifest.archive": (("simulation-environment", "environment_id"),),
    "simulation.environment.preflight": (
        ("simulation-environment", "environment_id"), ("simulation-connector", "device_id"),
    ),
    "simulation.environment.materialize": (
        ("simulation-environment", "environment_id"), ("simulation-connector", "device_id"),
    ),
    "simulation.materialization_run.action.get": (("simulation-materialization-run", "run_id"),),
    "simulation.materialization_run.dispatch": (("simulation-materialization-run", "run_id"),),
    "simulation.capture_run.start": (
        ("simulation-environment", "environment_id"), ("simulation-connector", "device_id"),
    ),
    "simulation.capture_run.get": (("simulation-capture-run", "capture_run_id"),),
    "simulation.capture_run.action.get": (("simulation-capture-run", "capture_run_id"),),
    "simulation.capture_run.dispatch": (("simulation-capture-run", "capture_run_id"),),
    "simulation.capture_run.cancel": (("simulation-capture-run", "capture_run_id"),),
    "simulation.capture_step.retry": (("simulation-capture-run", "capture_run_id"),),
    "simulation.connector_capture_outcome.apply": (("simulation-capture-run", "capture_run_id"),),
    "simulation.connector_materialization_outcome.apply": (("simulation-materialization-run", "run_id"),),
    "simulation.connector_document_snapshot_outcome.apply": (("simulation-document-snapshot", "snapshot_request_id"),),
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
    ("document_snapshot_action_not_ready", "The prepared document snapshot action is not ready to dispatch."),
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
    ("downstream_confirmation_required", "The exact downstream action requires a separately issued user confirmation."),
    ("capture_action_not_ready", "No capture action is currently ready to dispatch."),
    ("materialization_run_not_found", "The materialization run is unavailable or not visible."),
    ("materialization_action_not_ready", "The materialization action is not ready to dispatch."),
    ("plan_outcome_invalid", "The Connector outcome does not match the immutable execution plan."),
    ("capability_migration_required", "This deprecated immediate-dispatch version must migrate to the @2 two-phase workflow."),
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
    "simulation.document_snapshot.action.get": "Return the exact Connector action that must be confirmed before the active VisMockup BOM is read.",
    "simulation.document_snapshot.dispatch": "Consume the separately issued Connector confirmation and dispatch the prepared active-document snapshot once.",
    "simulation.environment.compose": "Create one immutable, reproducible simulation-environment manifest from the selected process version, active VisMockup BOM and governed resource-model mappings.",
    "simulation.environment.manifest.get": "Return one caller-visible immutable simulation-environment manifest with its exact source and Connector contract pins.",
    "simulation.environment.manifest.search": "Return a bounded caller-visible list of simulation-environment manifests for reuse and audit.",
    "simulation.environment.manifest.archive": "Archive a simulation-environment identity while retaining every immutable manifest and execution record for audit.",
    "simulation.environment.preflight": "Report every known incompatibility between an immutable environment manifest and the bound AI00 Connector session without starting local work.",
    "simulation.environment.materialize": "Queue construction and verification of the exact immutable simulation environment in the bound user's VisMockup session.",
    "simulation.materialization_run.action.get": "Return the exact Connector action that must be confirmed before the prepared VisMockup environment is materialized.",
    "simulation.materialization_run.dispatch": "Consume the separately issued Connector confirmation and dispatch the prepared environment materialization once.",
    "simulation.capture_run.start": "Queue VisMockup-internal screenshots in reverse process order for an exact environment manifest and attach confirmed artifacts to their Craft operations.",
    "simulation.capture_run.get": "Return authoritative capture-run, step and artifact-association progress for the caller-visible run.",
    "simulation.capture_run.action.get": "Return the exact next Connector or Craft action that must be confirmed before one serialized capture transition.",
    "simulation.capture_run.dispatch": "Consume the separately issued confirmation for the exact next downstream action and dispatch only that action.",
    "simulation.capture_run.cancel": "Cancel only capture work that has not started while preserving active and completed outcomes for reconciliation.",
    "simulation.capture_step.retry": "Create a new attempt for one proven-failed capture step without replaying successful or outcome-unknown local effects.",
    "simulation.connector_capture_outcome.apply": "Project one authenticated Simulation-owned Connector outcome into the exact caller-visible capture run without dispatching later work.",
    "simulation.connector_materialization_outcome.apply": "Project one authenticated Simulation-owned Connector outcome into the exact caller-visible materialization run.",
    "simulation.connector_document_snapshot_outcome.apply": "Project one authenticated Simulation-owned Connector outcome into the exact caller-visible document snapshot request.",
}
_TWO_PHASE_BUSINESS_EFFECTS = {
    "simulation.document_snapshot.request": "Prepare one bounded immutable snapshot request for later user-confirmed Connector dispatch.",
    "simulation.environment.materialize": "Prepare construction and verification of the exact immutable simulation environment for later user-confirmed Connector dispatch.",
    "simulation.capture_run.start": "Prepare reverse-order VisMockup-internal screenshot steps; each Connector or Craft action is dispatched only after separate exact confirmation.",
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
    "simulation.document_snapshot.dispatch": (
        BusinessInvariantContract(
            rule_id="simulation.document_snapshot.dispatch_once", version=1,
            statement="The immutable snapshot plan is dispatched only after separate confirmation of the exact Connector action and is not offered again after dispatch.",
            applies_when="a prepared active-document snapshot is dispatched",
            enforcement_ref="plugins/simulation/simulation_backend/application/document_snapshots.py:DocumentSnapshotWorkflow.dispatch",
            error_code="document_snapshot_action_not_ready",
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
    "simulation.materialization_run.dispatch": (
        BusinessInvariantContract(
            rule_id="simulation.materialization.dispatch.confirmed_exact_plan", version=1,
            statement="Materialization dispatches only the immutable Connector plan prepared for the caller-visible run and requires its separate downstream confirmation.",
            applies_when="a prepared environment materialization is dispatched",
            enforcement_ref="plugins/simulation/simulation_backend/application/capture_worker.py:CaptureWorkflow.dispatch_materialization",
            error_code="downstream_confirmation_required",
            test_refs=("backend/tests/test_simulation_capture_workflow.py::test_materialization_plan_attaches_models_before_scene_verification",),
        ),
    ),
    "simulation.capture_run.dispatch": (
        BusinessInvariantContract(
            rule_id="simulation.capture.dispatch.one_at_a_time", version=1,
            statement="A later capture is not dispatched until the prior VisMockup artifact is uploaded and attached to its exact Craft operation.",
            applies_when="one prepared capture action is dispatched",
            enforcement_ref="plugins/simulation/simulation_backend/application/capture_worker.py:CaptureWorkflow.dispatch_next",
            error_code="capture_action_not_ready",
            test_refs=("backend/tests/test_simulation_capture_workflow.py::test_completed_artifact_is_attached_once_before_later_completed_step",),
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
    "simulation.connector_capture_outcome.apply": (
        BusinessInvariantContract(
            rule_id="simulation.connector_outcome.capture_identity", version=1,
            statement="A capture outcome updates only the capture run named by the immutable plan and never dispatches the next action.",
            applies_when="an authenticated capture outcome is projected",
            enforcement_ref="plugins/simulation/simulation_backend/capabilities/connector_outcomes.py:ConnectorOutcomeProvider.apply_capture",
            error_code="plan_outcome_invalid",
            test_refs=("backend/tests/test_simulation_connector_outcome_capabilities.py::test_capture_outcome_is_projected_only_through_its_exact_simulation_resource",),
        ),
    ),
    "simulation.connector_materialization_outcome.apply": (
        BusinessInvariantContract(
            rule_id="simulation.connector_outcome.materialization_identity", version=1,
            statement="A materialization outcome is accepted only for the exact persisted plan id and plan hash of its caller-visible run.",
            applies_when="an authenticated materialization outcome is projected",
            enforcement_ref="plugins/simulation/simulation_backend/application/capture_worker.py:CaptureWorkflow.apply_materialization_outcome",
            error_code="plan_outcome_invalid",
            test_refs=("backend/tests/test_simulation_capture_workflow.py::test_materialization_outcome_projects_terminal_status_to_domain_run",),
        ),
    ),
    "simulation.connector_document_snapshot_outcome.apply": (
        BusinessInvariantContract(
            rule_id="simulation.connector_outcome.document_snapshot_identity", version=1,
            statement="A document snapshot outcome is accepted only for the exact persisted plan and projects an empty uncertain reconciliation without inventing step data.",
            applies_when="an authenticated document snapshot outcome is projected",
            enforcement_ref="plugins/simulation/simulation_backend/application/document_snapshots.py:DocumentSnapshotWorkflow.apply_connector_outcome",
            error_code="plan_outcome_invalid",
            test_refs=("backend/tests/test_simulation_document_snapshot_workflow.py::test_snapshot_request_is_idempotent_and_completes_only_from_connector_outcome",),
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
            LifecycleStatus.DEPRECATED
            if governed.id in _TWO_PHASE_ENTRYPOINTS and governed.version == 1
            else LifecycleStatus.EXPERIMENTAL
            if governed.id in _TWO_PHASE_ENTRYPOINTS and governed.version >= 2
            or governed.id.startswith("simulation.document_snapshot.")
            or governed.id in {
                "simulation.capture_run.action.get", "simulation.capture_run.dispatch",
                "simulation.materialization_run.action.get", "simulation.materialization_run.dispatch",
            }
            or governed.id.startswith("simulation.connector")
            or governed.id.startswith("simulation.vismockup.")
            else LifecycleStatus.STABLE
        ),
        "exposure": (
            ExposurePolicy(local_runtime=True)
            if governed.id.startswith("simulation.vismockup.")
            else ExposurePolicy(web=True, api=True, plugin=True, agent=True, mcp=True)
        ),
        "exposure_policy_source": "provider_explicit",
        "automation_level": AutomationLevel.A1 if is_write else AutomationLevel.A2,
        "authorization_policy": "simulation.v2:" + ",".join(governed.permissions),
        "resource_selectors": tuple(ResourceSelector(resource_type=t, payload_path=p) for t, p in _RESOURCES.get(governed.id, ())),
        "data_classification": "confidential", "delegation_policy": "scoped",
        "agent_output_schema": descriptor.output_schema,
        "execution_mode": (
            ExecutionMode.LOCAL
            if governed.id.startswith("simulation.vismockup.")
            else ExecutionMode.CLOUD_ASYNC
            if governed.id == "simulation.run.start"
            else descriptor.execution_mode
        ),
        "artifact_policy": (
            "input" if governed.id == "simulation.vismockup.model.open"
            else "output" if governed.id in {"simulation.result.get", "simulation.vismockup.capture.create"}
            else "none"
        ),
        "operation_policy": (
            "required" if governed.id.startswith("simulation.vismockup.") or governed.id == "simulation.run.start"
            else "optional" if is_write else "none"
        ),
        "concurrency_policy": "none", "idempotency_policy": "required" if is_write else "none",
        "consistency_policy": "external" if is_write else "strong", "evidence_policy": "required",
        "domain_errors": _errors(connector_environment=(
            "connector_environment" in governed.tags
            or governed.id.startswith("simulation.connector")
            or governed.id.startswith("simulation.vismockup.")
        )),
        "domain_errors_complete": True,
    }
    if governed.id in _TWO_PHASE_ENTRYPOINTS and governed.version == 1:
        updates.update({
            "exposure": ExposurePolicy(),
            "agent_output_schema": None,
            "deprecation_message": f"Immediate dispatch is closed; migrate to {governed.id}@2 and its action/dispatch workflow.",
            "no_consumer_reason": "The unsafe immediate-dispatch contract is frozen with no verified runtime consumer and accepts no new traffic.",
        })
    if governed.id.startswith("simulation.connector_") and governed.id.endswith("_outcome.apply"):
        updates.update({
            "exposure": ExposurePolicy(local_runtime=True),
            "automation_level": AutomationLevel.A2,
        })
    if "connector_environment" in governed.tags:
        invariants = _CONNECTOR_BUSINESS_INVARIANTS.get(governed.id, ())
        updates.update({
            "business_effect": (
                _TWO_PHASE_BUSINESS_EFFECTS[governed.id]
                if governed.id in _TWO_PHASE_ENTRYPOINTS and governed.version >= 2
                else _CONNECTOR_BUSINESS_EFFECTS[governed.id]
            ),
            "business_acceptance_criteria": (
                "The result is scoped to the caller-visible immutable environment or capture-run identity.",
                "Inputs and outputs satisfy the closed published contract and retain exact source version pins.",
                "Rejected or uncertain local outcomes return a governed error and durable reconciliation evidence.",
            ),
            "business_invariants": invariants,
            "no_business_invariant_reason": None if invariants else _CONNECTOR_READ_REASON,
        })
    if (
        governed.id.startswith("simulation.connector.")
        or governed.id.startswith("simulation.vismockup.")
    ):
        updates.update({
            "business_effect": (
                "Validate and persist one exact Connector control-plane operation for the caller-bound Simulation runtime."
                if governed.id.startswith("simulation.connector.")
                else "Expose one exact VisMockup adapter atom exclusively to a signed Simulation Connector execution plan."
            ),
            "business_acceptance_criteria": (
                "The operation is scoped to the caller's single bound Simulation Connector.",
                "The closed request and response contracts preserve exact Connector and Adapter identity.",
                "Rejected operations do not create ungoverned VisMockup side effects.",
            ),
            "business_invariants": (),
            "no_business_invariant_reason": (
                "Identity, contract and execution-plan validation fully determine this atomic boundary; no additional business-state rule is decided here."
            ),
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

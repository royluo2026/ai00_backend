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

_VISMOCKUP_WEB_WORKFLOWS = {
    "simulation.teamcenter.product.search.request",
    "simulation.teamcenter.revision_rule.search.request",
    "simulation.teamcenter.product_structure.observe.request",
    "simulation.teamcenter.product_structure.page.read.request",
    "simulation.teamcenter.visualization.launch.request",
    "simulation.teamcenter.visualization.insert.request",
    "simulation.vismockup.document.identity.read.request",
    "simulation.vismockup.document.hierarchy_inventory.read.request",
    "simulation.vismockup.application.attach.request",
    "simulation.vismockup.application.launch.request",
    "simulation.vismockup.model.open.request",
    "simulation.environment.runtime_package.open.request",
    "simulation.vismockup.model.insert.request",
    "simulation.vismockup.model.close.request",
    "simulation.vismockup.visibility.change.request",
    "simulation.vismockup.node.visibility.change.request",
    "simulation.vismockup.node.selection.change.request",
    "simulation.vismockup.tree.read.request",
    "simulation.vismockup.command.get",
}

_TEAMCENTER_BUSINESS_EFFECTS = {
    "simulation.teamcenter.product.search.request": "Queue a deterministic exact, prefix, and contains search of Teamcenter item IDs and names without mutating Teamcenter.",
    "simulation.teamcenter.revision_rule.search.request": "Queue a read of the revision rules available to the current in-memory Teamcenter session.",
    "simulation.teamcenter.product_structure.observe.request": "Queue one bounded read-only observation of the selected Teamcenter product structure.",
    "simulation.teamcenter.product_structure.page.read.request": "Return a signed operation receipt for retrieving occurrence rows from an existing local Teamcenter observation.",
    "simulation.teamcenter.visualization.launch.request": "Queue an official Teamcenter Visualization launch that opens one exact online source as a new VisMockup document.",
    "simulation.teamcenter.visualization.insert.request": "Queue an official Teamcenter Visualization launch that inserts one exact online source into the active VisMockup document.",
    "simulation.teamcenter.product.search": "Search Teamcenter item IDs and names using deterministic exact, prefix, and contains matching.",
    "simulation.teamcenter.revision_rule.search": "Read the revision rules available to the current in-memory Teamcenter session.",
    "simulation.teamcenter.product_structure.observe": "Materialize a temporary local observation identity and node-count evidence for an exact Teamcenter product structure.",
    "simulation.teamcenter.product_structure.page.read": "Return cached occurrence rows, continuation position, and an integrity hash from a local Teamcenter observation.",
    "simulation.teamcenter.visualization.launch": "Open one exact Teamcenter online source as a new VisMockup document using official launch information.",
    "simulation.teamcenter.visualization.insert": "Insert one exact Teamcenter online source into the active VisMockup document using official launch information.",
}

_RESOURCES = {
    "simulation.connector.health.get": (("simulation-connector", "connector_id"),),
    "simulation.connector.plan.queue": (("simulation-connector", "plan.device_id"),),
    "simulation.teamcenter.product.search.request": (("teamcenter-endpoint", "endpoint_id"),),
    "simulation.teamcenter.revision_rule.search.request": (("teamcenter-endpoint", "endpoint_id"),),
    "simulation.teamcenter.product_structure.observe.request": (("teamcenter-endpoint", "source_selector.endpoint_id"), ("teamcenter-online-source", "source_selector.object_uid")),
    "simulation.teamcenter.product_structure.page.read.request": (("teamcenter-observation", "observation_id"),),
    "simulation.teamcenter.visualization.launch.request": (("teamcenter-endpoint", "source_selector.endpoint_id"), ("teamcenter-online-source", "source_selector.object_uid")),
    "simulation.teamcenter.visualization.insert.request": (("teamcenter-endpoint", "source_selector.endpoint_id"), ("teamcenter-online-source", "source_selector.object_uid")),
    "simulation.teamcenter.product.search": (("teamcenter-endpoint", "endpoint_id"),),
    "simulation.teamcenter.revision_rule.search": (("teamcenter-endpoint", "endpoint_id"),),
    "simulation.teamcenter.product_structure.observe": (("teamcenter-endpoint", "source_selector.endpoint_id"), ("teamcenter-online-source", "source_selector.object_uid")),
    "simulation.teamcenter.product_structure.page.read": (("teamcenter-observation", "observation_id"),),
    "simulation.teamcenter.visualization.launch": (("teamcenter-endpoint", "source_selector.endpoint_id"), ("teamcenter-online-source", "source_selector.object_uid")),
    "simulation.teamcenter.visualization.insert": (("teamcenter-endpoint", "source_selector.endpoint_id"), ("teamcenter-online-source", "source_selector.object_uid")),
    "simulation.vismockup.application.attach.request": (),
    "simulation.vismockup.application.launch.request": (),
    "simulation.vismockup.model.open.request": (("artifact", "artifact_ref.artifact_id"),),
    "simulation.environment.runtime_package.open.request": (("simulation-workspace", "workspace_gid"),),
    "simulation.environment.runtime_package.prepare": (("simulation-workspace", "workspace_gid"),),
    "simulation.vismockup.model.insert.request": (("artifact", "artifact_ref.artifact_id"),),
    "simulation.vismockup.model.close.request": (),
    "simulation.vismockup.visibility.change.request": (),
    "simulation.vismockup.node.visibility.change.request": (),
    "simulation.vismockup.node.selection.change.request": (),
    "simulation.vismockup.tree.read.request": (),
    "simulation.vismockup.document.hierarchy_inventory.read.request": (),
    "simulation.vismockup.command.get": (("simulation-connector-command", "operation_id"),),
    "simulation.vismockup.status.get": (("simulation-connector", "connector_id"),),
    "simulation.vismockup.application.launch": (("simulation-connector", "connector_id"),),
    "simulation.vismockup.model.open": (
        ("simulation-connector", "connector_id"),
        ("artifact", "artifact_ref.artifact_id"),
    ),
    "simulation.vismockup.tree.get": (("simulation-connector", "connector_id"),),
    "simulation.vismockup.selection.highlight": (("simulation-connector", "connector_id"),),
    "simulation.vismockup.visibility.change.apply": (("simulation-connector", "connector_id"),),
    "simulation.vismockup.node.visibility.change.apply": (("simulation-connector", "connector_id"),),
    "simulation.vismockup.node.selection.change.apply": (("simulation-connector", "connector_id"),),
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
    "simulation.vismockup.model.insert": (
        ("simulation-connector", "connector_id"),
        ("artifact", "artifact_ref.artifact_id"),
    ),
    "simulation.environment.bop_vm_binding_draft.preview": (
        ("craft-bop-version", "execution_plan_ref.version_gid"),
        ("simulation-document-snapshot", "snapshot_request_id"),
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
    "simulation.connector_environment_runtime_outcome.apply": (),
    "simulation.run.start": (("simulation-environment", "environment_id"),),
    "simulation.run.get": (("simulation-run", "run_id"),),
    "simulation.result.get": (("simulation-run", "run_id"),),
    "simulation.result.compare": (("simulation-run", "left_result_ref.run_id"), ("simulation-run", "right_result_ref.run_id")),
    "simulation.environment.workspace.get": (("simulation-workspace", "workspace_gid"),),
    "simulation.environment.model_document.search": (("simulation-workspace", "workspace_gid"),),
    "simulation.environment.model_document.add": (("simulation-workspace", "workspace_gid"),),
    "simulation.environment.model_document.remove": (("simulation-workspace", "workspace_gid"),),
    "simulation.environment.online_source.bind": (("simulation-workspace", "workspace_gid"),),
    "simulation.product_structure.observation.begin": (("simulation-workspace", "workspace_gid"),),
    "simulation.product_structure.observation.page.append": (),
    "simulation.product_structure.observation.publish": (),
    "simulation.product_structure.snapshot.page.get": (),
    "simulation.environment.alternate_hierarchy.search": (("simulation-workspace", "workspace_gid"),),
    "simulation.environment.alternate_hierarchy.get": (("simulation-alternate-hierarchy", "hierarchy_gid"),),
    "simulation.environment.alternate_hierarchy.create": (("simulation-workspace", "workspace_gid"),),
    "simulation.environment.alternate_hierarchy.bootstrap_from_bop_fork": (("simulation-workspace", "workspace_gid"),),
    "simulation.environment.alternate_hierarchy.update": (("simulation-alternate-hierarchy", "hierarchy_gid"),),
    "simulation.environment.alternate_hierarchy.archive": (("simulation-alternate-hierarchy", "hierarchy_gid"),),
    "simulation.environment.placement.create": (("simulation-alternate-hierarchy", "hierarchy_gid"),),
    "simulation.environment.placement.move": (("simulation-placement", "placement_gid"),),
    "simulation.environment.placement.remove": (("simulation-placement", "placement_gid"),),
    "simulation.environment.bop_projection.preview": (("simulation-workspace", "workspace_gid"), ("craft-bop-version", "version_gid")),
    "simulation.environment.bop_projection.apply": (("simulation-workspace", "workspace_gid"), ("craft-bop-version", "version_gid")),
    "simulation.plmxml.environment.inspect": (("artifact", "artifact_ref.artifact_id"),),
    "simulation.plmxml.model_tree.read": (("artifact", "artifact_ref.artifact_id"),),
    "simulation.environment.restore_from_plmxml": (("artifact", "artifact_ref.artifact_id"),),
    "simulation.environment.plmxml.insert": (("simulation-workspace", "workspace_gid"), ("artifact", "artifact_ref.artifact_id")),
    "simulation.plmxml.environment.import": (("simulation-workspace", "workspace_gid"), ("artifact", "artifact_ref.artifact_id")),
    "simulation.plmxml.environment.export": (("simulation-workspace", "workspace_gid"),),
    "simulation.environment.workspace.cache_lease.get": (("simulation-workspace", "workspace_gid"),),
    "simulation.environment.workspace.update": (("simulation-workspace", "workspace_gid"),),
    "simulation.environment.workspace.delete": (("simulation-workspace", "workspace_gid"),),
    "simulation.environment.workspace.fork.preview": (("simulation-workspace", "source_workspace_gid"),),
    "simulation.environment.workspace_version.search": (("simulation-workspace", "workspace_gid"),),
    "simulation.environment.structure_node.create": (("simulation-workspace", "workspace_gid"),),
    "simulation.environment.structure_node.move": (("simulation-workspace", "workspace_gid"),),
    "simulation.environment.structure_node.remove": (("simulation-workspace", "workspace_gid"),),
    "simulation.environment.binding.create": (("simulation-workspace", "workspace_gid"),),
    "simulation.environment.binding.remove": (("simulation-workspace", "workspace_gid"),),
    "simulation.environment.live_document.rebind": (("simulation-workspace", "workspace_gid"),),
    "simulation.environment.version.freeze": (("simulation-workspace", "workspace_gid"),),
    "simulation.vm_checkpoint.create": (("simulation-workspace", "workspace_gid"), ("simulation-document-snapshot", "snapshot_request_id")),
    "simulation.vm_checkpoint.search": (("simulation-workspace", "workspace_gid"),),
    "simulation.vm_checkpoint.archive": (("simulation-vm-checkpoint", "checkpoint_gid"), ("simulation-workspace", "workspace_gid")),
    "simulation.vm_diff_report.generate": (("simulation-vm-checkpoint", "before_checkpoint_gid"), ("simulation-vm-checkpoint", "after_checkpoint_gid")),
    "simulation.vm_diff_report.get": (("simulation-vm-diff-report", "report_gid"),),
    "simulation.vm_diff_item.search": (("simulation-vm-diff-report", "report_gid"),),
}
_ERROR_PAIRS = (
    ('runtime_owner_mismatch', 'The authenticated user and tenant do not own this runtime device.'),
    ('runtime_session_invalid', 'The session no longer matches the active device, generation, instance, hash, or expiry.'),
    ('runtime_generation_invalid', 'The expected runtime generation has changed.'),
    ('runtime_instance_invalid', 'The runtime instance identity is malformed.'),
    ('runtime_session_conflict', 'A concurrent runtime change fenced this operation.'),
    ('runtime_plans_unresolved', 'Leased, executing, unknown, or manual-review work blocks replacement.'),
    ('runtime_takeover_audit_required', 'Takeover requires the authenticated actor and a nonempty bounded reason.'),
    ('pairing_owner_mismatch', 'The App pairing belongs to another user or tenant.'),
    ('pairing_consumed', 'The App pairing has already been activated or cancelled.'),
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
    ("primary_model_document_exists", "The environment already has an active primary model document."),
    ("primary_model_document_required", "Exactly one active primary model document is required."),
    ("model_document_dependency_cycle", "The selected model document would create a cyclic PLMXML dependency."),
    ("plmxml_artifact_hash_mismatch", "The PLMXML Artifact bytes do not match the immutable reference hash."),
    ("plmxml_artifact_unavailable", "The immutable PLMXML Artifact is unavailable or outside the caller scope."),
    ("alternate_hierarchy_not_found", "The alternate hierarchy is unavailable or outside the caller scope."),
    ("bop_fork_projection_failed", "The completed Craft fork projection could not be loaded for repair."),
    ("bop_fork_already_bootstrapped", "The Craft fork already has an alternate hierarchy in this environment."),
    ("bop_projection_hash_invalid", "The Craft fork projection has no valid immutable content hash."),
    ("bop_projection_parent_missing", "The Craft fork projection references a missing parent node."),
    ("bop_projection_cycle", "The Craft fork projection contains a node cycle."),
    ("pairing_not_found", "The Connector pairing request does not exist."),
    ("pairing_bootstrap_not_found", "The Connector bootstrap ticket does not exist or is not visible to this user."),
    ("pairing_bootstrap_expired", "The two-minute Connector bootstrap ticket expired."),
    ("pairing_bootstrap_reused", "The Connector bootstrap ticket was already claimed or cancelled."),
    ("pairing_bootstrap_active", "An active Connector bootstrap ticket cannot be cancelled."),
    ("pairing_bootstrap_version_conflict", "The Connector bootstrap ticket changed after it was displayed."),
    ("pairing_bootstrap_conflict", "The Connector bootstrap ticket could not be created uniquely."),
    ("pairing_bootstrap_owner_mismatch", "The Connector bootstrap ticket belongs to a different user or team scope."),
    ("pairing_expired", "The five-minute Connector pairing request expired."),
    ("pairing_proof_invalid", "The Connector did not prove the original verifier and installation identity."),
    ("pairing_activation_proof_invalid", "The Connector activation proof is invalid."),
    ("pairing_not_approved", "The signed-in AI00 user has not approved this pairing."),
    ("pairing_version_conflict", "The pairing changed after it was displayed."),
    ("connector_binding_conflict", "The AI00 user already has a different Connector binding."),
    ("connector_binding_not_found", "The signed-in user has no bound Simulation Connector."),
    ("connector_command_not_found", "The requested Connector command is unavailable or outside the caller scope."),
    ("capability_provenance_required", "The Connector command requires exact Capability version and business-definition provenance."),
    ("vismockup_document_not_owned", "AI00 may close only a VisMockup document that it opened in this Connector session."),
    ("feishu_login_required", "Pairing approval requires an AI00 Web session established through Feishu login."),
)
_RUNTIME_ERROR_CODES = frozenset(code for code, _ in _ERROR_PAIRS[:9])
_LEGACY_ERROR_CODES = frozenset(code for code, _ in _ERROR_PAIRS[9:18])
_RETRYABLE_ERROR_CODES = frozenset({
    "source_resolver_unavailable", "simulation_result_not_ready",
    "execution_plan_unavailable", "active_document_unavailable",
    "connector_offline", "interactive_session_missing", "vismockup_unavailable",
    "capture_failed", "artifact_upload_unconfirmed", "craft_screenshot_attach_failed",
})

_PLMXML_ERROR_PAIRS = (
    ("plmxml_artifact_hash_mismatch", "The PLMXML Artifact bytes do not match the immutable reference hash."),
    ("plmxml_artifact_unavailable", "The immutable PLMXML Artifact is unavailable or outside the caller scope."),
    ("plmxml_dependency_artifact_invalid", "A supplied PLMXML dependency Artifact reference is malformed or duplicated."),
    ("plmxml_dependency_media_type_mismatch", "A dependency Artifact media type does not match the PLMXML reference."),
    ("plmxml_dependency_artifact_unavailable", "A dependency Artifact is unavailable or outside the caller scope."),
    ("plmxml_dependency_artifact_hash_mismatch", "A dependency Artifact does not match its immutable SHA-256 reference."),
    ("plmxml_insert_mode_required", "PLMXML insertion requires an explicit model-only or selected-hierarchy mode."),
    ("plmxml_hierarchy_selection_invalid", "The selected hierarchy identities are invalid for this inspected PLMXML."),
    ("plmxml_inspection_changed", "The inspected PLMXML projection changed before the requested write."),
)

_PLMXML_WEB_BUSINESS_EFFECTS = {
    "simulation.plmxml.environment.inspect": "Return a bounded, immutable inspection of one PLMXML Artifact so a user can explicitly choose which model and alternate-hierarchy projections to import.",
    "simulation.plmxml.model_tree.read": "Return the bounded read-only product occurrence tree of one authorized immutable PLMXML Artifact for the Simulation model-document panel.",
    "simulation.environment.restore_from_plmxml": "Create one private Simulation workspace from an immutable PLMXML model and its selected hierarchies, retaining unresolved external references for later explicit materialization.",
    "simulation.environment.plmxml.insert": "Add one immutable PLMXML model and only the explicitly selected alternate hierarchies to one exact owned Simulation workspace draft.",
}

_CONNECTOR_BUSINESS_EFFECTS = {
    "simulation.document_snapshot.request": "Queue one bounded immutable snapshot of the bound user's currently active VisMockup BOM for later environment composition.",
    "simulation.document_snapshot.get": "Return authoritative status and the immutable confirmed BOM snapshot for one caller-visible request.",
    "simulation.document_snapshot.action.get": "Return the exact Connector action that must be confirmed before the active VisMockup BOM is read.",
    "simulation.document_snapshot.dispatch": "Consume the separately issued Connector confirmation and dispatch the prepared active-document snapshot once.",
    "simulation.environment.compose": "Create one immutable, reproducible simulation-environment manifest from the selected process version, active VisMockup BOM and governed resource-model mappings.",
    "simulation.environment.bop_vm_binding_draft.preview": "Produce a deterministic non-mutating first-pass binding draft from one pinned BOP execution structure and one confirmed VM snapshot.",
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
    "simulation.connector_environment_runtime_outcome.apply": "Project one authenticated frozen-environment open and tree-readback outcome without prematurely claiming semantic equivalence.",
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
    "simulation.connector_environment_runtime_outcome.apply": (
        BusinessInvariantContract(
            rule_id="simulation.connector_outcome.environment_runtime_identity", version=1,
            statement="A frozen-environment runtime outcome updates only the pending verification bound to its exact immutable Connector plan and tree readback never implies semantic verification.",
            applies_when="an authenticated frozen-environment runtime outcome is projected",
            enforcement_ref="plugins/simulation/simulation_backend/data/workspace_repository.py:WorkspaceRepository.apply_runtime_package_outcome",
            error_code="plan_outcome_invalid",
            test_refs=("backend/tests/test_simulation_connector_outcome_capabilities.py::test_environment_runtime_outcome_records_readback_without_claiming_semantic_verification",),
        ),
    ),
}


def _errors(*, connector_environment: bool, include_runtime_errors: bool) -> tuple[DomainErrorContract, ...]:
    return tuple(
        DomainErrorContract(
            code=code, meaning=meaning, retryable=code in _RETRYABLE_ERROR_CODES,
        )
        for code, meaning in _ERROR_PAIRS
        if (
            code in _LEGACY_ERROR_CODES
            or connector_environment and (include_runtime_errors or code not in _RUNTIME_ERROR_CODES)
        )
    )


def governed_spec(spec: Any) -> Any:
    input_schema = INPUT_SCHEMAS.get((spec.id, spec.version), INPUT_SCHEMAS.get(spec.id, spec.input_schema))
    output_schema = OUTPUT_SCHEMAS.get((spec.id, spec.version), OUTPUT_SCHEMAS.get(spec.id, spec.output_schema))
    return spec.model_copy(update={"plugin_callable": True, "input_schema": input_schema, "output_schema": output_schema})


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
            or governed.id == "simulation.environment.compose" and governed.version >= 2
            or governed.id.startswith("simulation.document_snapshot.")
            or governed.id in {
                "simulation.capture_run.action.get", "simulation.capture_run.dispatch",
                "simulation.materialization_run.action.get", "simulation.materialization_run.dispatch",
            }
            or governed.id.startswith("simulation.connector")
            or governed.id.startswith("simulation.vismockup.")
            or governed.id.startswith("simulation.teamcenter.")
            or "experimental" in governed.tags
            else LifecycleStatus.STABLE
        ),
        "exposure": (
            ExposurePolicy(web=True)
            if governed.id.startswith("simulation.teamcenter.") and governed.id in _VISMOCKUP_WEB_WORKFLOWS
            else ExposurePolicy(web=True, api=True, plugin=True, agent=True, mcp=True)
            if governed.id in _VISMOCKUP_WEB_WORKFLOWS
            else ExposurePolicy(local_runtime=True)
            if governed.id.startswith("simulation.vismockup.") or governed.id.startswith("simulation.teamcenter.")
            or governed.id in {
                "simulation.connector.pairing.request",
                "simulation.connector.pairing.complete",
                "simulation.connector.pairing.activate",
            }
            else ExposurePolicy(web=True)
            if governed.id in {
                "simulation.connector.pairing.bootstrap.create",
                "simulation.connector.pairing.bootstrap.get",
                "simulation.connector.pairing.summary.get",
                "simulation.connector.pairing.approve",
                "simulation.connector.pairing.cancel",
                "simulation.connector.binding.get",
                "simulation.connector.runtime.takeover",
            }
            else ExposurePolicy(web=True, api=True, plugin=True, agent=True, mcp=True)
        ),
        "exposure_policy_source": "provider_explicit",
        "automation_level": AutomationLevel.A1 if is_write else AutomationLevel.A2,
        "authorization_policy": "simulation.v2:" + ",".join(governed.permissions),
        "resource_selectors": tuple(ResourceSelector(resource_type=t, payload_path=p) for t, p in _RESOURCES.get(governed.id, ())),
        "data_classification": "confidential", "delegation_policy": "scoped",
        "agent_output_schema": descriptor.output_schema,
        "execution_mode": (
            ExecutionMode.CLOUD_SYNC
            if governed.id in _VISMOCKUP_WEB_WORKFLOWS
            else ExecutionMode.LOCAL
            if governed.id.startswith("simulation.vismockup.") or governed.id.startswith("simulation.teamcenter.")
            or governed.id in {
                "simulation.connector.pairing.request",
                "simulation.connector.pairing.complete",
                "simulation.connector.pairing.activate",
            }
            else ExecutionMode.CLOUD_ASYNC
            if governed.id == "simulation.run.start"
            else descriptor.execution_mode
        ),
        "artifact_policy": (
            "input" if governed.id in {"simulation.vismockup.model.open", "simulation.vismockup.model.open.request"}
            else "output" if governed.id in {"simulation.result.get", "simulation.vismockup.capture.create"}
            else "none"
        ),
        "operation_policy": (
            "optional" if governed.id in _VISMOCKUP_WEB_WORKFLOWS and is_write
            else "none" if governed.id in _VISMOCKUP_WEB_WORKFLOWS
            else "required" if governed.id.startswith(("simulation.vismockup.", "simulation.teamcenter.")) or governed.id == "simulation.run.start"
            else "optional" if is_write else "none"
        ),
        "concurrency_policy": "none", "idempotency_policy": "required" if is_write else "none",
        "consistency_policy": "external" if is_write else "strong", "evidence_policy": "required",
        "domain_errors": _errors(connector_environment=(
            "connector_environment" in governed.tags
            or governed.id.startswith("simulation.connector")
            or governed.id.startswith("simulation.vismockup.")
            or governed.id.startswith("simulation.teamcenter.")
        ), include_runtime_errors=(
            governed.id.startswith("simulation.connector")
            or governed.id.startswith("simulation.vismockup.")
            or governed.id.startswith("simulation.teamcenter.")
        )),
        "domain_errors_complete": "experimental" not in governed.tags,
    }
    if governed.id in _TWO_PHASE_ENTRYPOINTS and governed.version == 1:
        updates.update({
            "exposure": ExposurePolicy(),
            "agent_output_schema": None,
            "deprecation_message": f"Immediate dispatch is closed; migrate to {governed.id}@2 and its action/dispatch workflow.",
            "no_consumer_reason": "The unsafe immediate-dispatch contract is frozen with no verified runtime consumer and accepts no new traffic.",
        })
    if governed.id == "simulation.environment.workspace.cache_lease.get":
        updates.update({
            "domain_errors": (
                DomainErrorContract(code="workspace_not_found", meaning="The requested workspace is unavailable or no longer readable.", is_caller_error=True),
                DomainErrorContract(code="cache_lease_ttl_invalid", meaning="The requested cache lease lifetime must be between 60 and 300 seconds.", is_caller_error=True),
                DomainErrorContract(code="cache_lease_signing_key_unavailable", meaning="The server cannot issue authenticated cache leases until signing material is configured."),
            ),
            "domain_errors_complete": True,
        })
    if governed.id.startswith("simulation.plmxml.environment.") or governed.id in {
        "simulation.plmxml.model_tree.read",
        "simulation.environment.restore_from_plmxml",
        "simulation.environment.plmxml.insert",
    }:
        updates.update({
            "domain_errors": tuple(
                DomainErrorContract(code=code, meaning=meaning, is_caller_error=True)
                for code, meaning in _PLMXML_ERROR_PAIRS
            ),
            "domain_errors_complete": False,
        })
    if governed.id in _PLMXML_WEB_BUSINESS_EFFECTS:
        updates.update({
            "exposure": ExposurePolicy(web=True),
            "business_effect": _PLMXML_WEB_BUSINESS_EFFECTS[governed.id],
            "business_acceptance_criteria": (
                "The source and every dependency are immutable Artifact references whose bytes match the declared SHA-256 hash.",
                "An inspection hash binds the user's explicit import decision to the exact parsed projection.",
                "Rejected input creates no partial workspace, document, hierarchy or placement state.",
            ),
            "business_invariants": (),
            "no_business_invariant_reason": "Artifact immutability, explicit selection, optimistic concurrency and one Simulation transaction fully determine this atomic boundary.",
        })
    if governed.id in {"simulation.environment.bop_projection.preview", "simulation.environment.bop_projection.apply"}:
        updates.update({
            "exposure": ExposurePolicy(web=True),
            "business_effect": (
                "Preview the exact published or explicitly selected active Craft BOP process skeleton for insertion into one owned Simulation environment."
                if governed.id.endswith(".preview") else
                "Atomically insert the previously previewed exact Craft BOP process skeleton as one editable alternate hierarchy."
            ),
            "business_acceptance_criteria": (
                "The source is read only through Craft's revision-pinned execution structure contract: published versions use get@1 and an explicitly selected active version uses preview@1 after resolving its current revision.",
                "Product and resource references are counted as separate source references and are never copied into the editable process skeleton as hierarchy nodes.",
                "Apply recomputes the projection and rejects a changed source, target row version or plan hash without partial writes.",
            ),
            "business_invariants": (),
            "no_business_invariant_reason": "The exact owner projection, deterministic plan hash, optimistic concurrency and one Simulation transaction fully determine this experimental boundary.",
            "consistency_policy": "external" if governed.id.endswith(".apply") else "strong",
            "domain_errors": tuple(DomainErrorContract(code=code, meaning=meaning, retryable=retryable, is_caller_error=True) for code, meaning, retryable in (
                ("workspace_not_found", "The target Simulation environment is unavailable or not owned by the caller.", False),
                ("version_conflict", "The target environment row version changed.", True),
                ("fork_depth_invalid", "The requested BOP projection depth is unsupported.", False),
                ("bop_projection_hash_invalid", "The Craft execution structure has no valid immutable hash.", False),
                ("bop_projection_node_invalid", "The Craft execution structure contains an invalid node.", False),
                ("bop_projection_line_not_found", "The requested line is not present in the exact Craft execution structure.", False),
                ("bop_projection_parent_missing", "The projected process skeleton references a missing parent.", False),
                ("bop_projection_cycle", "The projected process skeleton contains a cycle.", False),
                ("bop_projection_plan_changed", "The exact preview no longer matches the current source or target.", True),
                ("bop_projection_already_inserted", "The exact BOP projection is already present in the target environment.", False),
                ("bop_execution_structure_failed", "The owning Craft capability could not return the exact revision-pinned execution structure.", True),
                ("bop_version_resolution_failed", "The owning Craft capability could not resolve the selected BOP revision.", True),
                ("bop_revision_unavailable", "The selected BOP did not expose a valid revision for a draft preview.", False),
                ("domain_client_unavailable", "The governed owning-domain invocation boundary is unavailable.", True),
                ("idempotency_conflict", "The idempotency key is bound to another BOP projection request.", False),
            )),
            "domain_errors_complete": True,
        })
    if governed.id.startswith("simulation.vm_checkpoint."):
        updates.update({
            "business_effect": "Persist or read immutable user-named VM version evidence without deleting its underlying technical snapshot.",
            "business_acceptance_criteria": (
                "A checkpoint references only an exact completed Connector snapshot already projected into authoritative VM persistence.",
                "Personal checkpoints remain caller-private while shared baselines require workspace ownership, project management, or super-admin authority.",
                "Archive preserves the checkpoint row and all referenced snapshot evidence.",
            ),
            "business_invariants": (),
            "no_business_invariant_reason": _CONNECTOR_READ_REASON,
            "domain_errors": tuple(DomainErrorContract(code=code, meaning=meaning, retryable=retryable, is_caller_error=caller) for code, meaning, retryable, caller in (
                ("workspace_not_found", "The checkpoint workspace is unavailable or unreadable.", False, True),
                ("document_snapshot_not_found", "The source snapshot request is unavailable to this caller.", False, True),
                ("document_snapshot_not_completed", "The source snapshot request has not completed.", True, True),
                ("snapshot_hash_mismatch", "The supplied hash differs from the authoritative completed snapshot.", False, True),
                ("vm_snapshot_projection_required", "The completed Connector snapshot has not yet been projected into authoritative VM persistence.", True, False),
                ("vm_checkpoint_shared_forbidden", "The caller cannot create or archive a shared project baseline.", False, True),
                ("vm_checkpoint_not_found_or_conflict", "The checkpoint is unavailable or its row version changed.", True, True),
                ("idempotency_conflict", "The idempotency key is bound to different checkpoint content.", False, True),
            )),
            "domain_errors_complete": True,
        })
    if governed.id.startswith("simulation.vm_diff_"):
        updates.update({
            "business_effect": "Generate or read an immutable deterministic node-level difference report between two governed VM checkpoints.",
            "business_acceptance_criteria": (
                "Both source checkpoints are caller-visible and belong to the same Simulation workspace.",
                "Identity ambiguity is reported for review and is never resolved by guessing.",
                "Repeated generation for the same snapshot pair and algorithm returns the same immutable report.",
            ),
            "business_invariants": (), "no_business_invariant_reason": _CONNECTOR_READ_REASON,
            "domain_errors": (
                DomainErrorContract(code="vm_checkpoint_not_found", meaning="One or both source checkpoints are unavailable.", is_caller_error=True),
                DomainErrorContract(code="vm_diff_workspace_mismatch", meaning="The checkpoints belong to different workspaces.", is_caller_error=True),
                DomainErrorContract(code="vm_diff_report_not_found", meaning="The report is unavailable or unreadable.", is_caller_error=True),
            ), "domain_errors_complete": True,
        })
    if governed.id == "simulation.environment.runtime_package.open.request":
        updates.update({
            "business_effect": "Materialize one exact frozen Simulation environment and queue one App-runtime plan that opens only its generated top-level PLMXML.",
            "business_acceptance_criteria": (
                "The selected workspace version is frozen, caller-visible, and resolves to one immutable runtime model.",
                "Every referenced dependency is staged with its exact Artifact hash before VisMockup opens the generated top-level PLMXML.",
                "The queued plan contains exactly one model-open step and preserves outcome-unknown reconciliation semantics.",
            ),
            "business_invariants": (BusinessInvariantContract(
                rule_id="simulation.environment.runtime_package.single_root", version=1,
                statement="Frozen replay opens exactly one generated top-level PLMXML while its immutable dependencies are staged beside it.",
                applies_when="a frozen Simulation environment is opened in the AI00 App runtime",
                enforcement_ref="plugins/simulation/simulation_backend/capabilities/connector_runtime.py:open_runtime_package",
                error_code="frozen_workspace_version_not_found",
                test_refs=("plugins/simulation/tests/test_plmxml_environment_capabilities.py::test_frozen_runtime_package_prepares_one_top_level_open_with_staged_dependencies",),
            ),),
            "no_business_invariant_reason": None,
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
        or governed.id.startswith("simulation.teamcenter.")
    ):
        is_teamcenter = governed.id.startswith("simulation.teamcenter.")
        updates.update({
            "business_effect": (
                "Validate and persist one exact Connector control-plane operation for the caller-bound Simulation runtime."
                if governed.id.startswith("simulation.connector.")
                else _TEAMCENTER_BUSINESS_EFFECTS[governed.id]
                if is_teamcenter
                else "Queue or read one user-scoped signed VisMockup command through the bound Simulation Connector."
                if governed.id in _VISMOCKUP_WEB_WORKFLOWS
                else "Expose one exact VisMockup adapter atom exclusively to a signed Simulation Connector execution plan."
            ),
            "business_acceptance_criteria": (
                "The operation is scoped to the caller's single bound Simulation Connector.",
                "The closed request and response contracts preserve exact Connector and Adapter identity.",
                "Rejected operations do not create ungoverned Teamcenter product-data or VisMockup side effects.",
            ),
            "business_invariants": (),
            "no_business_invariant_reason": (
                "Identity, contract and execution-plan validation fully determine this atomic boundary; no additional business-state rule is decided here."
            ),
        })
    if governed.id in {"simulation.vismockup.document.identity.read.request",
                       "simulation.vismockup.document.hierarchy_inventory.read.request"} or "live_document" in governed.tags:
        from backend.capability_v2.identity import DESKTOP_CONSUMER_ID
        effects = {
            "simulation.vismockup.document.identity.read.request": "Queue one signed read identifying the active native document on the owner's current App workstation.",
            "simulation.vismockup.document.hierarchy_inventory.read.request": "Queue one signed bounded read of alternate hierarchies from an exact active document session.",
            "simulation.environment.live_document.adopt": ("Bind the owner's already-open native document and register it as the environment's primary live model."
                if governed.version >= 2 else "Bind the owner's already-open native document to one durable private importing environment."),
            "simulation.environment.live_document.binding.get": "Resolve the owner's saved document-to-environment association for document and environment selection.",
            "simulation.environment.live_document.rebind": "Explicitly rotate one owned environment to the freshly attested current native document session while retaining the prior session as history.",
            "simulation.environment.live_document.inventory.apply": "Persist one signed complete page of alternate hierarchies into the bound environment without mutating VisMockup.",
        }
        updates.update(exposure=ExposurePolicy(web=True), execution_mode=ExecutionMode.CLOUD_SYNC,
            lifecycle_status=LifecycleStatus.EXPERIMENTAL,
            business_effect=effects[governed.id],
            business_acceptance_criteria=(
                "Identity is derived only from the caller-owned persisted signed read outcome and current App session.",
                ("Explicit rebind supersedes the prior runtime session, preserves the environment, and never matches by display name."
                 if governed.id.endswith('.rebind') else
                 "Duplicate adoption preserves the same environment and primary live model; AH ingestion remains a separate observed operation."
                 if governed.version >= 2 else "Duplicate adoption preserves the same environment and model/AH ingestion is never implied."),
                "Unavailable or other-owner evidence cannot disclose or create a binding."),
            business_invariants=(BusinessInvariantContract(rule_id="simulation.live_document.attested_identity", version=1,
                statement="A native document adoption uses only fresh signed identity evidence bound to the current owner App session.",
                applies_when="an existing native document is adopted or its identity is resolved",
                enforcement_ref="plugins/simulation/simulation_backend/application/live_document_identity.py:verify_identity_evidence",
                error_code="live_document_identity_unavailable",
                test_refs=("plugins/simulation/tests/test_live_document_identity_evidence.py::test_verifies_only_persisted_signed_identity",)),),
            no_business_invariant_reason=None,
            consumer_refs=({'consumer_id':DESKTOP_CONSUMER_ID,'consumer_type':'web','version_constraint':'==1'},),
            test_refs=({'path':'plugins/simulation/tests/test_live_document_capabilities.py'},
                       {'path':'plugins/simulation/tests/test_live_document_identity_evidence.py'},
                       {'path':'backend/tests/test_simulation_connector_runtime_v2_sql.py'},),
            transaction_policy={
                'owner':'simulation', 'atomicity':(
                    'signed AH page/hierarchies/nodes/workspace revision/idempotency in one repository transaction'
                    if governed.id.endswith('.inventory.apply') else
                    'active binding rotation/primary live model/workspace revision/idempotency in one repository transaction'
                    if governed.id.endswith('.rebind') else
                    'workspace create/version/head/binding/primary live model/idempotency reservation in one repository transaction'
                    if governed.id.endswith('.adopt') and governed.version >= 2 else
                    'workspace create/version/head/binding/idempotency reservation in one repository transaction'
                    if governed.id.endswith('.adopt') else
                    'read or signed queue persistence only; no workspace mutation'),
                'native_atomicity':'identity read and the following binding mutation are not atomic with native document changes',
                'tables': (['workmanship_sim_connector_runtime_plans','workmanship_sim_connector_runtime_devices',
                    'workmanship_sim_live_document_bindings','workmanship_sim_workspaces',
                    'workmanship_sim_vm_documents','workmanship_sim_materialization_verifications',
                    'workmanship_sim_workspace_idempotency'] if governed.id.endswith('.rebind') else
                    ['workmanship_sim_connector_runtime_plans','workmanship_sim_connector_runtime_devices',
                    'workmanship_sim_live_document_bindings','workmanship_sim_live_document_adoptions',
                    'workmanship_sim_workspaces','workmanship_sim_workspace_versions','workmanship_sim_workspace_heads',
                    *(['workmanship_sim_vm_documents'] if ((governed.id.endswith('.adopt') and governed.version >= 2) or governed.id.endswith('.rebind')) else []),
                    *(['workmanship_sim_workspace_hierarchies','workmanship_sim_workspace_nodes']
                      if governed.id.endswith('.inventory.apply') else []),
                    *(['workmanship_sim_workspace_idempotency']
                      if governed.id.endswith('.inventory.apply') or governed.id.endswith('.rebind') else [])]),
                'migration_refs':['backend/db/migrations/domains/simulation/0008_connector_app_runtime_v2.sql',
                    'backend/db/migrations/domains/simulation/0025_simulation_live_document_bindings.sql'],
                'dependencies':['vismockup.document.identity.read@1','vismockup.document.hierarchy_inventory.read@1','simulation.vismockup.command.get@1'],
                'idempotency':('workspace/key plus exact prior and newly attested session' if governed.id.endswith('.rebind') else
                    'owner/tenant/key plus exact device/session/name' + ('/document display name' if governed.version >= 2 else ''))
                    + '; retained responses forbid recreation'},
            domain_errors=tuple(DomainErrorContract(code=code, meaning=meaning) for code, meaning in (
                ('live_document_identity_unavailable','The authenticated native identity cannot be established.'),
                ('live_document_identity_stale','The signed native identity or server receipt is stale.'),
                ('live_document_owner_required','The authenticated web owner and tenant are required.'),
                ('live_document_input_invalid','The closed live document request is invalid.'),
                ('live_document_binding_stale','The prior binding cannot be reused safely.'),
                ('document_session_changed','The saved binding changed before the explicit rebind committed.'),
                ('live_document_already_bound','The newly attested native session belongs to another environment.'),
                ('primary_live_document_unavailable','The selected environment has no unique primary live document to rebind.'),
                ('idempotency_conflict','The request key was already used for different adoption input.'),
                ('runtime_v2_required','A current App v2 runtime is required.'))), domain_errors_complete=False)
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

    # Preserve the Provider's transaction-participant declaration through the
    # governance context adapter.  The Gateway inspects the registered
    # callable (the wrapper), not the original bound method.
    if getattr(handler, "__capability_transactional__", False):
        governed_handler.__capability_transactional__ = True

    registry.register(governed, governed_handler, descriptor=descriptor)


__all__ = ["descriptor_for", "register"]

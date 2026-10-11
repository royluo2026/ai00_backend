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
    "simulation.teamcenter.node_properties.read.request",
    "simulation.teamcenter.product_structure.children.read.request",
    "simulation.teamcenter.product.search.request",
    "simulation.teamcenter.revision_rule.search.request",
    "simulation.teamcenter.product_structure.observe.request",
    "simulation.teamcenter.product_structure.page.read.request",
    "simulation.teamcenter.visualization.launch.request",
    "simulation.teamcenter.visualization.insert.request",
    "simulation.vismockup.document.identity.read.request",
    "simulation.vismockup.document.existing_identity.read.request",
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
    "simulation.teamcenter.model_file.fetch": "Acquire one exact cached JT ImanFile through FMS and publish verified immutable bytes without opening a viewer.",
    "simulation.teamcenter.model_files.size.preflight": "Read the byte sizes of up to eight exact cached Teamcenter ImanFiles before bounded JT acquisition.",
    "simulation.teamcenter.model_cache.read": "Read one TC cache page pinned to the authenticated TC principal, preserving every returned raw property field and read state.",
    "simulation.teamcenter.node_properties.read.request": "Queue a read of the fixed display-property projection for one exact Teamcenter occurrence, preferring the current principal's local Connector cache.",
    "simulation.teamcenter.node_properties.read": "Return the fixed display-property projection for one exact Teamcenter occurrence with source identity, capture time and authoritative cache-hit evidence.",
    "simulation.teamcenter.product_structure.children.read.request": "Queue a read-only generation-pinned page of direct children for one exact Teamcenter source and occurrence path.",
    "simulation.teamcenter.product_structure.children.read": "Return the requested parent and a bounded page of direct children with source identity, cache age, generation and explicit incomplete-tree semantics.",
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
    "simulation.teamcenter.node_properties.read.request": (("teamcenter-endpoint", "source_selector.endpoint_id"), ("teamcenter-online-source", "source_selector.object_uid")),
    "simulation.teamcenter.node_properties.read": (("teamcenter-endpoint", "source_selector.endpoint_id"), ("teamcenter-online-source", "source_selector.object_uid")),
    'simulation.connector.recovery.search': (),
    'simulation.connector.recovery.resolve': (('simulation-connector', 'device_id'), ('simulation-connector-command', 'plan_id')),
    "simulation.teamcenter.product_structure.children.read.request": (("teamcenter-endpoint", "source_selector.endpoint_id"), ("teamcenter-online-source", "source_selector.object_uid")),
    "simulation.teamcenter.product_structure.children.read": (("teamcenter-endpoint", "source_selector.endpoint_id"), ("teamcenter-online-source", "source_selector.object_uid")),
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
    "simulation.environment.cache_source.materialization.inspect": (("simulation-workspace", "workspace_gid"),),
    "simulation.environment.cache_source.open.request": (("simulation-workspace", "workspace_gid"),),
    "simulation.environment.cache_source.bind": (("simulation-workspace", "workspace_gid"),),
    "simulation.environment.cache_source.live_document.bind": (("simulation-workspace", "workspace_gid"),),
    "simulation.environment.cache_source.live_document.resume": (("simulation-workspace", "workspace_gid"),),
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
    "simulation.environment.live_document.resume_online": (("simulation-workspace", "workspace_gid"),),
    "simulation.environment.online_source.live_document.bind": (("simulation-workspace", "workspace_gid"),),
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

_TEAMCENTER_NODE_PROPERTY_CAPABILITIES = frozenset({
    "simulation.teamcenter.node_properties.read.request",
    "simulation.teamcenter.node_properties.read",
})
_TEAMCENTER_NODE_PROPERTY_ERROR_PAIRS = (
    ("teamcenter_login_required", "The current Connector process has no authenticated in-memory Teamcenter session."),
    ("teamcenter_input_invalid", "The Teamcenter request envelope is malformed."),
    ("teamcenter_source_selector_invalid", "The Teamcenter source selector is incomplete or invalid."),
    ("teamcenter_node_properties_input_invalid", "The occurrence path or fixed node-property request is invalid."),
    ("teamcenter_node_properties_cache_invalid", "The local node-property cache entry is corrupt, open-ended, or belongs to another occurrence."),
    ("teamcenter_worker_response_invalid", "The Teamcenter worker returned an invalid or open-ended response."),
    ("teamcenter_authentication_failed", "Teamcenter rejected the current authentication attempt."),
    ("teamcenter_session_expired", "The in-memory Teamcenter session expired and must be authenticated again."),
    ("teamcenter_runtime_unavailable", "The supported Teamcenter runtime is unavailable on the Connector host."),
    ("teamcenter_worker_start_failed", "The bounded Teamcenter worker process could not be started."),
    ("teamcenter_timeout", "The bounded Teamcenter read exceeded its execution deadline."),
    ("teamcenter_worker_response_too_large", "The Teamcenter worker response exceeded the governed size limit."),
    ("teamcenter_worker_command_forbidden", "The worker rejected an operation outside its fixed read-only allowlist."),
    ("teamcenter_worker_failed", "The Teamcenter worker failed before producing a valid result."),
    ("teamcenter_source_not_found", "The exact Teamcenter source object is unavailable."),
    ("teamcenter_bom_window_failed", "Teamcenter could not create the read-only BOM window for the selected source."),
    ("teamcenter_parent_path_not_found", "The exact parent occurrence path no longer resolves in Teamcenter."),
    ("teamcenter_occurrence_identity_invalid", "Teamcenter returned an invalid occurrence identity while walking the path."),
    ("teamcenter_structure_expand_failed", "Teamcenter could not expand the requested occurrence."),
    ("teamcenter_structure_properties_failed", "Teamcenter could not read the fixed property projection."),
    ("teamcenter_structure_response_invalid", "Teamcenter returned an invalid structure response."),
)
_TEAMCENTER_NODE_PROPERTY_RETRYABLE_ERRORS = frozenset({
    "teamcenter_login_required",
    "teamcenter_session_expired",
    "teamcenter_runtime_unavailable",
    "teamcenter_worker_start_failed",
    "teamcenter_timeout",
    "teamcenter_worker_failed",
    "teamcenter_bom_window_failed",
    "teamcenter_structure_expand_failed",
    "teamcenter_structure_properties_failed",
})
_TEAMCENTER_NODE_PROPERTY_CALLER_ERRORS = frozenset({
    "teamcenter_input_invalid",
    "teamcenter_source_selector_invalid",
    "teamcenter_node_properties_input_invalid",
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
            if governed.id.startswith('simulation.viewer.interaction.') or governed.id in {
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
    if governed.id in _TEAMCENTER_NODE_PROPERTY_CAPABILITIES:
        updates.update({
            "domain_errors": tuple(updates["domain_errors"]) + tuple(
                DomainErrorContract(
                    code=code,
                    meaning=meaning,
                    retryable=code in _TEAMCENTER_NODE_PROPERTY_RETRYABLE_ERRORS,
                    is_caller_error=code in _TEAMCENTER_NODE_PROPERTY_CALLER_ERRORS,
                )
                for code, meaning in _TEAMCENTER_NODE_PROPERTY_ERROR_PAIRS
            ),
            # Worker/runtime diagnostics can evolve independently; this list is
            # intentionally useful and stable without claiming exhaustiveness.
            "domain_errors_complete": False,
        })
    if governed.id in _TWO_PHASE_ENTRYPOINTS and governed.version == 1:
        updates.update({
            "exposure": ExposurePolicy(),
            "agent_output_schema": None,
            "deprecation_message": f"Immediate dispatch is closed; migrate to {governed.id}@2 and its action/dispatch workflow.",
            "no_consumer_reason": "The unsafe immediate-dispatch contract is frozen with no verified runtime consumer and accepts no new traffic.",
        })
    if governed.id.startswith('simulation.connector.recovery.'):
        from backend.capability_v2.identity import DESKTOP_CONSUMER_ID
        updates.update({
            'exposure': ExposurePolicy(web=True),
            'delegation_policy': 'none',
            'consistency_policy': 'strong',
            'replay_data_policy': 'projected' if governed.id.endswith('.resolve') else 'metadata_only',
            'execution_mode': ExecutionMode.CLOUD_SYNC,
            'consumer_refs': ({'consumer_id': DESKTOP_CONSUMER_ID, 'consumer_type': 'web', 'version_constraint': '==1'},),
            'test_refs': ({'path': 'backend/tests/test_simulation_connector_runtime_v2_sql.py'},),
            'transaction_policy': {
                'owner': 'simulation',
                'atomicity': ('One bounded owner-scoped read with no writes.' if governed.id.endswith('.search') else
                    'Device lock then exact plan lock; status and append-only human disposition audit commit together.'),
                'tables': ['workmanship_sim_connector_runtime_devices', 'workmanship_sim_connector_runtime_plans',
                           'workmanship_sim_connector_runtime_audit'],
                'migration_refs': ['backend/db/migrations/domains/simulation/0027_connector_manual_recovery_status.sql'],
                'idempotency': 'Exact device/plan/generation/expected outcome hash/expected plan hash/expected recovery fingerprint/decision/reason replays one audit reference; differing dispositions refuse. Missing new fields in historical audits normalize to null.',
                'native_atomicity': 'A human disposition does not assert a native result or mutate native documents.',
            },
            'business_effect': ('Return a stable, counted page of owner-visible unresolved Connector operations for human review.'
                if governed.id.endswith('.search') else
                'Close one exact uncertain Connector plan with an audited human disposition or abandonment while preserving any recorded runtime outcome.'),
            'business_acceptance_criteria': (
                'Only the authenticated web device owner in the same tenant may review the operation.',
                'The signed outcome remains immutable; review never retries execution or proves successful document association.',
                'Executed/not_executed decisions require one operation with an outcome hash: document open/insert; probe allow_launch=true; visibility all_on/all_off; node visibility show/hide/isolate; node selection highlight/select/unhighlight/deselect.',
                'Abandoned archives an exact plan, including unsupported operations/actions, multiple steps, missing hashes or malformed stored JSON, without asserting execution, retrying, or reversing external side effects.',
                'Every unresolved item has a durable recovery_fingerprint and at least abandoned; only a parseable known bounded operation with a stored outcome hash also allows executed/not_executed. Malformed plan JSON is exposed safely as unknown_operation rather than breaking the page.',
                'The recovery fingerprint hashes stored device/plan identity, generation, status, raw plan JSON, both hashes, raw outcome, protocol, actor and tenant. Any supplied fingerprint is checked under the device and plan locks; hashless abandonment requires it. Exact historical replay uses the recorded disposition before rechecking the now-cancelled status fingerprint.',
                'An existing valid outcome hash still requires the exact expected_outcome_hash for legacy clients. Supplied plan hashes must match. Without an outcome, only abandonment with exact plan hash or fingerprint is allowed. Missing optional hashes/fingerprint are omitted in requests, never JSON null; audits record all three expected values including nulls.',
                'Search defaults to page 1 with five items, allows 1..20 items per page, and counts and pages the same owner/tenant/current-generation unresolved scope within one SQL statement snapshot ordered by created_at and plan_id. Out-of-range pages are empty with truthful totals.',
            ),
            'business_invariants': (BusinessInvariantContract(
                rule_id='simulation.connector.recovery.owner_exact_outcome', version=1,
                statement=('Search exposes at most the requested page size (maximum twenty) with an exact scoped total, stable created_at/plan_id ordering, and matching owner, tenant and current generation.'
                    if governed.id.endswith('.search') else
                    'Human review is owner and tenant scoped and binds exact generation plus stored outcome identity or a locked recovery fingerprint for hashless abandonment; executed/not_executed require one bounded operation and outcome hash; conflicting decisions refuse without side effects.'),
                applies_when='an unresolved Connector operation is reviewed',
                enforcement_ref='plugins/simulation/simulation_backend/data/connector_repository.py:SimulationConnectorRepository.' +
                    ('search_manual_recovery' if governed.id.endswith('.search') else 'resolve_manual_recovery'),
                error_code='runtime_owner_mismatch' if governed.id.endswith('.search') else 'recovery_state_changed',
                test_refs=('backend/tests/test_simulation_connector_runtime_v2_sql.py::test_manual_recovery_preserves_signed_outcome_and_replays',
                           'backend/tests/test_simulation_connector_runtime_v2_sql.py::test_manual_recovery_refuses_wrong_owner_or_stale_state',
                           'backend/tests/test_simulation_connector_runtime_v2_sql.py::test_manual_recovery_bounded_actions_release_unresolved_blocker',
                           'backend/tests/test_simulation_connector_runtime_v2_sql.py::test_manual_recovery_ineligible_reasons_refuse_without_mutation',
                           'backend/tests/test_simulation_connector_runtime_v2_sql.py::test_manual_recovery_abandoned_archives_exact_plan_without_claiming_execution',
                           'backend/tests/test_simulation_connector_runtime_v2_sql.py::test_manual_recovery_search_paginates_scoped_stable_results',
                           'backend/tests/test_simulation_connector_runtime_v2_sql.py::test_manual_recovery_search_count_and_page_share_one_statement',
                           'backend/tests/test_simulation_connector_runtime_v2_sql.py::test_manual_recovery_missing_outcome_requires_exact_plan_identity',
                           'backend/tests/test_simulation_connector_runtime_v2_sql.py::test_manual_recovery_result_hash_still_required_and_old_audit_replays',
                           'backend/tests/test_simulation_connector_runtime_v2_sql.py::test_manual_recovery_fingerprint_archives_damaged_plan_and_refuses_stale_snapshot',
                           'backend/tests/test_simulation_connector_runtime_v2_sql.py::test_manual_recovery_fingerprint_binds_each_storage_identity_field',
                           'backend/tests/test_connector_recovery_gateway_transaction.py::test_recovery_gateway_plan_hash_only_abandonment_binds_confirmation'),
            ),),
            'no_business_invariant_reason': None,
            'domain_errors': tuple(DomainErrorContract(code=code, meaning=meaning, is_caller_error=True)
                for code, meaning in (
                    ('runtime_owner_mismatch', 'The device and plan must belong to the authenticated user and tenant.'),
                    ('runtime_session_invalid', 'The device must be active and use runtime protocol v2.'),
                    ('recovery_confirmation_required', 'An exact user confirmation is required.'),
                    ('recovery_input_invalid', 'Search requires integer page >= 1 and page_size 1..20; resolve requires a valid decision, correctly formatted expected hashes and nonempty bounded reason.'),
                    ('recovery_state_changed', 'The generation, required outcome/plan identity, recovery fingerprint or unresolved plan state is missing or changed; read it again.'),
                    ('recovery_decision_conflict', 'A different human disposition has already been recorded.'),
                    ('recovery_operation_unsupported', 'The selected decision is not allowed for this exact plan; unsupported, multi-step, malformed or outcome-less plans may only be abandoned using their exact recovery identity.'),
                )),
            'domain_errors_complete': True,
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
                "Preview the exact published or explicitly selected active Craft BOP hierarchy at the selected depth for insertion into one owned Simulation environment."
                if governed.id.endswith(".preview") else
                "Atomically insert the previously previewed exact Craft BOP hierarchy at the selected depth as one editable alternate hierarchy."
            ),
            "business_acceptance_criteria": (
                "The source is read only through Craft's revision-pinned execution structure contract: published versions use get@1 and an explicitly selected active version uses preview@1 after resolving its current revision.",
                "All depth preserves every actual source BOP node and its parentage, including parts and resources, up to 20000 nodes; bounded process depths retain their existing truncation semantics.",
                "Product and resource references remain separate source references and never generate additional or duplicate hierarchy nodes.",
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
    if not governed.id.startswith('simulation.connector.recovery.') and (
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
                       "simulation.vismockup.document.existing_identity.read.request",
                       "simulation.vismockup.document.hierarchy_inventory.read.request"} or "live_document" in governed.tags:
        from backend.capability_v2.identity import DESKTOP_CONSUMER_ID
        effects = {
            "simulation.environment.cache_source.live_document.bind": "Bind the exact frozen-cache package and returned native document identity without changing the cached source.",
            "simulation.environment.cache_source.live_document.resume": "Renew only the current-runtime association and grant for the exact already-open frozen-cache document.",
            "simulation.vismockup.document.identity.read.request": "Queue one signed read identifying the active native document on the owner's current App workstation.",
            "simulation.vismockup.document.existing_identity.read.request": "Select an already-open VisMockup document by exact native session and persist its signed identity in the current App runtime.",
            "simulation.vismockup.document.hierarchy_inventory.read.request": "Queue one signed bounded read of alternate hierarchies from an exact active document session.",
            "simulation.environment.live_document.adopt": ("Bind the owner's already-open native document and register it as the environment's primary live model."
                if governed.version >= 2 else "Bind the owner's already-open native document to one durable private importing environment."),
            "simulation.environment.live_document.binding.get": "Resolve the owner's saved document-to-environment association for document and environment selection.",
                "simulation.environment.live_document.rebind": "Explicitly rotate one owned environment to the freshly attested current native document session while retaining the prior session as history.",
                "simulation.environment.live_document.resume_online": "Renew the current runtime source association for the exact already-bound Teamcenter online document without opening a model.",
                "simulation.environment.online_source.live_document.bind": "Bind one user-confirmed Teamcenter online-source launch to the exact freshly attested VisMockup document without replacing its Teamcenter source identity.",
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
                        'signed Teamcenter launch/current document identity/live binding/online model runtime device/workspace revision/idempotency in one repository transaction'
                        if governed.id.endswith('online_source.live_document.bind') else
                    'workspace create/version/head/binding/primary live model/idempotency reservation in one repository transaction'
                    if governed.id.endswith('.adopt') and governed.version >= 2 else
                    'workspace create/version/head/binding/idempotency reservation in one repository transaction'
                    if governed.id.endswith('.adopt') else
                    'read or signed queue persistence only; no workspace mutation'),
                'native_atomicity':'identity read and the following binding mutation are not atomic with native document changes',
                'tables': (['workmanship_sim_connector_runtime_plans','workmanship_sim_connector_runtime_devices',
                    'workmanship_sim_live_document_bindings','workmanship_sim_workspaces',
                    'workmanship_sim_vm_documents','workmanship_sim_materialization_verifications',
                        'workmanship_sim_workspace_idempotency'] if (governed.id.endswith('.rebind') or governed.id.endswith('online_source.live_document.bind')) else
                    ['workmanship_sim_connector_runtime_plans','workmanship_sim_connector_runtime_devices',
                    'workmanship_sim_live_document_bindings','workmanship_sim_live_document_adoptions',
                    'workmanship_sim_workspaces','workmanship_sim_workspace_versions','workmanship_sim_workspace_heads',
                        *(['workmanship_sim_vm_documents'] if ((governed.id.endswith('.adopt') and governed.version >= 2) or governed.id.endswith('.rebind') or governed.id.endswith('online_source.live_document.bind')) else []),
                    *(['workmanship_sim_workspace_hierarchies','workmanship_sim_workspace_nodes']
                      if governed.id.endswith('.inventory.apply') else []),
                    *(['workmanship_sim_workspace_idempotency']
                          if governed.id.endswith('.inventory.apply') or governed.id.endswith('.rebind') or governed.id.endswith('online_source.live_document.bind') else [])]),
                'migration_refs':['backend/db/migrations/domains/simulation/0008_connector_app_runtime_v2.sql',
                    'backend/db/migrations/domains/simulation/0025_simulation_live_document_bindings.sql'],
                    'dependencies':['vismockup.document.identity.read@1','vismockup.document.hierarchy_inventory.read@1','teamcenter.visualization.launch@1','simulation.vismockup.command.get@1'],
                    'idempotency':('workspace/key plus exact signed launch source and freshly attested document session' if governed.id.endswith('online_source.live_document.bind') else
                        'workspace/key plus exact prior and newly attested session' if governed.id.endswith('.rebind') else
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
                    ('live_document_binding_conflict','The selected environment already has another active native session.'),
                    ('launch_evidence_unavailable','The signed Teamcenter launch result is unavailable or invalid.'),
                    ('launch_evidence_stale','The signed Teamcenter launch result is stale.'),
                    ('launch_document_device_mismatch','The launch and current native document were attested by different Connector devices.'),
                    ('online_model_document_not_found','The selected primary Teamcenter online-source document is unavailable.'),
                    ('online_source_identity_mismatch','The signed launch source does not match the selected online-source document.'),
                ('primary_live_document_unavailable','The selected environment has no unique primary live document to rebind.'),
                ('idempotency_conflict','The request key was already used for different adoption input.'),
                ('runtime_v2_required','A current App v2 runtime is required.'))), domain_errors_complete=False)
    if governed.id == 'simulation.vismockup.document.existing_identity.read.request':
        updates.update(
            business_acceptance_criteria=(
                'The Connector selects only an already-open document whose native session equals the requested saved session.',
                'The signed identity result is scoped to the current owner runtime; mismatched or missing documents fail closed.',
                'No Teamcenter launch or model opening occurs.'),
            business_invariants=(BusinessInvariantContract(rule_id='simulation.viewer.existing_identity', version=1,
                statement='An existing native document identity is accepted only from a fresh signed current-runtime outcome for the exact requested session.',
                applies_when='the owner reads an already-open document identity for runtime resumption',
                enforcement_ref='plugins/simulation/simulation_backend/application/live_document_identity.py:verify_existing_identity_evidence',
                error_code='live_document_identity_unavailable',
                test_refs=('plugins/simulation/tests/test_live_document_identity_evidence.py::test_existing_document_identity_is_pinned_to_requested_session_and_current_runtime',)),),
            test_refs=({'path':'plugins/simulation/tests/test_live_document_identity_evidence.py'},),
            transaction_policy={**updates['transaction_policy'],
                'dependencies':['vismockup.document.existing_identity.read@1'],
                'idempotency':'owner/runtime/request key and exact expected native document session'})
    if governed.id == 'simulation.environment.live_document.resume_online':
        updates.update(
            business_acceptance_criteria=(
                'The signed existing-document identity is fresh and belongs to the current owner App runtime.',
                'The saved binding, active prior source association, source revision and primary Teamcenter document match exactly.',
                'Only the runtime source association changes; no model is opened and no workspace content revision changes.'),
            business_invariants=(BusinessInvariantContract(rule_id='simulation.viewer.existing_document_resume', version=1,
                statement='Only an exact already-bound Teamcenter document with a fresh signed current-runtime native identity can renew its source association.',
                applies_when='an owner resumes local control of an already-open online-source document',
                enforcement_ref='plugins/simulation/simulation_backend/data/workspace_repository.py:resume_online_live_document',
                error_code='live_document_identity_mismatch',
                test_refs=('plugins/simulation/tests/test_live_document_resume.py::test_resume_rejects_wrong_source_or_session',)),),
            test_refs=({'path':'plugins/simulation/tests/test_live_document_resume.py'},),
            transaction_policy={**updates['transaction_policy'],
                'atomicity':'signed current-runtime identity/owned binding/prior source revision check and association/idempotency renewal in one transaction',
                'tables':['workmanship_sim_connector_runtime_plans','workmanship_sim_connector_runtime_devices',
                    'workmanship_sim_workspaces','workmanship_sim_vm_documents',
                    'workmanship_sim_live_document_bindings','workmanship_sim_viewer_source_associations',
                    'workmanship_sim_workspace_idempotency'],
                'migration_refs':['backend/db/migrations/domains/simulation/0028_viewer_interaction.sql'],
                'dependencies':['vismockup.document.existing_identity.read@1','simulation.environment.online_source.live_document.bind@3'],
                'idempotency':'workspace/key plus exact signed identity operation, document session and expected workspace revision'})
    if governed.id.startswith('simulation.viewer.interaction.'):
        from backend.capability_v2.identity import DESKTOP_CONSUMER_ID
        updates.update(
            exposure=ExposurePolicy(web=True), execution_mode=ExecutionMode.CLOUD_SYNC,
            lifecycle_status=LifecycleStatus.EXPERIMENTAL,
            business_effect=('Resolve the current verified source association for one owner workspace document.'
                if governed.id.endswith('scope.get') else
                'Issue a 60-second signed local interaction grant scoped to the current owner, device, source and opened document.'),
            business_acceptance_criteria=(
                'The workspace, primary online-source document, active binding and current runtime belong to the authenticated owner and tenant.',
                'Caller input cannot select device, runtime, operations, actor, tenant or authorization lifetime.',
                'Renewal retains the same session nonce and allocates a strictly increasing generation only after current-scope revalidation.'),
            business_invariants=(BusinessInvariantContract(rule_id='simulation.viewer.interaction.current_source', version=1,
                statement='Local interaction authority exists only for one active verified source association and authenticated runtime.',
                applies_when='an owner resolves or authorizes a local viewer interaction',
                enforcement_ref='plugins/simulation/simulation_backend/data/viewer_interaction_repository.py:authorize_scope',
                error_code='interaction_binding_stale', test_refs=('backend/tests/test_viewer_interaction_repository.py::test_current_association_fails_closed_after_scope_changes',)),),
            no_business_invariant_reason=None,
            consumer_refs=({'consumer_id':DESKTOP_CONSUMER_ID, 'consumer_type':'web', 'version_constraint':'==1'},),
            test_refs=({'path':'plugins/simulation/tests/test_viewer_interaction_provider.py'},
                {'path':'backend/tests/test_viewer_interaction_repository.py'}, {'path':'backend/tests/test_viewer_interaction_audit.py'}),
            transaction_policy=dict(owner='simulation', atomicity='workspace/source/runtime/binding checks and generation allocation through signing in one transaction',
                tables=['workmanship_sim_viewer_source_associations', 'workmanship_sim_viewer_interaction_grants', 'workmanship_sim_viewer_grant_evidence'],
                migration_refs=['backend/db/migrations/domains/simulation/0028_viewer_interaction.sql', 'backend/db/migrations/domains/simulation/0029_viewer_grant_evidence.sql'],
                dependencies=['simulation.environment.online_source.live_document.bind@2'],
                idempotency='source association/session nonce/prior grant; stale renewals rejected'),
            domain_errors=tuple(DomainErrorContract(code=code, meaning=meaning) for code, meaning in (
                ('interaction_scope_denied', 'The caller does not own a current permitted source scope.'),
                ('interaction_binding_stale', 'The source, document binding or current runtime changed.'),
                ('interaction_renewal_stale', 'The prior grant is not the latest grant for this session.'),
                ('interaction_signer_unavailable', 'Trusted grant signing material is unavailable.'),
                ('interaction_catalog_binding_unavailable', 'Exact trusted authorization or operation Catalog binding is unavailable.'),
                ('interaction_authorization_rejected', 'The closed request or trusted signer rejected the grant.'))),
            domain_errors_complete=False)
    if governed.id == 'simulation.environment.online_source.live_document.bind' and governed.version in (2, 3):
        updates.update(
            business_effect='Atomically bind one verified launch major 2 source/document receipt and persist its local interaction source association.',
            business_acceptance_criteria=(
                'The signed current-open receipt binds source selector and document identity to the same fresh owner runtime.',
                'Source association, live binding, document device, workspace revision and idempotency result commit or roll back together.',
                'No independent identity read or saved environment document identity is required.'),
            business_invariants=(BusinessInvariantContract(rule_id='simulation.viewer.current_open_receipt', version=1,
                statement='A source association is established only from a verified signed current-open launch receipt.',
                applies_when='an online source is bound for local interaction',
                enforcement_ref='plugins/simulation/simulation_backend/data/connector_repository.py:verified_teamcenter_opened_source_evidence',
                error_code='launch_evidence_unavailable', test_refs=('plugins/simulation/tests/test_viewer_opened_source_binding.py::test_current_open_receipt_atomically_binds_source_and_idempotent_association',)),),
            consumer_refs=tuple({**ref, 'version_constraint':f'=={governed.version}'} for ref in updates['consumer_refs']),
            test_refs=({'path':'plugins/simulation/tests/test_viewer_opened_source_binding.py'},),
            transaction_policy={**updates['transaction_policy'],
                'atomicity':'verified opened-source evidence/source association/live binding/document/workspace revision/idempotency in one transaction',
                'tables':[*updates['transaction_policy']['tables'], 'workmanship_sim_viewer_source_associations'],
                'migration_refs':[*updates['transaction_policy']['migration_refs'], 'backend/db/migrations/domains/simulation/0028_viewer_interaction.sql'],
                'dependencies':['teamcenter.visualization.launch@2'],
                'idempotency':'workspace/key plus launch receipt/runtime/document/source and expected workspace revision'})
        if governed.version == 3:
            updates.update(
                business_effect='Atomically complete a verified current open, bind its source and issue a signed local interaction grant.',
                business_acceptance_criteria=(*updates['business_acceptance_criteria'],
                    'Binding, grant signature, exact issuer proof and immutable completion result commit or roll back together.',
                    'A repeated completion key and nonce returns the same result without another open or grant allocation.'),
                test_refs=({'path':'plugins/simulation/tests/test_viewer_open_completion.py'},),
                transaction_policy={**updates['transaction_policy'],
                    'atomicity':'source binding/revision/association/grant/signature/proof/idempotent completion in one transaction',
                    'tables':[*updates['transaction_policy']['tables'], 'workmanship_sim_viewer_interaction_grants', 'workmanship_sim_viewer_grant_evidence'],
                    'migration_refs':[*updates['transaction_policy']['migration_refs'], 'backend/db/migrations/domains/simulation/0029_viewer_grant_evidence.sql'],
                    'idempotency':'workspace/key plus launch operation/document/expected revision/Main nonce; immutable replay, nonce conflict rejected'})
    if governed.id == 'simulation.environment.cache_source.live_document.bind':
        updates.update(
            concurrency_policy='expected_version', expected_version_payload_path='expected_workspace_row_version',
            business_effect='Atomically bind an attested frozen-cache package open and issue its exact document interaction grant.',
            business_acceptance_criteria=(
                'The completed signed open receipt matches the pinned cache batch, package and current owner runtime.',
                'The cache source is preserved; no online selector or independent active-window identity is substituted.',
                'Binding, source association, revision, signed grant proof and immutable idempotent result commit together.'),
            business_invariants=(BusinessInvariantContract(rule_id='simulation.viewer.cache_open_receipt',version=1,
                statement='A cached source association requires a verified signed package-open receipt matching its immutable batch identity.',
                applies_when='a cached model document is bound for local interaction',
                enforcement_ref='plugins/simulation/simulation_backend/application/cache_open_evidence.py',
                error_code='cache_open_evidence_unavailable',
                test_refs=('plugins/simulation/tests/test_cache_open_evidence.py',)),),
            no_business_invariant_reason=None,
            test_refs=({'path':'plugins/simulation/tests/test_cache_open_evidence.py'},),
            transaction_policy={**updates['transaction_policy'],
                'atomicity':'cache binding/package/association/workspace revision/grant proof/idempotent completion in one transaction',
                'tables':['workmanship_sim_workspaces','workmanship_sim_vm_documents','workmanship_sim_live_document_bindings',
                    'workmanship_sim_connector_runtime_plans','workmanship_sim_connector_runtime_devices',
                    'workmanship_sim_viewer_source_associations','workmanship_sim_viewer_interaction_grants',
                    'workmanship_sim_viewer_grant_evidence','workmanship_sim_workspace_idempotency'],
                'migration_refs':['backend/db/migrations/domains/simulation/0028_viewer_interaction.sql',
                    'backend/db/migrations/domains/simulation/0029_viewer_grant_evidence.sql'],
                'dependencies':['vismockup.model.open@3'],
                'idempotency':'workspace/key plus exact cache open operation/document/revision/Main nonce'})
    if governed.id == 'simulation.environment.cache_source.live_document.resume':
        updates.update(
            concurrency_policy='expected_version', expected_version_payload_path='expected_workspace_row_version',
            business_acceptance_criteria=(
                'Fresh signed existing-document identity matches the same owned device and bound native session.',
                'Frozen batch/package/content and the active prior source revision match without another model open.',
                'Association, signed grant and nonce-bound replay commit atomically without changing workspace content.'),
            business_invariants=(BusinessInvariantContract(rule_id='simulation.viewer.cache_document_resume', version=1,
                statement='Only a fresh current-runtime native identity and unchanged frozen source can renew cached control.',
                applies_when='an already-open cached document is resumed after environment selection',
                enforcement_ref='plugins/simulation/simulation_backend/data/workspace_repository.py:resume_cache_live_document',
                error_code='cache_source_identity_mismatch',
                test_refs=('plugins/simulation/tests/test_cache_document_resume.py::test_resume_cache_rejects_changed_pins',)),),
            test_refs=({'path':'plugins/simulation/tests/test_cache_document_resume.py'},),
            transaction_policy={**updates['transaction_policy'],
                'atomicity':'signed current-runtime identity/immutable package/prior source/grant proof/idempotent completion in one transaction',
                'tables':['workmanship_sim_connector_runtime_plans','workmanship_sim_connector_runtime_devices',
                    'workmanship_sim_workspaces','workmanship_sim_vm_documents','workmanship_sim_live_document_bindings',
                    'workmanship_sim_viewer_source_associations','workmanship_sim_viewer_interaction_grants',
                    'workmanship_sim_viewer_grant_evidence','workmanship_sim_workspace_idempotency'],
                'migration_refs':['backend/db/migrations/domains/simulation/0028_viewer_interaction.sql',
                    'backend/db/migrations/domains/simulation/0029_viewer_grant_evidence.sql'],
                'dependencies':['vismockup.document.existing_identity.read@1','simulation.environment.cache_source.live_document.bind@1'],
                'idempotency':'workspace/key plus exact signed identity/document/session/revision/Main nonce; immutable replay'})
    if governed.id == 'simulation.teamcenter.model_cache.read':
        bulk=governed.version==2
        updates.update(
            exposure=ExposurePolicy(local_runtime=True),
            timeout_seconds=600,
            lifecycle_status=LifecycleStatus.EXPERIMENTAL,
            consumer_refs=({'consumer_id':'simulation.model_cache.advance','consumer_type':'worker','version_constraint':'==1'},),
            business_acceptance_criteria=(
                'Only a signed read-only Connector execution plan invokes this atom.',
                'The expected TC principal, source selector and occurrence path remain fixed throughout the read.',
                'Raw TC fields preserve object identity, field names, JSON values and unavailable/null read states.'),
            business_invariants=(BusinessInvariantContract(rule_id='simulation.model_cache.principal_pinned',version=1,
                statement='Every page belongs to the same TC principal and Connector device as the durable batch.',
                applies_when='a shared cache reads a TC page',
                enforcement_ref='local-runtime/src/Ai00.Connector.Adapters.VisMockup/TeamcenterBulkModelCache.cs:ReadModelCacheV2Async' if bulk else 'local-runtime/src/Ai00.Connector.Adapters.VisMockup/TeamcenterModelCache.cs:ReadModelCacheAsync',
                error_code='cache_principal_changed',test_refs=('plugins/simulation/tests/test_cloud_model_cache.py::test_principal_change_rolls_back',)),),
            no_business_invariant_reason=None,
            test_refs=({'path':'local-runtime/tests/Ai00.Connector.Tests/TeamcenterBulkModelCacheTests.cs'}, {'path':'local-runtime/tests/teamcenter_bulk_cache.test.cjs'}) if bulk else ({'path':'plugins/simulation/tests/test_cloud_model_cache.py'},),
            transaction_policy={'owner':'simulation','atomicity':'read-only TC access; principal-scoped local SQLite staging; complete durable topology and replay-stable property pages' if bulk else 'read-only TC access; principal-scoped local SQLite cache',
                'dependencies':['teamcenter.product_structure.children.read@1'],
                'contract_refs':[f'docs/contracts/teamcenter.model_cache.read@{governed.version}.json']},
            domain_errors=(DomainErrorContract(code='cache_principal_changed',meaning='TC login changed; start a new batch.'),),
            domain_errors_complete=False)
        if bulk:
            updates.update(business_effect=governed.description,
                execution_budget={**descriptor.execution_budget.model_dump(),'max_output_bytes':16*1024*1024,'memory_class':'large','collection_policy':'paged','max_page_size':500},
                business_acceptance_criteria=(*updates['business_acceptance_criteria'],
                    'Each new durable capture reads a fresh configured BOM; repeated occurrence instances preserve exact parent paths.',
                    'A saved page replays identical bytes without TC; unfinished blocks rebuild and compare the full topology after reconnection.',
                    'Native and escaped output pages obey independent byte limits; unavailable optional fields retain explicit states.'))
    if governed.id.startswith('simulation.model_cache.'):
        from .cloud_model_cache import WORKER_ID
        from backend.capability_v2.identity import DESKTOP_CONSUMER_ID
        advance = governed.id.endswith('.advance')
        control = governed.id.endswith('.control')
        updates.update(
            exposure=ExposurePolicy(web=not advance, worker=advance),
            timeout_seconds=600 if advance else 300 if governed.id.endswith('.query') else 30,
            execution_budget={**descriptor.execution_budget.model_dump(),
                'memory_class':'medium' if advance or governed.id.endswith('.query') else 'small',
                'max_parallel_per_consumer':1 if advance else 2,
                'max_parallel_per_tenant':4 if advance else 8,
                'max_output_bytes':32*1024*1024 if governed.id.endswith('.query') else 4*1024*1024,
                'collection_policy':'paged' if governed.id.endswith(('.query','.list')) else 'bounded',
                'max_page_size':500 if governed.id.endswith(('.query','.list')) else None},
            delegation_policy='none', execution_mode=ExecutionMode.CLOUD_SYNC,
            authorization_policy='simulation.model_cache:trusted_super_admin_trigger_project_scoped_read',
            business_effect=governed.description,
            side_effects='Persist shared cache metadata and deterministic read-only TC work; never modify TC.' if is_write else 'Return authorized project cache metadata and bounded full-value rows.',
            consumer_refs=({'consumer_id':WORKER_ID if advance else DESKTOP_CONSUMER_ID,'consumer_type':'worker' if advance else 'web','version_constraint':'==1'},),
            business_acceptance_criteria=(
                'Only trusted super_admin can trigger/control; scheduled and project-manager triggers remain disabled.',
                'Cloud writes enlist their open Simulation transaction with Gateway Outcome and audit persistence.',
                'Each project/data-stage batch receives its v1/v2 label from a locked server counter; callers cannot name it.',
                'One tenant/project/selector batch persists all actual TC business return fields with their original types.',
                'A page receipt, node rows and continuation work commit atomically; retries never restart accepted pages.',
                'Generation mismatch requires a new batch; incomplete/paused/failed batches cannot be consumed as complete snapshots.',
                'Search and AND/OR filters run across the whole persisted batch, independent of UI page size.'),
            business_invariants=(BusinessInvariantContract(rule_id='simulation.model_cache.atomic_checkpoint',version=1,
                statement='Accepted TC pages and their durable continuations are atomic, deduplicated and source/generation pinned.',
                applies_when='cache advances a durable read-only TC task',
                enforcement_ref='plugins/simulation/simulation_backend/data/cloud_model_cache_repository.py:apply_result',
                error_code='cache_generation_stale',test_refs=('plugins/simulation/tests/test_cloud_model_cache.py::test_generation_mismatch_rolls_back_page',)),),
            test_refs=({'path':'plugins/simulation/tests/test_cloud_model_cache.py'},{'path':'plugins/simulation/tests/test_cloud_model_cache_gateway.py'},{'path':'plugins/simulation/tests/test_cloud_model_cache_bulk.py'}),
            domain_errors=tuple(DomainErrorContract(code=code,meaning=meaning,retryable=code in ('cache_version_conflict',),is_caller_error=code in ('cache_filter_invalid','cache_trigger_disabled')) for code,meaning in (
                ('cache_trigger_forbidden','Only trusted super_admin may trigger or control.'),('cache_actor_mismatch','Worker actor must be the original trigger actor.'),
                ('cache_project_forbidden','Actor cannot read this project.'),('cache_not_found','Batch is absent in this tenant.'),
                ('cache_version_conflict','Reload the batch before changing its state.'),('cache_state_invalid','The requested state transition is unavailable.'),
                ('cache_generation_stale','Pinned sibling generation changed; create a new batch.'),('cache_source_mismatch','TC returned a different selector digest.'),
                ('cache_sensitive_field_rejected','Transport secrets cannot enter the shared cache.'),('cache_page_invalid','TC page violates the durable task contract.'),
                ('cache_receipt_conflict','An accepted page has conflicting contents.'),('cache_filter_invalid','Use a supported typed filter.'),
                ('cache_node_limit','The bounded batch node budget is exhausted.'),('cache_page_too_large','The TC page exceeds the governed byte limit.'),
                ('cache_idempotency_conflict','An existing creation key refers to different input.'),('cache_trigger_disabled','Scheduled triggering is reserved and disabled.'))),
            domain_errors_complete=False,
            concurrency_policy='expected_version' if control else 'none',
            expected_version_payload_path='expected_version' if control else None,
            idempotency_policy='required' if is_write else 'none',
            consistency_policy='strong',evidence_policy='required',
            replay_data_policy='projected' if is_write and not advance else 'metadata_only',
            transaction_policy={'mode':'provider','boundary':'simulation','atomicity':'batch lock; accepted node page, receipt and durable continuation commit together',
                'outcome_enlistment':'Gateway commits or rolls back the shared open transaction; rejected TC pages roll back to repository savepoints.',
                'tables':['workmanship_sim_cloud_cache_batches','workmanship_sim_cloud_cache_tasks','workmanship_sim_cloud_cache_nodes','workmanship_sim_cloud_cache_receipts','workmanship_sim_cloud_cache_versions','workmanship_sim_cloud_cache_manifests'],
                'migration_refs':['backend/db/migrations/domains/simulation/0030_cloud_model_cache.sql','backend/db/migrations/domains/simulation/0031_cloud_model_cache_versions.sql','backend/db/migrations/domains/simulation/0032_cloud_model_cache_snapshot_coverage.sql','backend/db/migrations/domains/simulation/0033_cloud_model_cache_pinned_query.sql'],
                'dependencies':['simulation.teamcenter.model_cache.read@1','simulation.teamcenter.model_cache.read@2','project.project.read.atomic.projects_get@2'],
                'idempotency':'tenant/actor/create key; batch/task/attempt deterministic signed plan; task receipt/body hash',
                'recovery':'worker reuses admitted operation after restart; stale generation is terminal; super_admin resumes auth/transient failures'},
            automation_level=AutomationLevel.A2 if advance or not is_write else AutomationLevel.A1)
        if governed.id=='simulation.model_cache.query' and governed.version==2:
            updates.update(
                side_effects='Return the authorized fixed completed snapshot; never query current TC, mutate snapshots or download model files.',
                business_acceptance_criteria=(
                    'Roots and children read bounded indexed structure rows without scanning full property bags, including cold legacy snapshots.',
                    'Node details come from the same batch, with original read states and exact geometry references.',
                    'Only completed batches can be consumed; pinned generation/hash and cursor scope mismatches fail explicitly.',
                    'Legacy unknown hashes and spatial semantics remain unknown; completion is distinct from downloaded JT readiness.'),
                business_invariants=(BusinessInvariantContract(rule_id='simulation.model_cache.fixed_snapshot',version=1,
                    statement='Every returned node belongs to the requested authorized completed batch and pinned identity; no latest or live fallback.',
                    applies_when='a consumer reads an explicit completed cache source',
                    enforcement_ref='plugins/simulation/simulation_backend/data/cloud_model_cache_snapshot.py:read',
                    error_code='cache_snapshot_mismatch',test_refs=('plugins/simulation/tests/test_cloud_model_cache_pinned.py::test_unready_missing_and_mismatched_snapshots_fail_explicitly',)),),
                test_refs=({'path':'plugins/simulation/tests/test_cloud_model_cache_pinned.py'},),
                domain_errors=updates['domain_errors']+tuple(DomainErrorContract(code=code,meaning=meaning,retryable=False,is_caller_error=False) for code,meaning in (
                    ('cache_snapshot_not_ready','Only completed batches can be bound.'),('cache_snapshot_mismatch','The fixed content digest differs.'),
                    ('cache_snapshot_hash_unavailable','The requested content digest cannot be verified.'),('cache_cursor_invalid','Cursor binding or shape is invalid.'),
                    ('cache_node_not_found','Node is absent from this batch.'),('cache_snapshot_unindexed','This snapshot lacks the requested indexed position.'))))
    if governed.id in ('simulation.environment.cache_source.materialization.inspect','simulation.environment.cache_source.open.request'):
        from backend.capability_v2.identity import DESKTOP_CONSUMER_ID
        opening=governed.id.endswith('open.request')
        updates.update(exposure=ExposurePolicy(web=True), timeout_seconds=600,
            authorization_policy='simulation.workspace:owner_cache_materialization',
            business_effect=governed.description,
            side_effects='Admit one exact native open from prepared shared TC metadata; the current client downloads missing JT through TC/FMS and reports local file proofs. No JT upload or OIS JT artifact is created.' if opening else 'Read prepared fixed cache structure and exact TC file references; no native effect or JT transfer.',
            consumer_refs=({'consumer_id':DESKTOP_CONSUMER_ID,'consumer_type':'web','version_constraint':'==1'},),
            concurrency_policy='expected_version' if opening else 'none',
            expected_version_payload_path='expected_workspace_row_version' if opening else None,
            idempotency_policy='required' if opening else 'none', consistency_policy='strong',evidence_policy='required',
            execution_budget={**descriptor.execution_budget.model_dump(),'max_output_bytes':8*1024*1024,'memory_class':'large',
                'collection_policy':'paged' if not opening else 'bounded','max_page_size':500 if not opening else None},
            business_acceptance_criteria=(
                'Only the owned document fixed cache identity supplies nodes and geometry; request bodies cannot supply nodes, artifact receipts or spatial authority.',
                'When root_node_key is supplied, only that exact occurrence and its descendants supply geometry and file requests; unknown keys fail without widening to the document.',
                'Original logical groups remain mapped; unsupported own geometry is explicitly excluded and valid geometry uses frozen absolute transforms with documented server-owned spatial evidence.',
                'Each included JT is resolved on the current client from the exact pinned TC file reference and attested by its signed local SHA256/size proof; no JT upload occurs.',
                'Package and native receipt use canonical V2 hashes; request replay never opens a second document.'),
            business_invariants=(BusinessInvariantContract(rule_id='simulation.cache_source.exact_materialization',version=1,
                statement='The assembly description, TC dependencies and node map come only from prepared project-authorized fixed cache metadata; file readiness remains client-local.',
                applies_when='a cache source is inspected or opened',
                enforcement_ref='plugins/simulation/simulation_backend/capabilities/cache_tc_open.py:TcCacheSourceOpenProvider',
                error_code='cache_materialization_changed',test_refs=('plugins/simulation/tests/test_cache_tc_open.py',)),),
            no_business_invariant_reason=None,test_refs=({'path':'plugins/simulation/tests/test_cache_tc_open.py'},{'path':'plugins/simulation/tests/test_cache_preparation_store.py'}),
            transaction_policy={'owner':'simulation','mode':'provider' if opening else 'read_only','boundary':'simulation',
                'atomicity':'owner workspace lock and idempotent response enlist in Gateway Outcome; deterministic queue admission is independently durable and recovered by exact plan identity',
                'tables':['workmanship_sim_workspaces','workmanship_sim_vm_documents','workmanship_sim_workspace_idempotency','workmanship_sim_connector_runtime_plans'],
                'migration_refs':['backend/db/migrations/domains/simulation/0018_simulation_environment_documents_and_hierarchies.sql','backend/db/migrations/domains/simulation/0036_cache_assembly_preparation.sql','backend/db/migrations/domains/simulation/0037_cache_assembly_preparation_chunks.sql'],
                'dependencies':['simulation.model_cache.query@2','vismockup.model.open@3'],
                'idempotency':'workspace/request key and exact normalized input; replay returns original operation/package/node map'},
            domain_errors_complete=False)
    if governed.id == 'simulation.environment.cache_source.bind':
        updates.update(
            business_effect='Associate one explicitly selected completed project-cache snapshot with a Simulation model document.',
            business_acceptance_criteria=(
                'The caller can read the selected project batch and owns the target workspace.',
                'Batch, generation, schema and available digest are validated before persistence; no latest-batch substitution.',
                'The binding is source metadata, not a file Artifact or a VisMockup runtime session.'),
            concurrency_policy='expected_version', expected_version_payload_path='expected_row_version',
            test_refs=({'path':'plugins/simulation/tests/test_cache_source_binding.py'},),
            transaction_policy={'mode':'provider','boundary':'simulation',
                'atomicity':'document binding, workspace revision and idempotency receipt commit together',
                'tables':['workmanship_sim_vm_documents','workmanship_sim_workspaces','workmanship_sim_workspace_idempotency'],
                'migration_refs':['backend/db/migrations/domains/simulation/0018_simulation_environment_documents_and_hierarchies.sql'],
                'dependencies':['simulation.model_cache.query@2'],
                'recovery':'reuse the same insertion identity; never substitute another batch'})
    cache_visualization_version=(
        governed.id=='simulation.teamcenter.visualization.launch.request' and governed.version==3
        or governed.id=='simulation.teamcenter.visualization.insert.request' and governed.version==2)
    if cache_visualization_version:
        from backend.capability_v2.identity import DESKTOP_CONSUMER_ID
        updates.update(
            authorization_policy='simulation.model_cache:project_scoped_completed_node_open',
            business_effect=('Resolve one completed cloud-cache node to its exact Teamcenter ItemRevision and '
                'queue one native Visualization open or insert; JT bytes remain in FMS/FCC.'),
            resource_selectors=(
                ResourceSelector(resource_type='simulation-model-cache-batch',payload_path='cache_source.batch_id',required=False),
                ResourceSelector(resource_type='simulation-model-cache-node',payload_path='cache_source.node_key',required=False),
                ResourceSelector(resource_type='teamcenter-endpoint',payload_path='source_selector.endpoint_id',required=False),
                ResourceSelector(resource_type='teamcenter-online-source',payload_path='source_selector.object_uid',required=False),
            ),
            consumer_refs=({'consumer_id':DESKTOP_CONSUMER_ID,'consumer_type':'web',
                'version_constraint':'==1'},),
            business_acceptance_criteria=(
                'A cache-bound request reads one completed tenant/project-scoped batch and one exact node.',
                'The browser cannot submit the resolved ItemRevision UID in the cache_source branch.',
                'One request queues exactly one existing Teamcenter Visualization operation.',
                'The normal path performs no product search, BOM traversal, property read, JT file fetch or OIS upload.',
            ),
            business_invariants=(BusinessInvariantContract(
                rule_id='simulation.model_cache.visualization_exact_node',version=1,
                statement='A cache-bound Visualization root is the exact ItemRevision stored on the selected completed cache node.',
                applies_when='a model-file tree node is opened or inserted from the cloud cache',
                enforcement_ref='plugins/simulation/simulation_backend/capabilities/connector_runtime.py:_resolve_cache_visualization_source',
                error_code='cache_source_identity_missing',
                test_refs=('plugins/simulation/tests/test_viewer_interaction_provider.py::test_cache_bound_launch_resolves_server_identity_and_queues_one_native_launch',)),),
            no_business_invariant_reason=None,
            test_refs=({'path':'plugins/simulation/tests/test_viewer_interaction_provider.py'},
                {'path':'plugins/simulation/tests/test_cloud_model_cache.py'},
                {'path':'packages/sim-plugin/web/cad_sim/teamcenter_lazy_tree.test.js'}),
            transaction_policy={'mode':'external','boundary':'simulation_and_teamcenter_visualization',
                'atomicity':'Read the fixed cache identity before deterministic signed Connector queue admission; the viewer effect is confirmed by the existing signed receipt.',
                'tables':['workmanship_sim_cloud_cache_batches','workmanship_sim_cloud_cache_nodes','workmanship_sim_connector_runtime_plans'],
                'dependencies':['simulation.model_cache.query@2','teamcenter.visualization.launch@2','teamcenter.visualization.insert@1'],
                'recovery':'Retry the same deterministic admission key; never fall back to product search, Latest, or the document root.'},
            domain_errors=tuple(updates['domain_errors'])+tuple(DomainErrorContract(code=code,meaning=code,retryable=False,
                is_caller_error=code in {'cache_source_forbidden','cache_source_node_not_found','cache_source_identity_missing','cache_source_stale'})
                for code in ('cache_source_not_ready','cache_source_forbidden','cache_source_node_not_found','cache_source_identity_missing','cache_source_stale')),
            domain_errors_complete=False,
        )
    if governed.id in ('simulation.model_cache.file.fetch.request','simulation.model_cache.file.fetch.result','simulation.teamcenter.model_file.fetch',
        'simulation.model_cache.file.fetch.batch.request','simulation.model_cache.file.fetch.batch.result','simulation.teamcenter.model_files.size.preflight'):
        from backend.capability_v2.identity import DESKTOP_CONSUMER_ID
        local=governed.execution=='local'
        updates.update(
            exposure=ExposurePolicy(local_runtime=True) if local else ExposurePolicy(web=True),
            timeout_seconds=600 if local else 30,
            authorization_policy='simulation.model_cache:project_scoped_exact_file_read',
            business_effect=governed.description,
            side_effects=('Read exact ImanFile sizes for preflighted cache members; do not fetch file contents or open the viewer.' if governed.id=='simulation.teamcenter.model_files.size.preflight' else
                'Read an exact TC ImanFile and publish immutable verified bytes through Base ArtifactService; no BOM rebuild or viewer open.' if local else
                'Admit or read a bounded actor/tenant-bound signed file batch; preserve the pinned snapshot and separate per-file artifacts.' if '.batch.' in governed.id else
                'Admit or read an actor/tenant-bound deterministic signed file acquisition plan; preserve completed cache snapshots.'),
            consumer_refs=({'consumer_id':'simulation.model_cache.file.fetch.batch.request' if governed.id=='simulation.teamcenter.model_files.size.preflight' else 'simulation.model_cache.file.fetch.request','consumer_type':'worker','version_constraint':'==1'},) if local else ({'consumer_id':DESKTOP_CONSUMER_ID,'consumer_type':'web','version_constraint':'==1'},),
            business_acceptance_criteria=(
                'Only exact JT references present in the authorized completed node snapshot may be acquired; arbitrary file identifiers and latest revision fallback fail.',
                'A batch contains at most eight unique members; Teamcenter size preflight rejects multi-file totals above 100 MiB; a single JT may be up to 512 MiB.',
                'The signed result binds each member step to the batch/generation/hash, node/revision/file reference, artifact SHA-256 and byte length.',
                'Bytes acquired now are distinguished from bytes captured with the original cache; captured_bytes_verified stays false.',
                'Each JT remains a separate artifact mediated by its signed leased step and Base ArtifactService; acquisition never opens a viewer.'),
            business_invariants=(BusinessInvariantContract(rule_id='simulation.model_cache.file_membership',version=1,
                statement='The exact file reference and result belong to the fixed completed snapshot and admitted request.',
                applies_when='a cache consumer requests or reads JT acquisition',
                enforcement_ref='plugins/simulation/simulation_backend/capabilities/cloud_model_cache_files.py:member',
                error_code='cache_file_not_referenced',test_refs=('plugins/simulation/tests/test_cache_file_materialization.py',)),),
            no_business_invariant_reason=None,
            test_refs=({'path':'plugins/simulation/tests/test_cache_file_materialization.py'},{'path':'local-runtime/tests/Ai00.Connector.Tests/TeamcenterModelFileTests.cs'},{'path':'local-runtime/tests/teamcenter_cache_file.test.cjs'}),
            transaction_policy={'owner':'simulation','mode':'provider' if is_write and not local else 'read_only',
                'atomicity':'Gateway Outcome enlists the open Simulation read transaction; signed queue admission uses its existing deterministic idempotent transaction and survives replay.',
                'tables':['workmanship_sim_cloud_cache_batches','workmanship_sim_cloud_cache_nodes','workmanship_sim_connector_runtime_plans'],
                'dependencies':['simulation.model_cache.query@2','simulation.teamcenter.model_file.fetch@1','simulation.teamcenter.model_files.size.preflight@1','Base ArtifactService'],
                'contract_refs':['docs/contracts/teamcenter.model_file.fetch@1.json','docs/contracts/teamcenter.model_files.size.preflight@1.json',
                    *(['docs/contracts/simulation.model_cache.file.fetch.batch.request@1.json','docs/contracts/simulation.model_cache.file.fetch.batch.result@1.json'] if '.batch.' in governed.id else [])],
                'recovery':'Retry the same deterministic admission key; unknown artifact publication is not claimed to have no effect.'},
            idempotency_policy='required' if is_write else 'none',
            consistency_policy='strong',evidence_policy='required',
            replay_data_policy='projected' if is_write else 'metadata_only',
            domain_errors=tuple(DomainErrorContract(code=code,meaning=code) for code in ('cache_file_not_referenced','cache_file_references_unavailable','cache_file_operation_not_found','cache_file_operation_mismatch','cache_file_result_invalid','cache_file_content_mismatch','cache_file_batch_size_invalid','cache_file_batch_duplicate_member','cache_file_batch_member_invalid','cache_file_batch_size_exceeded','cache_project_forbidden','cache_snapshot_not_ready','cache_generation_stale','cache_snapshot_mismatch','connector_offline','cache_file_integrity_failed')),
            domain_errors_complete=False)
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

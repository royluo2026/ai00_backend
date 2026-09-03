"""Craft-owned registration boundary for native Capability V2 contracts."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.contracts import (
    AutomationLevel,
    BusinessInvariantContract,
    CapabilityDescriptorV2,
    DomainErrorContract,
    ExposurePolicy,
    LifecycleStatus,
    ResourceSelector,
    SideEffectLevel,
)
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec

from .contracts import input_schema_for, output_schema_for
from .reviewed_ids import DEPRECATED_REVIEWED_CAPABILITIES
from .rule_descriptors import RULE_DEFINITION_CHANGE_CAPABILITY_ID


_RESOURCE_FIELDS: dict[str, tuple[tuple[str, str], ...]] = {
    "craft.resource_requirement.create": (("craft-resource-requirement-type", "resource_type"),),
    "craft.resource_requirement.update": (("craft-resource-requirement", "gid"),),
    "craft.resource_requirement.retire": (("craft-resource-requirement", "gid"),),
    "craft.resource_requirement.alias.create": (("craft-resource-requirement", "resource_gid"),),
    "craft.resource_requirement.alias.delete": (("craft-resource-requirement", "resource_gid"),),
    "craft.resource_requirement.staging.search": (("craft-bop-version", "version_gid"),),
    "craft.resource_requirement.staging.resolve": (("craft-resource-staging", "staging_gid"),),
    "craft.resource_requirement.staging.ignore": (("craft-resource-staging", "staging_gid"),),
    "craft.bop.version.get": (("craft-bop-version", "version_gid"),),
    "craft.bop.execution_structure.get": (("craft-bop-version", "version_gid"),),
    "craft.bop.execution_structure.preview": (("craft-bop-version", "version_gid"),),
    "craft.bop.linked_parts.get": (("craft-bop-version", "version_gid"),),
    "craft.bop.work_package.get": (("craft-bop-version", "version_gid"),),
    "craft.bop.structure.outline.get": (("craft-bop-version", "version_gid"),),
    "craft.bop.entry.detail.get": (("craft-bop-version", "version_gid"),),
    "craft.bop.entry.relation.list": (("craft-bop-version", "version_gid"),),
    "craft.bop.linked_entity.detail.get": (("craft-bop-version", "version_gid"),),
    "craft.bop.version.compare": (
        ("craft-bop-version", "from_version_gid"),
        ("craft-bop-version", "to_version_gid"),
    ),
    "craft.pbom.part.search": (("craft-pbom-version", "version_gid"),),
    "craft.pbom.version.get": (("craft-pbom-version", "version_gid"),),
    "craft.pbom.version.submit": (("craft-pbom-version", "version_gid"),),
    "craft.pbom.version.publish": (("craft-pbom-version", "version_gid"),),
    "craft.pbom.version.archive": (("craft-pbom-version", "version_gid"),),
    "craft.pbom.version.compare": (("craft-pbom-version", "from_version_gid"), ("craft-pbom-version", "to_version_gid")),
    "craft.pbom.draft.change.preview": (("craft-pbom-version", "version_gid"),),
    "craft.pbom.draft.change.apply": (("craft-pbom-version", "version_gid"),),
    "craft.gbop.item.usage.get": (("craft-gbop-item", "item_gid"),),
    "craft.gbop.item.knowledge.list": (("craft-gbop-item", "item_gid"),),
    "craft.bop.draft.change.preview": (("craft-bop-version", "version_gid"),),
    "craft.bop.draft.change.apply": (("craft-bop-preview", "preview_gid"),),
    "craft.bop.version.archive": (("craft-bop-version", "version_gid"),),
    "craft.process_screenshot.attach": (("craft-bop-version", "bop_version_gid"),),
}

_EXPECTED_REVISION = {
    "craft.bop.draft.change.preview",
    "craft.bop.execution_structure.preview",
    "craft.bop.version.archive",
    RULE_DEFINITION_CHANGE_CAPABILITY_ID,
}

_EXPECTED_VERSION_PATHS = {
    "craft.resource_requirement.update": "expected_resource_version",
    "craft.resource_requirement.retire": "expected_resource_version",
    "craft.resource_requirement.staging.resolve": "expected_staging_version",
    "craft.resource_requirement.staging.ignore": "expected_staging_version",
}

_STANDARD_OPERATION_CHANGE_ID = "craft.standard_operation.change.apply"
_STANDARD_OPERATION_READ_ID = "craft.standard_operation.read"
_BOP_IMPORT_PREVIEW_ID = "craft.bop.import.preview"
_BOP_ENTRY_BULK_CHANGE_ID = "craft.bop.entry.bulk.change.apply"
_LIBRARY_CHANGE_ID = "craft.library.change.apply"
_CRAFT_BUSINESS_DEFINITIONS = {
    "craft.process_screenshot.attach": (
        "Idempotently associate one finalized screenshot ArtifactRef with one exact BOP operation and update its current screenshot projection.",
        (
            "The BOP version and operation exist and match the requested identity.",
            "The ArtifactRef is finalized, immutable, image-typed and authorized for the target BOP version.",
            "The same capture run and operation return the same association; a different artifact is rejected.",
        ),
        "The write preserves screenshot history and updates the operation projection in one Craft transaction.",
    ),
    "craft.bop.entry.detail.get": (
        "Return the governed BOP entry, its bounded links and allowlisted linked-entity projection at one exact revision.",
        (
            "The returned entry and every link belong to the requested BOP version and revision.",
            "At most 500 links are returned and arbitrary linked tables or columns cannot be requested.",
            "The detail read does not mutate BOP or linked-entity records.",
        ),
        "This read projects existing governed records; exact-revision scoping, result bounds and field allowlisting are enforced by its repository and closed contract.",
    ),
    "craft.bop.lifecycle.state.change.apply": (
        "Initialize or advance the governed lifecycle state of one caller-scoped BOP version.",
        (
            "Initialization changes only the requested BOP version lifecycle state.",
            "Phase confirmation advances only from the version's current valid lifecycle phase.",
            "Rejected transitions return a stable domain error without partially changing lifecycle state.",
        ),
        "Lifecycle transition rules are owned and enforced by the existing lifecycle service; this capability adds only the governed transport boundary.",
    ),
    "craft.bop.lifecycle.state.read": (
        "Return the bounded lifecycle dashboard state for one caller-scoped BOP version.",
        (
            "The result belongs only to the requested BOP version.",
            "The projection reports the persisted current phase, checklist and route state.",
            "The lifecycle-state read does not mutate lifecycle or BOP records.",
        ),
        "This read projects lifecycle state already governed by the lifecycle service and introduces no additional state decision.",
    ),
    "craft.bop.lifecycle.stats.refresh.apply": (
        "Recompute and persist the lifecycle statistics snapshot for one caller-scoped BOP version.",
        (
            "Statistics are derived only from records belonging to the requested BOP version.",
            "A successful result returns the newly persisted lifecycle statistics snapshot.",
            "A failed refresh does not report a successful snapshot.",
        ),
        "Metric definitions and persistence rules remain owned by the existing lifecycle statistics service; this capability adds only the governed command boundary.",
    ),
    "craft.bop.linked_parts.get": (
        "Return a bounded list of PBOM parts linked to one BOP version with their governed usage locations.",
        (
            "Every returned part is linked to the requested BOP version.",
            "Usage locations identify only entries within that BOP version.",
            "The linked-parts read does not mutate PBOM parts, BOP entries or links.",
        ),
        "This read projects existing governed links and introduces no additional business-state decision.",
    ),
    "craft.bop.version.get": (
        "Return the identity, lifecycle state and revision evidence for one exact BOP version.",
        (
            "The result identity matches the requested BOP version GID.",
            "The result exposes the persisted current revision and lifecycle evidence.",
            "The version read does not mutate BOP records.",
        ),
        "This read projects one existing governed BOP version and introduces no additional business-state decision.",
    ),
    "craft.bop.work_package.get": (
        "Return one bounded page of BOP work-package nodes with reference summaries for a governed line, station or role scope.",
        (
            "Every returned node belongs to the requested BOP version, revision and work-package scope.",
            "A page contains at most 200 nodes and returns an opaque continuation cursor when more nodes exist.",
            "Entity summaries expose only allowlisted fields and the work-package read does not mutate domain records.",
        ),
        "This read projects existing governed BOP records; scope, pagination and field allowlisting are enforced by its repository and closed contract.",
    ),
    "craft.library.read": (
        "Return bounded caller-visible manufacturing resource library records for the requested governed collection.",
        (
            "Results contain only records from the requested Craft library collection.",
            "List operations respect the published collection bound and closed output schema.",
            "Library reads do not mutate manufacturing resource records.",
        ),
        "This read projects existing governed library records and introduces no additional business-state decision.",
    ),
    "craft.vpps_audit.change.apply": (
        "Apply one governed bulk-ignore or revert operation to the caller-scoped PBOM VPPS audit state.",
        (
            "A bulk-ignore changes only the selected Rule4 audit rows in the requested PBOM scope.",
            "A revert targets one recorded audit operation and restores only its governed changes.",
            "Rejected operations return a stable domain error without reporting success.",
        ),
        "VPPS audit selection, ignore and revert rules remain owned by the existing audit service; this capability adds only the governed command boundary.",
    ),
    "craft.vpps_audit.read": (
        "Return bounded caller-visible PBOM VPPS audit history or Rule4 ignore state.",
        (
            "Results belong only to the requested PBOM audit scope.",
            "History and Rule4 state are returned through the published bounded output contract.",
            "VPPS audit reads do not mutate audit or PBOM records.",
        ),
        "This read projects existing governed audit records and introduces no additional business-state decision.",
    ),
}
_BOP_ENTRY_BULK_CHANGE_RULES = (
    BusinessInvariantContract(
        rule_id="craft.bop.entry.bulk.import_tc.atomicity",
        version=1,
        statement=(
            "A TC import commits its BOP entries, independent socket/tool/fixture/equipment "
            "links and unresolved-resource staging rows completely or not at all."
        ),
        applies_when="operation is import_tc",
        enforcement_ref=(
            "plugins/craft/craft_backend/routers/_bop/entries.py:_legacy_import_tc_entries"
        ),
        error_code="provider_failed",
        test_refs=(
            "backend/tests/test_craft_bop_entry_bulk_change_boundary.py::test_tc_import_rolls_back_entries_when_resource_link_write_fails",
        ),
    ),
    BusinessInvariantContract(
        rule_id="craft.bop.entry.bulk.import_tc.resource_type_isolation",
        version=1,
        statement=(
            "TC socket, tool, fixture and equipment requirements remain separate BOP node and link types."
        ),
        applies_when="operation is import_tc and a row declares a resource requirement node",
        enforcement_ref=(
            "plugins/craft/craft_backend/capabilities/resource_requirements.py:resolve_tc_resource_for_import"
        ),
        error_code="resource_type_mismatch",
        test_refs=(
            "backend/tests/test_craft_bop_entry_bulk_change_boundary.py::test_tc_import_commits_entries_and_independent_resource_links",
        ),
    ),
)
_LIBRARY_CHANGE_BUSINESS_RULES = (
    BusinessInvariantContract(
        rule_id="craft.library.part_names.bulk_import.atomicity",
        version=1,
        statement="A VPPS part-name import batch is committed completely or not at all.",
        applies_when="operation is part_names.bulk_import",
        enforcement_ref="plugins/craft/craft_backend/capabilities/library_change.py:_bulk_import_part_names",
        error_code="provider_failed",
        test_refs=(
            "backend/tests/test_craft_library_boundary.py::test_part_name_bulk_import_does_not_commit_partial_batch",
        ),
    ),
    BusinessInvariantContract(
        rule_id="craft.library.part_names.bulk_import.reconciliation",
        version=1,
        statement="Created and skipped counts reconcile every supplied VPPS part-name row exactly once.",
        applies_when="operation is part_names.bulk_import",
        enforcement_ref="plugins/craft/craft_backend/capabilities/library_change.py:_bulk_import_part_names",
        error_code="invalid_input",
        test_refs=(
            "backend/tests/test_craft_library_boundary.py::test_part_name_bulk_import_skips_existing_duplicate_and_blank_vpps",
        ),
    ),
)
_STANDARD_OPERATION_BUSINESS_RULES = (
    BusinessInvariantContract(
        rule_id="craft.standard_operation.bulk_import.atomicity",
        version=1,
        statement="A standard-operation import batch is committed completely or not at all.",
        applies_when="operation is bulk_import",
        enforcement_ref="plugins/craft/craft_backend/capabilities/standard_operation.py:change_standard_operation",
        error_code="provider_failed",
        test_refs=(
            "plugins/craft/tests/test_standard_operation_provider.py::test_standard_operation_bulk_import_does_not_commit_a_partial_batch",
        ),
    ),
    BusinessInvariantContract(
        rule_id="craft.standard_operation.bulk_import.reconciliation",
        version=1,
        statement="Created, updated and skipped counts reconcile every supplied standard-operation record exactly once.",
        applies_when="operation is bulk_import",
        enforcement_ref="plugins/craft/craft_backend/capabilities/standard_operation.py:change_standard_operation",
        error_code="invalid_input",
        test_refs=(
            "plugins/craft/tests/test_standard_operation_provider.py::test_standard_operation_bulk_import_skips_existing_and_duplicate_codes",
        ),
    ),
)

_RESOURCE_REQUIREMENT_RULES = {
    "create": (
        BusinessInvariantContract(
            rule_id="craft.resource_requirement.type_code_unique", version=1,
            statement="A resource code identifies at most one standard within the same resource type.",
            applies_when="a resource requirement standard is created",
            enforcement_ref="plugins/craft/craft_backend/capabilities/resource_requirements.py:create_resource_requirement",
            error_code="resource_code_conflict",
            test_refs=("plugins/craft/tests/test_resource_requirement_provider.py::test_create_rejects_duplicate_type_scoped_code",),
        ),
    ),
    "update": (
        BusinessInvariantContract(
            rule_id="craft.resource_requirement.update_active_expected_version", version=1,
            statement="Only an active resource standard at the caller's expected version can be changed.",
            applies_when="a resource requirement standard is updated",
            enforcement_ref="plugins/craft/craft_backend/capabilities/resource_requirements.py:update_resource_requirement",
            error_code="resource_version_conflict",
            test_refs=("plugins/craft/tests/test_resource_requirement_provider.py::test_update_requires_expected_resource_version",),
        ),
    ),
    "retire": (
        BusinessInvariantContract(
            rule_id="craft.resource_requirement.retire_unreferenced", version=1,
            statement="A resource requirement standard cannot be retired while governed Craft data still references it.",
            applies_when="an active resource requirement standard is retired",
            enforcement_ref="plugins/craft/craft_backend/capabilities/resource_requirements.py:ensure_resource_not_referenced",
            error_code="resource_in_use",
            test_refs=("plugins/craft/tests/test_resource_requirement_provider.py::test_retirement_rejects_resources_still_used_by_a_bop",),
        ),
    ),
    "alias.create": (
        BusinessInvariantContract(
            rule_id="craft.resource_requirement.alias_active_unique", version=1,
            statement="A normalized alias is unique within one active resource requirement standard.",
            applies_when="a matching alias is added",
            enforcement_ref="plugins/craft/craft_backend/capabilities/resource_requirements.py:create_resource_alias",
            error_code="resource_alias_conflict",
            test_refs=("plugins/craft/tests/test_resource_requirement_provider.py::test_alias_create_requires_active_resource_and_unique_value",),
        ),
    ),
    "alias.delete": (
        BusinessInvariantContract(
            rule_id="craft.resource_requirement.alias_delete_owned", version=1,
            statement="An alias can only be removed through the resource standard that owns it.",
            applies_when="a matching alias is removed",
            enforcement_ref="plugins/craft/craft_backend/capabilities/resource_requirements.py:delete_resource_alias",
            error_code="resource_alias_not_found",
            test_refs=("plugins/craft/tests/test_resource_requirement_provider.py::test_alias_delete_rejects_wrong_resource",),
        ),
    ),
    "staging.resolve": (
    BusinessInvariantContract(
        rule_id="craft.resource_requirement.staging.type_match",
        version=1,
        statement="A staged resource can only resolve to an active standard of the same resource type.",
        applies_when="a TC resource staging row is resolved",
        enforcement_ref="plugins/craft/craft_backend/capabilities/resource_requirements.py:_decide_staging",
        error_code="resource_type_mismatch",
        test_refs=(
            "plugins/craft/tests/test_resource_requirement_provider.py::test_resolve_replaces_only_the_matching_resource_link",
        ),
    ),
    BusinessInvariantContract(
        rule_id="craft.resource_requirement.staging.atomic_decision",
        version=1,
        statement="The matching BOP link and staging decision commit in one Craft transaction.",
        applies_when="a TC resource staging row is resolved or ignored",
        enforcement_ref="plugins/craft/craft_backend/capabilities/resource_requirements.py:_decide_staging",
        error_code="resource_staging_conflict",
        test_refs=(
            "plugins/craft/tests/test_resource_requirement_provider.py::test_resolve_replaces_only_the_matching_resource_link",
        ),
    ),
    ),
    "staging.ignore": (
        BusinessInvariantContract(
            rule_id="craft.resource_requirement.staging.atomic_ignore", version=1,
            statement="Ignoring a staged requirement removes only its same-type provisional BOP link and records the decision in one transaction.",
            applies_when="a TC resource staging row is ignored",
            enforcement_ref="plugins/craft/craft_backend/capabilities/resource_requirements.py:_decide_staging",
            error_code="resource_staging_conflict",
            test_refs=("plugins/craft/tests/test_resource_requirement_provider.py::test_ignore_removes_only_same_type_provisional_link",),
        ),
    ),
}

_DOMAIN_ERRORS = tuple(
    DomainErrorContract(code=code, meaning=meaning)
    for code, meaning in (
        ("bop_version_not_found", "The scoped BOP version does not exist."),
        ("bop_revision_unavailable", "The BOP has no authoritative revision."),
        ("revision_conflict", "The current BOP revision differs from the expected revision."),
        ("bop_entry_not_found", "A referenced BOP entry does not exist."),
        ("bop_link_not_found", "A referenced BOP link does not exist."),
        ("bop_project_unassigned", "The BOP is not assigned to a project."),
        ("version_not_published", "An official execution structure requires a published BOP."),
        ("preview_not_found", "The requested BOP change preview does not exist."),
        ("preview_expired", "The requested BOP change preview has expired."),
        ("preview_already_applied", "The requested BOP change preview was already committed."),
        ("idempotency_conflict", "The idempotency key is already bound to another Craft payload."),
        ("source_not_found", "The requested version creation source does not exist."),
        ("archive_forbidden", "The BOP lifecycle forbids archiving this version."),
        ("pbom_snapshot_not_found", "The scoped PBOM snapshot does not exist."),
        ("active_gbop_not_found", "No active GBOP release exists."),
        ("multiple_active_gbop_releases", "More than one active GBOP release exists."),
        ("active_gbop_item_not_found", "The GBOP item is not in the active release."),
        ("provider_unavailable", "The Craft application provider is unavailable."),
        ("invalid_cursor", "The pagination cursor is invalid."),
        ("invalid_page_size", "The requested page size is outside the capability limit."),
        ("invalid_scope_kind", "The requested BOP scope kind is invalid."),
        ("scope_not_found", "The requested BOP scope does not exist in the version."),
        ("entry_not_found", "The requested BOP entry does not exist in the version."),
        ("entry_detail_too_large", "The BOP entry has too many links for bounded detail output."),
        ("rule_not_found", "The requested rule was not found."),
        ("evaluation_timeout", "Rule evaluation exceeded its bounded time limit."),
        ("evaluation_unavailable", "Rule evaluation could not produce a bounded result."),
        ("resource_not_found", "The requested active Craft resource requirement does not exist."),
        ("resource_code_conflict", "The resource type and code already identify another standard."),
        ("resource_version_conflict", "The resource requirement changed or is no longer active."),
        ("resource_in_use", "The resource requirement is still referenced by governed Craft data."),
        ("resource_alias_conflict", "The normalized alias already exists for this resource."),
        ("resource_alias_not_found", "The requested resource alias does not exist."),
        ("resource_staging_not_found", "The requested TC resource staging row does not exist."),
        ("resource_staging_conflict", "The staging row was already decided or changed."),
        ("resource_type_mismatch", "The selected standard does not match the staged resource type."),
        ("screenshot_artifact_invalid", "The supplied screenshot is not a valid finalized image ArtifactRef."),
    )
)
_DOMAIN_ERROR_BY_CODE = {item.code: item for item in _DOMAIN_ERRORS}
_RESOURCE_ERROR_CODES = {
    "search": ("invalid_page_size",),
    "create": ("resource_code_conflict",),
    "update": ("resource_not_found", "resource_code_conflict", "resource_version_conflict"),
    "retire": ("resource_in_use", "resource_version_conflict"),
    "alias.create": ("resource_not_found", "resource_alias_conflict"),
    "alias.delete": ("resource_alias_not_found",),
    "staging.search": ("invalid_page_size",),
    "staging.resolve": ("resource_staging_not_found", "resource_staging_conflict", "resource_not_found", "resource_type_mismatch"),
    "staging.ignore": ("resource_staging_not_found", "resource_staging_conflict"),
}


def _governed_spec(spec: Any) -> Any:
    if spec.id == RULE_DEFINITION_CHANGE_CAPABILITY_ID:
        return spec.model_copy(update={"plugin_callable": True})
    return spec.model_copy(update={
        "plugin_callable": True,
        "input_schema": input_schema_for(spec.id, spec.version),
        "output_schema": output_schema_for(spec.id, spec.version),
    })


def descriptor_for(spec: Any) -> CapabilityDescriptorV2:
    """Create the frozen native descriptor reviewed and released by Craft."""
    governed = _governed_spec(spec)
    descriptor = descriptor_from_provider_spec(governed)
    is_write = descriptor.side_effect_level is not SideEffectLevel.READ
    selectors = tuple(
        ResourceSelector(resource_type=resource_type, payload_path=payload_path)
        for resource_type, payload_path in _RESOURCE_FIELDS.get(spec.id, ())
    )
    updates = {
        "lifecycle_status": (
            LifecycleStatus.DEPRECATED
            if spec.id in DEPRECATED_REVIEWED_CAPABILITIES
            else LifecycleStatus.STABLE
        ),
        "deprecation_message": (
            "Final-wave identity retained for compatibility; no bound Craft "
            "application outcome is currently registered."
            if spec.id in DEPRECATED_REVIEWED_CAPABILITIES else None
        ),
        "exposure": ExposurePolicy(web=True, api=True, plugin=True, agent=True, mcp=True),
        "exposure_policy_source": "provider_explicit",
        "automation_level": AutomationLevel.A1 if is_write else AutomationLevel.A2,
        "authorization_policy": "craft.v2:" + (",".join(governed.permissions) or "authenticated"),
        "resource_selectors": selectors,
        "data_classification": "confidential",
        "delegation_policy": "scoped",
        "agent_output_schema": descriptor.output_schema,
        "operation_policy": "optional" if is_write else "none",
        "replay_data_policy": (
            "projected" if spec.id == RULE_DEFINITION_CHANGE_CAPABILITY_ID else "metadata_only"
        ),
        "concurrency_policy": "expected_version" if spec.id in _EXPECTED_REVISION or spec.id in _EXPECTED_VERSION_PATHS else "none",
        "expected_version_payload_path": _EXPECTED_VERSION_PATHS.get(spec.id, "expected_revision" if spec.id in _EXPECTED_REVISION else None),
        "idempotency_policy": "required" if is_write else "none",
        "consistency_policy": "external" if is_write else "strong",
        "evidence_policy": (
            "required" if spec.id == "craft.process_screenshot.attach" else "optional"
        ),
        "domain_errors": _DOMAIN_ERRORS,
        "domain_errors_complete": True,
    }
    if spec.id.startswith("craft.resource_requirement."):
        action = spec.id.removeprefix("craft.resource_requirement.")
        effects = {
            "search": "Return a bounded page of active or retired Craft process resource requirement standards.",
            "create": "Create one reusable Craft process resource requirement standard with a type-scoped code.",
            "update": "Update one active Craft process resource requirement standard at its expected version.",
            "retire": "Retire one Craft process resource requirement standard while preserving its identity and references.",
            "alias.create": "Add one normalized matching alias to a Craft process resource requirement standard.",
            "alias.delete": "Remove one matching alias from a Craft process resource requirement standard.",
            "staging.search": "Return a bounded page of TC resource staging rows awaiting or recording a review decision.",
            "staging.resolve": "Resolve one TC resource staging row to a type-compatible active standard and BOP link atomically.",
            "staging.ignore": "Ignore one TC resource staging row and remove only its same-type provisional BOP link atomically.",
        }
        invariants = _RESOURCE_REQUIREMENT_RULES.get(action, ())
        updates.update({
            "business_effect": effects[action],
            "business_acceptance_criteria": (
                "The result is scoped to the Craft-owned process resource requirement identity.",
                "Inputs and outputs satisfy the closed published schema.",
                "Writes preserve type identity and return a stable domain error on rejected state.",
            ),
            "business_invariants": invariants,
            "no_business_invariant_reason": None if invariants else (
                "This read returns a bounded, resource-scoped projection and does not decide or change domain state."
            ),
            "domain_errors": tuple(_DOMAIN_ERROR_BY_CODE[code] for code in _RESOURCE_ERROR_CODES[action]),
            "domain_errors_complete": True,
        })
    elif spec.id in _CRAFT_BUSINESS_DEFINITIONS:
        effect, criteria, reason = _CRAFT_BUSINESS_DEFINITIONS[spec.id]
        updates.update({
            "business_effect": effect,
            "business_acceptance_criteria": criteria,
            "business_invariants": (),
            "no_business_invariant_reason": reason,
        })
    elif spec.id == _LIBRARY_CHANGE_ID:
        updates.update({
            "business_effect": (
                "Create or change manufacturing-resource library records, including one governed VPPS part-name batch import."
            ),
            "business_acceptance_criteria": (
                "A VPPS part-name import accepts at most 10000 records and requires a non-empty VPPS identifier for creation.",
                "Existing, duplicate and blank VPPS identifiers are skipped and counted without overwriting governed master data.",
                "Created and skipped counts reconcile the complete input batch.",
                "A database failure rolls back the complete batch rather than leaving a partial import.",
            ),
            "business_invariants": _LIBRARY_CHANGE_BUSINESS_RULES,
            "no_business_invariant_reason": None,
        })
    elif spec.id == _STANDARD_OPERATION_CHANGE_ID:
        updates.update({
            "business_effect": (
                "Create or change standard operations, including one governed batch import whose "
                "conflict policy and result counts are explicit to the caller."
            ),
            "business_acceptance_criteria": (
                "A bulk import accepts between 1 and 10000 records and requires a non-empty code and name for every record.",
                "The skip, overwrite and append conflict policies produce their declared create, update and skip outcomes.",
                "The created, updated and skipped counts reconcile the complete input batch.",
                "A database failure rolls back the complete batch rather than leaving a partial import.",
            ),
            "business_invariants": _STANDARD_OPERATION_BUSINESS_RULES,
            "no_business_invariant_reason": None,
        })
    elif spec.id == _STANDARD_OPERATION_READ_ID:
        updates.update({
            "business_effect": (
                "Return the caller-visible, bounded standard-operation library so users can select, inspect and verify reusable process definitions."
            ),
            "business_acceptance_criteria": (
                "List requests return at most 500 standard operations visible to the caller or their team.",
                "Get requests return the requested standard operation or a governed not-found error.",
                "Read operations do not mutate standard-operation records.",
            ),
            "business_invariants": (),
            "no_business_invariant_reason": (
                "This read projects already-governed records; visibility and result bounds are enforced by the provider query and contract."
            ),
        })
    elif spec.id == _BOP_IMPORT_PREVIEW_ID:
        updates.update({
            "business_effect": (
                "Validate a bounded spreadsheet-derived BOP document and return a non-mutating preview for the governed import workflow."
            ),
            "business_acceptance_criteria": (
                "The preview accepts the spreadsheet document shape emitted by the Web importer.",
                "The document contains no more than 10000 entries and fits the declared four-megabyte input budget.",
                "Preview execution does not write BOP or standard-operation records.",
            ),
            "business_invariants": (
                BusinessInvariantContract(
                    rule_id="craft.bop.import.preview.bounded_document",
                    version=1,
                    statement="A spreadsheet import preview contains at most 10000 entries and never mutates domain records.",
                    applies_when="a spreadsheet-derived BOP document is previewed",
                    enforcement_ref="plugins/craft/craft_backend/capabilities/contracts.py:INPUT_SCHEMAS",
                    error_code="invalid_input",
                    test_refs=(
                        "backend/tests/test_craft_capability_contracts.py::test_bop_import_preview_contract_accepts_the_document_shape_used_by_the_web_importer",
                    ),
                ),
            ),
            "no_business_invariant_reason": None,
        })
    elif spec.id == _BOP_ENTRY_BULK_CHANGE_ID:
        updates.update({
            "business_effect": (
                "Create, import, copy, auto-link, purge, patch or roll back governed BOP entries; "
                "TC imports preserve independent socket, tool, fixture and equipment requirements."
            ),
            "business_acceptance_criteria": (
                "The requested operation changes only the caller-scoped BOP version or entry history.",
                "A TC import either persists its complete entry, resource-link and staging result or leaves none of that batch persisted.",
                "Socket, tool, fixture and equipment requirements remain distinct node and link types after TC import.",
            ),
            "business_invariants": _BOP_ENTRY_BULK_CHANGE_RULES,
            "no_business_invariant_reason": None,
        })
    elif spec.id == "craft.bop.entry.relation.list":
        updates.update({
            "business_effect": (
                "Return one cursor-bounded page of direct or descendant relations for a caller-scoped BOP entry."
            ),
            "business_acceptance_criteria": (
                "Every returned relation belongs to the requested BOP version and revision.",
                "A page contains at most 200 relations and exposes an opaque continuation cursor when more rows exist.",
                "Relation reads do not mutate BOP entries, links or linked business entities.",
            ),
            "business_invariants": (),
            "no_business_invariant_reason": (
                "This capability projects existing governed BOP links; version scoping, traversal bounds and the closed result shape are enforced by its repository and contract."
            ),
        })
    elif spec.id == "craft.bop.linked_entity.detail.get":
        updates.update({
            "business_effect": (
                "Return the allowlisted business card for one entity reached through a caller-scoped BOP link identity."
            ),
            "business_acceptance_criteria": (
                "The BOP link must belong to the requested BOP version and revision.",
                "Only fields from the registered entity-type projection are returned; arbitrary tables and columns cannot be requested.",
                "Linked-entity detail reads do not mutate BOP links or linked business entities.",
            ),
            "business_invariants": (),
            "no_business_invariant_reason": (
                "This capability projects one existing governed entity card; link identity, version scoping and field allowlisting are enforced by its repository and closed output contract."
            ),
        })
    return CapabilityDescriptorV2.model_validate({**descriptor.model_dump(), **updates})


def register_capability(registry: Any, spec: Any, handler: Any) -> None:
    governed = _governed_spec(spec)
    registry.register(governed, handler, descriptor=descriptor_for(governed))


class NativeContractRegistry:
    """Intercept legacy module registration at the Craft provider boundary."""

    def __init__(self, registry: Any) -> None:
        self._registry = registry

    def register(self, spec: Any, handler: Any) -> None:
        register_capability(self._registry, spec, handler)


__all__ = ["NativeContractRegistry", "descriptor_for", "register_capability"]

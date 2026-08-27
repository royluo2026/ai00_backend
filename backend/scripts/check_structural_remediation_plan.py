"""Build and verify the Task 3B.3f structural owner-service execution plan."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
PLAN_PATH = ROOT / "docs/governance/capability-v2-structural-remediation-plan.json"
MARKDOWN_PATH = ROOT / "docs/governance/capability-v2-structural-remediation-plan.md"
INVENTORY_PATH = ROOT / "docs/governance/capability-coverage-review/generated/web_route_inventory.json"
MANIFEST_PATHS = (
    "docs/governance/base-structural-web-remediation.json",
    "docs/governance/integration-structural-web-remediation.json",
    "docs/governance/craft-agent-project-structural-web-remediation.json",
)

PROHIBITED_DISPOSITIONS = {"operations_excluded", "bff", "bff_registered", "operations"}
REQUIRED_GROUP_FIELDS = {
    "group_id", "package_id", "method", "normalized_route", "occurrences",
    "owner_domain", "owner_service", "owner_service_source", "current_blocker_evidence", "service_boundary",
    "transaction_model", "target_capability", "permission_object_scope",
    "contract_security_rules", "migration_strategy", "tests", "dependencies", "cross_domain_links",
    "approval", "exit_criteria", "implementation_disposition",
}


def _package(
    *, owner_domain: str, owner_service: str, boundary: str, security: list[str],
    tests: list[str], dependencies: list[str], approval: str | None = None,
    owner_service_source: str | None = None,
) -> dict[str, Any]:
    return {
        "owner_domain": owner_domain, "owner_service": owner_service,
        "owner_service_source": owner_service_source, "service_boundary": boundary, "contract_security_rules": security,
        "tests": tests, "dependencies": dependencies, "approval_gate": approval,
    }


PACKAGES: dict[str, dict[str, Any]] = {
    "base_plugin_lifecycle": _package(
        owner_domain="base", owner_service="backend.plugin_platform.service",
        boundary="Public marketplace lifecycle service; REST compatibility and Gateway provider call the same signed-release transition API.",
        security=["signed publisher release and dependency compatibility", "tenant-scoped installation lock and audit event", "no arbitrary URL or secret logging"],
        tests=["Gateway permission/tenant allow-deny", "replay/rollback/data-policy boundary", "signature/dependency/audit regression"],
        dependencies=["signed marketplace release registry", "plugin installation migration"],
        approval="Product/security must decide whether the obsolete arbitrary-URL flows are retired or mapped to signed marketplace acquisition.",
    ),
    "base_annotations": _package(
        owner_domain="base", owner_service="base.self_annotation_service",
        boundary="New public Base self-annotation service, with compatibility handlers and providers delegating to it rather than sharing router SQL.",
        security=["self-only user scope", "closed attachment summary/reference schema", "no opaque attachment JSON or secret-derived fields"],
        tests=["self/non-self Gateway authorization", "closed input/output validation", "write replay and attachment-retention boundary"],
        dependencies=["annotation aggregate migration", "attachment reference policy"],
        approval="Product/security must select the closed attachment projection and retention semantics; the existing arbitrary attachment records are not safely inferable.",
    ),
    "base_identity_profile": _package(
        owner_domain="base", owner_service="base.identity_profile_service",
        boundary="Public Base identity projection service shared by session compatibility handler and Gateway provider.",
        security=["actor-bound self scope", "allowlisted profile/grant projection", "never expose raw grants or permission blobs"],
        tests=["anonymous/self/other-user denial", "closed output schema", "redaction of grants and permissions"],
        dependencies=["identity projection contract"],
        approval="Security/product must approve which profile and effective-grant fields are browser-visible.",
    ),
    "base_saved_views": _package(
        owner_domain="base", owner_service="base.saved_view_service",
        boundary="New public Base saved-view aggregate service, used by Gateway and legacy adapter; it owns view records, sharing, copying, and revisions.",
        security=["owner/team/share visibility", "closed semantic view schema", "optimistic revision and idempotency key for writes"],
        tests=["owner/non-owner/team visibility", "copy/update/delete replay and conflict", "schema rejects arbitrary configuration"],
        dependencies=["saved-view storage migration", "approved semantic view configuration"],
        approval="Product must choose the finite saved-view configuration language and copy/share semantics; current dynamic config cannot be inferred safely.",
    ),
    "integration_connector": _package(
        owner_domain="integration", owner_service="plugins.integration.integration_backend.application.service.IntegrationApplication",
        boundary="Existing public IntegrationApplication with a credential-vault port and connector-runtime port; both legacy adapters and providers invoke that boundary.",
        security=["opaque credential_ref only", "network allowlist, timeout and bounded discovery", "masked outputs, structured external failure and no secret evidence"],
        tests=["tenant/cross-workspace Gateway authorization", "credential redaction", "connector-runtime timeout/outcome-unknown and idempotency"],
        dependencies=["credential-vault write channel", "connector runtime policy", "connector aggregate migration"],
        approval="Product/security must decide whether each stale browser connector flow is retained and authorize credential enrolment plus external-network policy.",
    ),
    "integration_mapping": _package(
        owner_domain="integration", owner_service="plugins.integration.integration_backend.application.service.IntegrationApplication",
        boundary="Existing public IntegrationApplication mapping operations backed by Integration repository and connector-runtime ports; no cross-domain database adapter.",
        security=["closed field-mapping grammar and restricted transforms", "owner/team binding", "bounded preview/import and safe external error classes"],
        tests=["mapping scope and revision conflict", "transform schema rejection", "preview/import timeout and outcome recovery"],
        dependencies=["connector package", "mapping aggregate migration", "target-capability validation"],
        approval="Product must decide whether absent legacy mapping routes become supported governed flows or are removed; that intent is not encoded in a provider.",
    ),
    "craft_library": _package(
        owner_domain="craft", owner_service="plugins.craft.craft_backend.application.library_lifecycle_service",
        boundary="New public Craft library lifecycle service that validates references and performs one lifecycle transition; no route-shaped SQL provider.",
        security=["Craft workspace/object scope", "reference/lifecycle validation", "audit event and revision lock"],
        tests=["referenced/unreferenced delete behavior", "owner/non-owner authorization", "replay and lifecycle conflict"],
        dependencies=["library reference index", "Craft lifecycle audit migration"],
        approval="Product must decide hard-delete versus obsolete/archive behavior because the only existing outcome is obsolete, not delete.",
    ),
    "craft_rules": _package(
        owner_domain="craft", owner_service="plugins.craft.craft_backend.application.rules.RuleService",
        boundary="Public Craft RuleService expanded into bounded definition/lifecycle/evaluation/waiver operations; compatibility and Gateway must share it.",
        security=["workspace rule ownership", "closed rule-definition grammar", "audit, revision lock, explicit confirmation and no generic JSON"],
        tests=["rule lifecycle authorization and revision conflict", "definition/schema rejection", "evaluation/waiver audit and idempotency"],
        dependencies=["rule aggregate migration", "approved closed rule-definition vocabulary"],
        approval="Product/security must approve the finite rule-definition and mutable lifecycle semantics; existing routes have no equivalent public service.",
    ),
    "craft_bop_lifecycle": _package(
        owner_domain="craft", owner_service="plugins.craft.craft_backend.application.bop_version_lifecycle_service",
        boundary="New public Craft BOP-version lifecycle service selected before Project list dispatch; it owns the conditional bop_version branch only.",
        security=["Craft version scope and expected revision", "archive lifecycle/audit", "no Project-list relabeling or direct SQL dispatch"],
        tests=["conditional branch selection", "BOP revision/authorization", "Project list branch remains unchanged"],
        dependencies=["BOP version aggregate", "conditional dispatch adapter"],
        approval="Product must confirm BOP-version archive/delete lifecycle and list projection; these are distinct from Project list semantics.",
    ),
    "agent_bounded_runtime": _package(
        owner_domain="agent", owner_service="plugins.agent.agent_backend.application.bounded_runtime_service",
        boundary="New public Agent bounded-runtime service with a fixed tool/node allowlist, sandbox executor, durable run records and audit lineage.",
        security=["no eval or browser supplied executable config", "authorization, sandbox, timeout and resource limits", "confirmation, pause-token integrity and outcome recovery"],
        tests=["allowlist/sandbox/timeout/resource limit", "cross-workspace authorization", "resume idempotency and audit lineage"],
        dependencies=["sandbox runtime", "durable run/pause-token store", "Agent execution audit"],
        approval="Security/product must approve the executable allowlist, sandbox/resource policy, confirmation policy and recovery behavior before implementation.",
    ),
    "project_approval": _package(
        owner_domain="project_management", owner_service="plugins.project_management.project_management_backend.application.service.ProjectManagementApplication",
        owner_service_source="plugins/project_management/project_management_backend/application/service.py",
        boundary="Existing ProjectManagementApplication approval.orders.reject boundary, extended in-package with notification outbox, audit and idempotency rather than a fabricated Project service.",
        security=["tenant/order scope and approver authorization", "revision/idempotency", "transactional audit plus durable notification outbox"],
        tests=["approver/non-approver/cross-tenant denial", "rejection replay and notification outbox", "state conflict and outcome recovery"],
        dependencies=["Project approval aggregate", "notification outbox migration"],
        approval="Product must confirm rejection notification recipients/templates because current candidate omits the legacy notification effect.",
    ),
}

PACKAGE_CROSS_DOMAIN_LINKS = {
    "base_plugin_lifecycle": ["Base identity/tenant context is supplied through the public context port; no router import."],
    "base_annotations": ["Attachment metadata is reached only through a typed Base attachment-reference port."],
    "base_identity_profile": ["None; this remains a Base-only projection."],
    "base_saved_views": ["None; sharing is enforced in the Base aggregate rather than delegated to a router."],
    "integration_connector": ["Credential vault and connector runtime are typed ports; credentials never cross into browser/Gateway evidence."],
    "integration_mapping": ["Exact stable target capability is resolved through the Catalog target index, never a cross-domain database query."],
    "craft_library": ["Reference checks use typed Craft ports only; no direct reads into other domain tables."],
    "craft_rules": ["None; rule evaluation remains within Craft's public service boundary."],
    "craft_bop_lifecycle": ["Project compatibility adapter selects item_type=bop_version then invokes Craft; it neither owns nor queries BOP tables."],
    "agent_bounded_runtime": ["Any Craft/Project data access is a bounded Gateway capability invocation, not direct SQL or imported routers."],
    "project_approval": ["Notifications are emitted through the transactional outbox, not a best-effort cross-domain HTTP call."],
}


def _spec(package_id: str, target: str, transaction: str, strategy: str, *, approval_required: bool = False) -> dict[str, Any]:
    return {"package_id": package_id, "target_capability": target, "transaction_model": transaction,
            "migration_strategy": strategy, "approval_required": approval_required}


GROUP_SPECS: dict[tuple[str, str], dict[str, Any]] = {
    ("DELETE", "/api/plugin/uninstall/{dynamic}"): _spec("base_plugin_lifecycle", "base.plugin.installation.transition.uninstall@1", "one tenant installation transaction with release/data-policy lock and audit event", "Replace only after signed marketplace uninstall contract; otherwise retire the dead browser call.", approval_required=True),
    ("POST", "/api/plugin/install"): _spec("base_plugin_lifecycle", "base.plugin.installation.request.create@1", "one tenant installation transaction; release verification and mount activation are explicit lifecycle steps", "Replace arbitrary URL input with signed release selection and explicit grants; otherwise retire.", approval_required=True),
    ("GET", "/api/self_ann/{dynamic}"): _spec("base_annotations", "base.self_annotation.record.get@1", "read-only self-scoped query", "Add a closed attachment summary/reference projection and migrate through Gateway.", approval_required=True),
    ("GET", "/api/self_ann/list"): _spec("base_annotations", "base.self_annotation.search@1", "read-only self-scoped bounded query", "Add bounded search/pagination and closed attachment projection before Gateway migration.", approval_required=True),
    ("PUT", "/api/self_ann/{dynamic}"): _spec("base_annotations", "base.self_annotation.change.apply@1", "one self-annotation revision transaction with attachment reference validation", "Use expected revision and idempotency key; migrate only after attachment contract approval.", approval_required=True),
    ("GET", "/api/users/me"): _spec("base_identity_profile", "base.identity.session.profile.get@1", "read-only actor-bound projection", "Create a redacted closed profile projection and migrate the session call.", approval_required=True),
    ("GET", "/api/views"): _spec("base_saved_views", "base.saved_view.search@1", "read-only owner/team/share scoped query", "Define finite saved-view query/config schema then migrate list callers.", approval_required=True),
    ("POST", "/api/views"): _spec("base_saved_views", "base.saved_view.create@1", "one saved-view create transaction with owner/share validation", "Use closed config, idempotency key and returned revision.", approval_required=True),
    ("DELETE", "/api/views/{dynamic}"): _spec("base_saved_views", "base.saved_view.delete@1", "one revision-locked delete transaction with audit", "Use expected revision; migrate after ownership and retention policy are approved.", approval_required=True),
    ("PATCH", "/api/views/{dynamic}"): _spec("base_saved_views", "base.saved_view.update@1", "one revision-locked update transaction with audit", "Use closed patch grammar and expected revision.", approval_required=True),
    ("POST", "/api/views/{dynamic}/copy"): _spec("base_saved_views", "base.saved_view.copy@1", "one source-read plus destination-create transaction with idempotency", "Define copy/share/ownership semantics and migrate with an idempotency key.", approval_required=True),
    ("GET", "/api/ext-datasources"): _spec("integration_connector", "integration.connector.search@1", "read-only actor/team bound query", "Decide retention, then normalize browser projection to the existing closed connector search contract.", approval_required=True),
    ("POST", "/api/ext-datasources"): _spec("integration_connector", "integration.connector.create@1", "one connector aggregate transaction; credential material is written only through vault port", "Replace plaintext browser credentials with credential_ref secure enrolment.", approval_required=True),
    ("PATCH", "/api/ext-datasources/{dynamic}"): _spec("integration_connector", "integration.connector.update@1", "one revision-locked connector aggregate transaction", "Use closed update and credential_ref rotation semantics; no raw config pass-through.", approval_required=True),
    ("GET", "/api/ext-datasources/{dynamic}/tables"): _spec("integration_connector", "integration.connector.schema.discover@1", "bounded external read through runtime port; no fabricated atomic DB transaction", "Add timeout/result cap/error policy and return safe schema metadata.", approval_required=True),
    ("POST", "/api/ext-datasources/{dynamic}/test"): _spec("integration_connector", "integration.connector.connection.test@1", "bounded external probe with durable operation result when outcome is uncertain", "Use runtime port test double in tests and disclose outcome-unknown semantics.", approval_required=True),
    ("GET", "/api/ext-field-mappings"): _spec("integration_mapping", "integration.field_mapping.search@1", "read-only actor/team bound bounded query", "Define exact field-mapping list projection instead of adapting singular mapping.get.", approval_required=True),
    ("PUT", "/api/ext-field-mappings/batch"): _spec("integration_mapping", "integration.field_mapping.batch.update@1", "one bounded batch transaction with per-item revision conflicts", "Define batch limit and all-or-partial success contract; do not relabel generic mapping.update.", approval_required=True),
    ("GET", "/api/ext-mappings"): _spec("integration_mapping", "integration.mapping.search@1", "read-only actor/team bound query", "Normalize browser projection to closed mapping search after retention decision.", approval_required=True),
    ("POST", "/api/ext-mappings"): _spec("integration_mapping", "integration.mapping.create@1", "one mapping aggregate transaction with target-capability validation", "Use restricted transform grammar and exact target version validation.", approval_required=True),
    ("GET", "/api/ext-mappings/{dynamic}/columns"): _spec("integration_mapping", "integration.mapping.source_columns.discover@1", "bounded external discovery through connector runtime", "Bind mapping to connector, cap result and apply runtime timeout policy.", approval_required=True),
    ("POST", "/api/ext-mappings/{dynamic}/import"): _spec("integration_mapping", "integration.mapping.import.start@1", "durable asynchronous import operation with idempotency and recoverable status", "Replace synthetic sync.start response with a real run/outcome resource.", approval_required=True),
    ("GET", "/api/ext-mappings/{dynamic}/preview"): _spec("integration_mapping", "integration.mapping.preview@1", "bounded external preview through runtime port", "Cap preview rows, redact values and expose structured timeout/outcome status.", approval_required=True),
    ("DELETE", "/api/craft_lib/equipments/{dynamic}"): _spec("craft_library", "craft.library.equipment.retire@1", "one Craft library transaction locking item and references plus audit", "Implement approved lifecycle outcome; do not map delete to an unrelated obsolete call.", approval_required=True),
    ("DELETE", "/api/craft_lib/fixtures/{dynamic}"): _spec("craft_library", "craft.library.fixture.retire@1", "one Craft library transaction locking item and references plus audit", "Implement approved lifecycle outcome; do not map delete to an unrelated obsolete call.", approval_required=True),
    ("GET", "/api/rule-engine/check-entry"): _spec("craft_rules", "craft.rule.entry.evaluate@1", "bounded read/evaluation with audit record; no arbitrary executable expression", "Implement exact entry-check semantics, not CEL or BOP audit substitution.", approval_required=True),
    ("PUT", "/api/rules/{dynamic}"): _spec("craft_rules", "craft.rule.definition.change.apply@1", "one revision-locked rule-definition transaction plus audit", "Define finite rule grammar before migration; reject arbitrary rule_definition JSON.", approval_required=True),
    ("POST", "/api/rules/{dynamic}/activate"): _spec("craft_rules", "craft.rule.lifecycle.activate@1", "one rule lifecycle transition with audit and expected state", "Implement mutable-rule activation only after its distinct lifecycle contract is approved.", approval_required=True),
    ("POST", "/api/rules/{dynamic}/deviations"): _spec("craft_rules", "craft.rule.deviation.create@1", "one rule deviation/waiver transaction with evidence and audit", "Do not substitute release waiver; model legacy deviation evidence exactly.", approval_required=True),
    ("POST", "/api/rules/{dynamic}/suspend"): _spec("craft_rules", "craft.rule.lifecycle.suspend@1", "one rule lifecycle transition with audit and expected state", "Implement a mutable-rule suspension service; no missing-handler adapter.", approval_required=True),
    ("GET", "/api/lists"): _spec("craft_bop_lifecycle", "craft.bop.version.search@1", "read-only Craft BOP-version query selected by item_type before Project dispatch", "Migrate only bop_version conditional branch; preserve Project list behavior.", approval_required=True),
    ("DELETE", "/api/lists/{dynamic}"): _spec("craft_bop_lifecycle", "craft.bop.version.archive@1", "one Craft BOP-version revision-locked archive transaction with audit", "Migrate only bop_version conditional branch with expected_revision; preserve Project delete behavior.", approval_required=True),
    ("POST", "/api/flows/test-node"): _spec("agent_bounded_runtime", "agent.workflow.node.test.execute@1", "durable bounded sandbox run with timeout/resource limits and auditable result", "Route through fixed node allowlist and public runtime service; never arbitrary dispatch.", approval_required=True),
    ("POST", "/api/skills/canvas-options"): _spec("agent_bounded_runtime", "agent.canvas.options.resolve@1", "bounded deterministic resolver with actor/workspace audit", "Expose only approved option resolvers; browser configuration is data, never executable code.", approval_required=True),
    ("POST", "/api/skills/execute-canvas"): _spec("agent_bounded_runtime", "agent.canvas.execution.start@1", "durable sandbox run with confirmation, idempotency, pause token and outcome recovery", "Do not substitute generic agent.run mutation; build exact canvas runtime path.", approval_required=True),
    ("POST", "/api/skills/resume-canvas"): _spec("agent_bounded_runtime", "agent.canvas.execution.resume@1", "durable resume transaction locking validated pause token and run state", "Validate signed pause token, replay behavior and sandbox policy; no generic run mutation.", approval_required=True),
    ("POST", "/api/approval/orders/{dynamic}/reject"): _spec("project_approval", "project.approval.order.reject@1", "one Project approval transition transaction with audit and transactional notification outbox", "Implement exact reject plus notification semantics; do not use candidate that omits notification.", approval_required=True),
}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_plan(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _occurrences(entry: Mapping[str, Any]) -> list[dict[str, Any]]:
    values = entry.get("final_occurrences") or entry.get("occurrences") or entry.get("old_occurrences")
    if not isinstance(values, list) or not all(isinstance(item, Mapping) for item in values):
        raise ValueError("manifest occurrence evidence missing")
    return [dict(item) for item in values]


def source_groups(root: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """Reconcile group membership from all independent manifests, then use fresh inventory IDs."""
    manifests: dict[tuple[str, str], dict[str, Any]] = {}
    for relative in MANIFEST_PATHS:
        path = root / relative
        payload = json.loads(path.read_text(encoding="utf-8"))
        for entry in payload.get("entries", []):
            if entry.get("final_disposition") != "unresolved":
                continue
            key = (entry.get("method"), entry.get("normalized_route"))
            if not all(isinstance(value, str) and value for value in key) or key in manifests:
                raise ValueError("manifest group identity invalid or duplicate")
            manifests[key] = {"manifest_path": relative, "entry": entry, "manifest_occurrence_count": len(_occurrences(entry))}
    inventory = json.loads((root / INVENTORY_PATH.relative_to(root)).read_text(encoding="utf-8"))
    for route in inventory.get("routes", []):
        if route.get("disposition") != "unresolved":
            continue
        key = (route.get("method"), route.get("normalized_route"))
        if key not in manifests:
            raise ValueError(f"canonical unresolved group absent from remediation manifests: {key}")
        manifests[key].setdefault("occurrences", []).append(dict(route))
    for key, evidence in manifests.items():
        occurrences = evidence.get("occurrences", [])
        if len(occurrences) != evidence["manifest_occurrence_count"]:
            raise ValueError(f"manifest/canonical occurrence count drift: {key}")
    if len(manifests) != 37 or sum(len(item.get("occurrences", [])) for item in manifests.values()) != 45:
        raise ValueError("final structural source scope drift")
    return manifests


def build_plan(root: Path) -> dict[str, Any]:
    sources = source_groups(root)
    if set(sources) != set(GROUP_SPECS):
        raise ValueError("owner-service specification does not exactly cover fresh source groups")
    groups = []
    for key in sorted(sources):
        source, spec = sources[key], GROUP_SPECS[key]
        package = PACKAGES[spec["package_id"]]
        entry = source["entry"]
        blocker = entry.get("unresolved_reason") or entry.get("non_equivalence") or "No provider-equivalent source boundary exists."
        groups.append({
            "group_id": f"{key[0]} {key[1]}", "package_id": spec["package_id"],
            "method": key[0], "normalized_route": key[1], "occurrences": source["occurrences"],
            "owner_domain": package["owner_domain"], "owner_service": package["owner_service"], "owner_service_source": package["owner_service_source"],
            "current_blocker_evidence": {"manifest_path": source["manifest_path"], "provider_anchor": entry.get("provider_anchor"), "provider_source_sha256": entry.get("provider_source_sha256"), "reason": blocker},
            "service_boundary": package["service_boundary"], "transaction_model": spec["transaction_model"],
            "target_capability": spec["target_capability"], "permission_object_scope": package["contract_security_rules"][0],
            "contract_security_rules": package["contract_security_rules"], "migration_strategy": spec["migration_strategy"],
            "tests": package["tests"], "dependencies": package["dependencies"], "cross_domain_links": PACKAGE_CROSS_DOMAIN_LINKS[spec["package_id"]],
            "approval": {"required": spec["approval_required"], "decision": package["approval_gate"] if spec["approval_required"] else None},
            "exit_criteria": ["public owner service and Gateway provider share this boundary", "closed contract and scope tests pass", "fresh canonical occurrence migrates without REST fallback", "no operations/BFF/canonical-disposition relabeling"],
            "implementation_disposition": "owner_service_required",
        })
    source_artifacts = [{"path": relative, "sha256": _sha256(root / relative)} for relative in (*MANIFEST_PATHS, str(INVENTORY_PATH.relative_to(root)))]
    plan = {"schema_version": "1.0.0", "artifact_id": "capability-v2-structural-remediation-plan",
            "source_artifacts": source_artifacts, "counts": {"groups": len(groups), "occurrences": sum(len(group["occurrences"]) for group in groups)},
            "anti_patterns": ["no private-router import", "no direct SQL provider", "no generic JSON contracts", "no secret logging", "no auto-confirm", "no unbounded runtime execution", "no fabricated atomicity", "no silent REST fallback"],
            "packages": [{"package_id": key, **value} for key, value in PACKAGES.items()], "groups": groups}
    plan["content_sha256"] = "sha256:" + hashlib.sha256(_canonical(plan).encode("utf-8")).hexdigest()
    return plan


def validate_plan(root: Path, payload: Mapping[str, Any]) -> tuple[str, ...]:
    issues: set[str] = set()
    try:
        sources = source_groups(root)
    except (OSError, ValueError, json.JSONDecodeError):
        return ("source_evidence_invalid",)
    if payload.get("counts") != {"groups": 37, "occurrences": 45}:
        issues.add("count_mismatch")
    if payload.get("anti_patterns") != ["no private-router import", "no direct SQL provider", "no generic JSON contracts", "no secret logging", "no auto-confirm", "no unbounded runtime execution", "no fabricated atomicity", "no silent REST fallback"]:
        issues.add("anti_pattern_policy_mismatch")
    artifacts = payload.get("source_artifacts")
    expected_artifacts = [{"path": relative, "sha256": _sha256(root / relative)} for relative in (*MANIFEST_PATHS, str(INVENTORY_PATH.relative_to(root)))]
    if artifacts != expected_artifacts:
        issues.add("source_artifact_hash_mismatch")
    groups = payload.get("groups")
    if not isinstance(groups, list):
        return tuple(sorted(issues | {"groups_invalid"}))
    keys = [(item.get("method"), item.get("normalized_route")) for item in groups if isinstance(item, Mapping)]
    if len(keys) != len(set(keys)) or set(keys) != set(sources) or len(groups) != len(sources):
        issues.add("group_identity_mismatch")
    expected_ids = {raw["occurrence_id"] for value in sources.values() for raw in value["occurrences"]}
    actual_ids: set[str] = set()
    for group in groups:
        if not isinstance(group, Mapping) or not REQUIRED_GROUP_FIELDS <= set(group):
            issues.add("group_contract_missing")
            continue
        key = (group["method"], group["normalized_route"])
        spec = GROUP_SPECS.get(key)
        if spec is None:
            continue
        package = PACKAGES[spec["package_id"]]
        if group.get("owner_domain") != package["owner_domain"]:
            issues.add("owner_domain_mismatch")
        if group.get("owner_service") != package["owner_service"]:
            issues.add("owner_service_mismatch")
        if group.get("owner_service_source") != package["owner_service_source"]:
            issues.add("owner_service_source_mismatch")
        source_path = group.get("owner_service_source")
        if source_path is not None and (not isinstance(source_path, str) or not (root / source_path).is_file()):
            issues.add("owner_service_source_missing")
        if group.get("package_id") != spec["package_id"] or group.get("target_capability") != spec["target_capability"]:
            issues.add("owner_service_mismatch")
        if group.get("implementation_disposition") in PROHIBITED_DISPOSITIONS:
            issues.add("forbidden_disposition")
        if group.get("implementation_disposition") != "owner_service_required":
            issues.add("implementation_disposition_mismatch")
        occurrences = group.get("occurrences")
        if not isinstance(occurrences, list):
            issues.add("occurrence_identity_mismatch")
            continue
        actual_ids.update(item.get("occurrence_id") for item in occurrences if isinstance(item, Mapping) and isinstance(item.get("occurrence_id"), str))
        expected = sources[key]["occurrences"]
        if occurrences != expected:
            issues.add("occurrence_identity_mismatch")
    if actual_ids != expected_ids or len(actual_ids) != 45:
        issues.add("occurrence_identity_mismatch")
    return tuple(sorted(issues))


def render_markdown(plan: Mapping[str, Any]) -> str:
    lines = ["# Capability V2 Structural Owner-Service Remediation Plan", "", "This plan reconciles the fresh canonical unresolved Web inventory to the three independent remediation manifests. It is an implementation sequence, not an operations or BFF exemption.", "", f"- Scope: **{plan['counts']['occurrences']} occurrences / {plan['counts']['groups']} root-cause groups**.", "- Implementation disposition for every group: `owner_service_required`.", "- Global prohibitions: " + "; ".join(plan["anti_patterns"]) + ".", "", "## Ordered packages", ""]
    for number, package in enumerate(plan["packages"], 1):
        approval = package["approval_gate"] or "No product/security decision is currently identified."
        links = PACKAGE_CROSS_DOMAIN_LINKS[package["package_id"]]
        lines += [f"### {number}. `{package['package_id']}`", "", f"- Owner service: `{package['owner_service']}` ({package['owner_domain']}).", f"- Boundary: {package['service_boundary']}", f"- Dependencies: {', '.join(package['dependencies'])}.", f"- Cross-domain links: {'; '.join(links)}", f"- Decision gate: {approval}", ""]
    lines += ["## Group execution cards", ""]
    for group in plan["groups"]:
        occurrences = ", ".join(item["occurrence_id"] for item in group["occurrences"])
        approval = group["approval"]["decision"] if group["approval"]["required"] else "None; implement from existing source evidence."
        lines += [f"### `{group['group_id']}`", "", f"- Occurrences: {occurrences}", f"- Owner/service: `{group['owner_domain']}` / `{group['owner_service']}`", f"- Blocker evidence: `{group['current_blocker_evidence']['manifest_path']}`; `{group['current_blocker_evidence']['provider_anchor']}`; {group['current_blocker_evidence']['reason']}", f"- Service boundary and transaction: {group['service_boundary']} {group['transaction_model']}.", f"- Target: `{group['target_capability']}`. Scope: {group['permission_object_scope']}.", f"- Contract/security: {'; '.join(group['contract_security_rules'])}.", f"- Migration: {group['migration_strategy']}", f"- Tests: {'; '.join(group['tests'])}. Dependencies: {', '.join(group['dependencies'])}. Cross-domain links: {'; '.join(group['cross_domain_links'])}.", f"- Approval: {approval}", f"- Exit: {'; '.join(group['exit_criteria'])}.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    plan = build_plan(ROOT)
    rendered, markdown = _canonical(plan), render_markdown(plan)
    if args.write:
        PLAN_PATH.write_text(rendered, encoding="utf-8", newline="\n")
        MARKDOWN_PATH.write_text(markdown, encoding="utf-8", newline="\n")
    if args.check:
        if not PLAN_PATH.exists() or not MARKDOWN_PATH.exists() or PLAN_PATH.read_text(encoding="utf-8") != rendered or MARKDOWN_PATH.read_text(encoding="utf-8") != markdown:
            raise SystemExit("structural remediation plan is stale")
        issues = validate_plan(ROOT, load_plan(PLAN_PATH))
        if issues:
            raise SystemExit("structural remediation plan invalid: " + ", ".join(issues))
    print("groups=37 occurrences=45")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

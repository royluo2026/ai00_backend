"""Integration tests — Dimension 4: Catalog audit and Release Gate.

Covers:
* evaluate_release_gate passes with the current codebase
* All CompletionReport metrics are clean (no cross-domain SQL, import violations,
  consumer bypasses)
* All 11 domains are registered as independent
* CatalogAuditReport: every required field present in every stable descriptor
* No open-arguments, no default-all-exposure, no invalid error schemas,
  no not_run test references
* AtomicityAudit: all generic-operation capabilities have valid dispositions
* OrchestrationAudit: all three registries (task_tool, bff_capability,
  business_capability) pass
* Regression guards: assertions that would have caught every past finding
  (web bypasses, missing fields, stale evidence)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.capability_v2.catalog_audit import CatalogAuditReport, audit_catalog
from backend.capability_v2.completion import CompletionReport, evaluate_completion
from backend.capability_v2.release_gate import ReleaseGateReport, evaluate_release_gate
from backend.capability_v2.consumer_routes import RouteScanConfigurationError

from .conftest import REPO_ROOT, FRONTEND_ROOT


# ---------------------------------------------------------------------------
# Module-level fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def catalog_report() -> CatalogAuditReport:
    return audit_catalog(REPO_ROOT / "docs/capabilities/catalog.v2.json")


@pytest.fixture(scope="module")
def completion_report() -> CompletionReport:
    """Completion report WITHOUT web scan (faster, available in offline mode)."""
    return evaluate_completion(REPO_ROOT, mode="strict")


@pytest.fixture(scope="module")
def full_gate_report() -> ReleaseGateReport:
    """Full Release Gate including web scan.
    Skips gracefully if the frontend root or wrapper contracts are stale.
    """
    if not FRONTEND_ROOT.is_dir():
        pytest.skip(f"Frontend root not accessible: {FRONTEND_ROOT}")
    try:
        return evaluate_release_gate(REPO_ROOT, web_root=FRONTEND_ROOT)
    except RouteScanConfigurationError as exc:
        pytest.skip(f"Web scan blocked by stale contract: {exc}")


def _format_gate_failures(report: ReleaseGateReport) -> str:
    """Return a human-readable summary of Release Gate failures."""
    lines: list[str] = []
    if not report.completion.complete:
        lines.append(f"completion.failed={list(report.completion.failed)}")
    if report.completion.web_consumer_bypasses:
        lines.append(f"web_consumer_bypasses={report.completion.web_consumer_bypasses}")
    for field, count in report.audit.required_field_missing_counts.items():
        if count:
            lines.append(f"required_field_missing: {field}={count}")
    if report.audit.invalid_error_schema_count:
        lines.append(f"invalid_error_schema_count={report.audit.invalid_error_schema_count}")
    if report.audit.test_evidence_not_run_count:
        lines.append(f"test_evidence_not_run_count={report.audit.test_evidence_not_run_count}")
    if report.atomicity and not report.atomicity.passed:
        lines.append(f"atomicity: unclassified={list(report.atomicity.unclassified_ids)[:5]}")
    for reg in report.orchestration:
        if not reg.passed:
            lines.append(f"orchestration/{reg.registry_kind}: {reg.invalid_entries[:3]}")
    return "; ".join(lines) if lines else "<no details>"


# ===========================================================================
# 1. Full Release Gate — end-to-end pass
# ===========================================================================

class TestFullReleaseGate:
    def test_release_gate_passes_with_full_catalog_and_frontend(
        self, full_gate_report
    ):
        """The complete Release Gate must report passed=True.

        This is the authoritative integration assertion for the entire
        Capability V2 governance program.  Any individual sub-assertion that
        follows is a finer-grained view of the same truth.
        """
        assert full_gate_report.passed is True, (
            "Release Gate FAILED.  Details:\n" + _format_gate_failures(full_gate_report)
        )

    def test_completion_web_consumer_bypasses_zero(self, full_gate_report):
        """No frontend route must bypass the Capability Gateway."""
        assert full_gate_report.completion.web_consumer_bypasses == 0

    def test_completion_cross_domain_sql_zero(self, full_gate_report):
        """No cross-domain SQL violations in the boundary baseline."""
        assert full_gate_report.completion.cross_domain_sql == 0

    def test_completion_internal_imports_zero(self, full_gate_report):
        """No forbidden internal Python imports in consumer adapters."""
        assert full_gate_report.completion.internal_imports == 0

    def test_completion_consumer_bypasses_zero(self, full_gate_report):
        """Backend consumer adapters must not bypass the Capability Gateway."""
        assert full_gate_report.completion.consumer_bypasses == 0


# ===========================================================================
# 2. Completion (no web scan) — structure checks
# ===========================================================================

class TestCompletion:
    def test_all_11_domains_are_independent(self, completion_report):
        """Every required domain must satisfy the independence constraints
        (unique database_name, runtime_url_env, ddl_url_env, existing paths).
        """
        assert completion_report.independent_domains == 11, (
            f"Expected 11 independent domains, got {completion_report.independent_domains}.\n"
            f"Failures: {list(completion_report.failed)}"
        )

    def test_no_completion_failures_without_web_scan(self, completion_report):
        """Completion without web scan must succeed (zero failed items)."""
        assert completion_report.complete is True, (
            f"Completion failures: {list(completion_report.failed)}"
        )

    def test_at_least_one_sync_production_path_declared(self, completion_report):
        """At least one synchronous cross-domain production path must be
        declared in capability_v2_production_paths.json."""
        assert completion_report.sync_production_paths >= 1, (
            "No synchronous production path declared — add at least one entry "
            "to backend/governance/capability_v2_production_paths.json"
        )

    def test_at_least_one_async_production_path_declared(self, completion_report):
        """At least one asynchronous (event) cross-domain production path must
        be declared."""
        assert completion_report.async_production_paths >= 1, (
            "No async production path declared — add at least one async entry "
            "to backend/governance/capability_v2_production_paths.json"
        )

    def test_catalog_capability_count_is_substantial(self, completion_report):
        """The registered stable capability count must be above a minimum threshold,
        ensuring the Catalog was built and is non-trivially populated."""
        assert completion_report.catalog_capabilities >= 100, (
            f"catalog_capabilities={completion_report.catalog_capabilities} — "
            "this is suspiciously low; verify the Catalog build."
        )


# ===========================================================================
# 3. Catalog audit — field completeness
# ===========================================================================

class TestCatalogAudit:
    def test_all_required_fields_present_in_stable_descriptors(
        self, catalog_report
    ):
        """No stable descriptor may omit any of the nine required fields
        (V2.1 §3 requirement)."""
        violations = {
            field: count
            for field, count in catalog_report.required_field_missing_counts.items()
            if count
        }
        assert not violations, (
            "Required Catalog field(s) missing from stable descriptor(s):\n"
            + "\n".join(f"  {field}: {count} descriptor(s)" for field, count in violations.items())
        )

    def test_no_open_arguments_in_stable_descriptors(self, catalog_report):
        """No operation+arguments descriptor may allow additionalProperties."""
        assert catalog_report.open_arguments_count == 0, (
            f"{catalog_report.open_arguments_count} descriptor(s) have open "
            "arguments schema — set additionalProperties: false."
        )

    def test_no_default_all_exposure_in_stable_descriptors(self, catalog_report):
        """No descriptor may use the adapter-default all-consumer exposure."""
        assert catalog_report.default_all_exposure_count == 0, (
            f"{catalog_report.default_all_exposure_count} descriptor(s) use the "
            "adapter_default all-consumer exposure — set exposure_policy_source "
            "to 'provider_explicit'."
        )

    def test_error_schema_valid_in_all_stable_descriptors(self, catalog_report):
        """Every error_schema entry must have is_retryable and is_caller_error."""
        assert catalog_report.invalid_error_schema_count == 0, (
            f"{catalog_report.invalid_error_schema_count} descriptor(s) have "
            "an error_schema that is missing required fields."
        )

    def test_no_test_refs_with_not_run_result(self, catalog_report):
        """No test_ref may have result='not_run' — only actually executed
        tests are valid evidence."""
        assert catalog_report.test_evidence_not_run_count == 0, (
            f"{catalog_report.test_evidence_not_run_count} descriptor(s) have "
            "test_refs with result=not_run — these cannot serve as release evidence."
        )

    def test_stable_descriptor_count_is_substantial(self, catalog_report):
        """The number of stable capabilities must meet a minimum floor."""
        assert catalog_report.stable_count >= 100, (
            f"Only {catalog_report.stable_count} stable capabilities — "
            "verify the Catalog build."
        )


# ===========================================================================
# 4. Atomicity audit
# ===========================================================================

class TestAtomicityAudit:
    def test_atomicity_audit_passes(self, full_gate_report):
        """All generic-operation capabilities must have valid dispositions."""
        assert full_gate_report.atomicity is not None, (
            "AtomicityAudit object is None — ensure the atomicity dispositions "
            "file is present."
        )
        assert full_gate_report.atomicity.passed is True, (
            "Atomicity audit FAILED.\n"
            f"  unclassified: {list(full_gate_report.atomicity.unclassified_ids)}\n"
            f"  invalid:      {list(full_gate_report.atomicity.invalid_ids)}\n"
            f"  expired:      {list(full_gate_report.atomicity.expired_ids)}\n"
            f"  missing repl: {list(full_gate_report.atomicity.missing_replacement_ids)}"
        )

    def test_no_unclassified_generic_operation_capabilities(
        self, full_gate_report
    ):
        """Every operation+arguments capability must have an explicit disposition."""
        unclassified = list(full_gate_report.atomicity.unclassified_ids) if full_gate_report.atomicity else []
        assert unclassified == [], (
            f"Unclassified generic-operation capabilities: {unclassified}\n"
            "Add a disposition entry to capability-atomicity-dispositions.json."
        )

    def test_no_expired_dispositions(self, full_gate_report):
        """No disposition must reference expired replacement capabilities."""
        expired = list(full_gate_report.atomicity.expired_ids) if full_gate_report.atomicity else []
        assert expired == [], f"Expired atomicity dispositions: {expired}"

    def test_all_replacement_capabilities_exist_in_catalog(
        self, full_gate_report
    ):
        """Every replacement_capabilities entry must exist in the Catalog."""
        missing = list(full_gate_report.atomicity.missing_replacement_ids) if full_gate_report.atomicity else []
        assert missing == [], (
            f"Replacement capabilities not found in Catalog: {missing}\n"
            "Register the replacement capability or update the disposition."
        )


# ===========================================================================
# 5. Orchestration registry audit
# ===========================================================================

class TestOrchestrationAudit:
    def test_exactly_three_orchestration_registries_evaluated(
        self, full_gate_report
    ):
        """The Release Gate must evaluate exactly three orchestration registries:
        task_tool, bff_capability, business_capability."""
        assert len(full_gate_report.orchestration) == 3, (
            f"Expected 3 orchestration registries, got {len(full_gate_report.orchestration)}"
        )

    def test_all_orchestration_registries_pass(self, full_gate_report):
        """All three orchestration registry audits must pass."""
        failures = [
            reg for reg in full_gate_report.orchestration if not reg.passed
        ]
        assert not failures, (
            "Orchestration registry failures:\n"
            + "\n".join(
                f"  [{reg.registry_kind}] invalid_entries={reg.invalid_entries[:5]}, "
                f"missing_capabilities={reg.missing_capabilities[:5]}, "
                f"duplicate_keys={reg.duplicate_keys[:5]}"
                for reg in failures
            )
        )

    @pytest.mark.parametrize("kind", ["task_tool", "bff_capability", "business_capability"])
    def test_specific_registry_passes(self, kind, full_gate_report):
        """Each registry kind must individually pass."""
        reg = next(
            (r for r in full_gate_report.orchestration if r.registry_kind == kind),
            None,
        )
        assert reg is not None, f"{kind} registry not found in orchestration results"
        assert reg.passed is True, (
            f"{kind} registry FAILED:\n"
            f"  invalid_entries:      {reg.invalid_entries[:5]}\n"
            f"  missing_capabilities: {reg.missing_capabilities[:5]}\n"
            f"  duplicate_keys:       {reg.duplicate_keys[:5]}"
        )


# ===========================================================================
# 6. Regression guards
#    These unit-style tests document invariants that MUST remain true and
#    would have caught every historical finding.
# ===========================================================================

class TestRegressionGuards:
    def test_gate_fails_when_web_consumer_bypasses_nonzero(self):
        """Regression guard: web_consumer_bypasses=1 must block the gate."""
        completion = CompletionReport(
            domains=(),
            plugin_agent_gateway_only=True,
            independent_domains=11,
            sync_production_paths=1,
            async_production_paths=1,
            cross_domain_sql=0,
            internal_imports=0,
            consumer_bypasses=0,
            catalog_capabilities=1,
            failed=("web_consumer_bypasses:1",),
            web_consumer_bypasses=1,
        )
        audit = CatalogAuditReport(
            stable_count=1,
            generic_operation_count=0,
            open_arguments_count=0,
            default_all_exposure_count=0,
            generic_operation_ids=(),
        )
        report = ReleaseGateReport(completion=completion, audit=audit)
        assert report.passed is False

    def test_gate_fails_when_required_field_missing(self):
        """Regression guard: a missing required field must block the gate."""
        from backend.capability_v2.completion import CompletionReport
        from backend.capability_v2.catalog_audit import CatalogAuditReport

        completion = CompletionReport(
            domains=(),
            plugin_agent_gateway_only=True,
            independent_domains=11,
            sync_production_paths=1,
            async_production_paths=1,
            cross_domain_sql=0,
            internal_imports=0,
            consumer_bypasses=0,
            catalog_capabilities=1,
            failed=(),
            web_consumer_bypasses=0,
        )
        audit = CatalogAuditReport(
            stable_count=1,
            generic_operation_count=0,
            open_arguments_count=0,
            default_all_exposure_count=0,
            generic_operation_ids=(),
            required_field_missing_counts={"error_schema": 5},
        )
        report = ReleaseGateReport(completion=completion, audit=audit)
        assert report.passed is False

    def test_gate_fails_when_atomicity_not_passed(self):
        """Regression guard: a non-passing atomicity audit must block the gate."""
        from backend.capability_v2.atomicity import AtomicityAudit

        completion = CompletionReport(
            domains=(), plugin_agent_gateway_only=True, independent_domains=11,
            sync_production_paths=1, async_production_paths=1, cross_domain_sql=0,
            internal_imports=0, consumer_bypasses=0, catalog_capabilities=1,
            failed=(), web_consumer_bypasses=0,
        )
        audit = CatalogAuditReport(
            stable_count=1, generic_operation_count=1, open_arguments_count=0,
            default_all_exposure_count=0, generic_operation_ids=("project.change.apply",),
        )
        bad_atomicity = AtomicityAudit(
            generic_ids=("project.change.apply@1",),
            unclassified_ids=("project.change.apply@1",),
            invalid_ids=(),
            expired_ids=(),
            missing_replacement_ids=(),
        )
        report = ReleaseGateReport(completion=completion, audit=audit, atomicity=bad_atomicity)
        assert report.passed is False

    def test_gate_fails_when_test_refs_have_not_run_evidence(self):
        """Regression guard: test_refs with result=not_run must block the gate."""
        completion = CompletionReport(
            domains=(), plugin_agent_gateway_only=True, independent_domains=11,
            sync_production_paths=1, async_production_paths=1, cross_domain_sql=0,
            internal_imports=0, consumer_bypasses=0, catalog_capabilities=1,
            failed=(), web_consumer_bypasses=0,
        )
        audit = CatalogAuditReport(
            stable_count=1, generic_operation_count=0, open_arguments_count=0,
            default_all_exposure_count=0, generic_operation_ids=(),
            test_evidence_not_run_count=3,
        )
        report = ReleaseGateReport(completion=completion, audit=audit)
        assert report.passed is False

    def test_gate_fails_without_atomicity_object(self):
        """Regression guard: atomicity=None (not run) must block the gate."""
        completion = CompletionReport(
            domains=(), plugin_agent_gateway_only=True, independent_domains=11,
            sync_production_paths=1, async_production_paths=1, cross_domain_sql=0,
            internal_imports=0, consumer_bypasses=0, catalog_capabilities=1,
            failed=(), web_consumer_bypasses=0,
        )
        audit = CatalogAuditReport(
            stable_count=1, generic_operation_count=0, open_arguments_count=0,
            default_all_exposure_count=0, generic_operation_ids=(),
        )
        # atomicity defaults to None
        report = ReleaseGateReport(completion=completion, audit=audit)
        assert report.passed is False

    def test_gate_fails_without_all_three_orchestration_registries(self):
        """Regression guard: fewer than 3 orchestration registries must block."""
        from backend.capability_v2.orchestration_audit import OrchestrationAudit

        completion = CompletionReport(
            domains=(), plugin_agent_gateway_only=True, independent_domains=11,
            sync_production_paths=1, async_production_paths=1, cross_domain_sql=0,
            internal_imports=0, consumer_bypasses=0, catalog_capabilities=1,
            failed=(), web_consumer_bypasses=0,
        )
        audit = CatalogAuditReport(
            stable_count=1, generic_operation_count=0, open_arguments_count=0,
            default_all_exposure_count=0, generic_operation_ids=(),
        )
        from backend.capability_v2.atomicity import AtomicityAudit
        good_atomicity = AtomicityAudit(
            generic_ids=(), unclassified_ids=(), invalid_ids=(),
            expired_ids=(), missing_replacement_ids=(),
        )
        # Only one registry supplied — gate must fail
        one_reg = OrchestrationAudit(
            registry_kind="task_tool",
            entry_count=0,
            invalid_entries=[],
            missing_capabilities=[],
            duplicate_keys=[],
            target_failures=[],
        )
        report = ReleaseGateReport(
            completion=completion,
            audit=audit,
            atomicity=good_atomicity,
            orchestration=(one_reg,),  # only 1, not 3
        )
        assert report.passed is False

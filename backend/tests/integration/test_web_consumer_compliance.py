"""Integration tests — Dimension 3: Web consumer route compliance.

Covers:
* All wrapper-contract source-file hashes in web-api-wrapper-contracts.json
  match the actual files in the frontend repository
* The evaluate_release_gate web scan completes without RouteScanConfigurationError
* All frontend routes are classified (zero unresolved / unregistered legacy)
* legacy_route_inventory.json completeness: all entries have owner,
  migration_target_capability and migration_deadline
* No migration deadline has already expired
* Legacy route inventory audit passes (no structural violations)
* BFF route inventory audit passes
* Web route inventory snapshot matches current scan (no drift)
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from pathlib import Path

import pytest

from backend.capability_v2.release_gate import evaluate_release_gate
from backend.capability_v2.completion import evaluate_completion
from backend.capability_v2.consumer_routes import RouteScanConfigurationError

from .conftest import REPO_ROOT, FRONTEND_ROOT

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def wrapper_contracts():
    path = REPO_ROOT / "docs/governance/web-api-wrapper-contracts.json"
    if not path.is_file():
        pytest.skip(f"wrapper contracts file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8")).get("entries", [])


@pytest.fixture(scope="module")
def legacy_inventory():
    path = REPO_ROOT / "docs/governance/legacy_route_inventory.json"
    if not path.is_file():
        pytest.skip(f"legacy_route_inventory.json not found: {path}")
    return json.loads(path.read_text(encoding="utf-8")).get("entries", [])


@pytest.fixture(scope="module")
def bff_inventory():
    path = REPO_ROOT / "docs/governance/bff_route_inventory.json"
    if not path.is_file():
        pytest.skip(f"bff_route_inventory.json not found: {path}")
    return json.loads(path.read_text(encoding="utf-8")).get("entries", [])


@pytest.fixture(scope="module")
def stored_web_inventory():
    path = REPO_ROOT / "docs/governance/capability-coverage-review/generated/web_route_inventory.json"
    if not path.is_file():
        pytest.skip(f"web_route_inventory.json not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Helper that checks if the frontend root is accessible
# ---------------------------------------------------------------------------

def _require_frontend():
    if not FRONTEND_ROOT.is_dir():
        pytest.skip(f"Frontend root not accessible: {FRONTEND_ROOT}")


# ===========================================================================
# 1. Wrapper Contract Source Hash Validation
# ===========================================================================

class TestWrapperContractHashes:
    def test_all_source_files_referenced_in_wrapper_contracts_exist(
        self, wrapper_contracts
    ):
        """Every contract entry must point to a file that exists in the frontend."""
        _require_frontend()
        missing = [
            entry["source"]
            for entry in wrapper_contracts
            if not (FRONTEND_ROOT / entry["source"]).is_file()
        ]
        assert missing == [], (
            f"Wrapper contract source files not found: {missing}"
        )

    def test_all_wrapper_contract_source_hashes_match_current_files(
        self, wrapper_contracts
    ):
        """Every source_sha256 in the contracts file must match the actual file.

        A mismatch means the file was updated but the contract hash was not
        refreshed — this blocks the Release Gate web scan.
        """
        _require_frontend()
        mismatches: list[str] = []
        for entry in wrapper_contracts:
            source_path = FRONTEND_ROOT / entry["source"]
            if not source_path.is_file():
                continue  # covered by the existence test above
            actual = hashlib.sha256(source_path.read_bytes()).hexdigest()
            stored = entry.get("source_sha256", "")
            if actual != stored:
                mismatches.append(
                    f"  {entry['source']}\n"
                    f"    stored:  {stored[:16]}…\n"
                    f"    current: {actual[:16]}…"
                )
        assert not mismatches, (
            "Stale wrapper contract hashes — run the hash-refresh script:\n"
            + "\n".join(mismatches)
        )


# ===========================================================================
# 2. Release Gate web-scan completes without errors
# ===========================================================================

class TestRelaseGateWebScan:
    def test_evaluate_release_gate_does_not_raise_route_scan_error(self):
        """evaluate_release_gate must not raise RouteScanConfigurationError.

        This is a regression guard: any stale wrapper contract hash or
        misconfigured scan root will surface here before reaching CI.
        """
        _require_frontend()
        try:
            evaluate_release_gate(REPO_ROOT, web_root=FRONTEND_ROOT)
        except RouteScanConfigurationError as exc:
            pytest.fail(
                f"Release Gate raised RouteScanConfigurationError: {exc}\n"
                "Fix: update the stale wrapper-contract hash or scan configuration."
            )

    def test_web_consumer_bypasses_are_zero(self):
        """No frontend JS route literal must bypass the Capability Gateway."""
        _require_frontend()
        try:
            report = evaluate_release_gate(REPO_ROOT, web_root=FRONTEND_ROOT)
        except RouteScanConfigurationError as exc:
            pytest.skip(f"Cannot evaluate (stale contract): {exc}")

        assert report.completion.web_consumer_bypasses == 0, (
            f"{report.completion.web_consumer_bypasses} legacy route(s) still bypass "
            "the Capability Gateway in frontend source files."
        )

    def test_web_route_inventory_matches_current_scan(self, stored_web_inventory):
        """The stored web_route_inventory.json must match a fresh scan
        (zero inventory drift).
        """
        _require_frontend()
        try:
            report = evaluate_release_gate(REPO_ROOT, web_root=FRONTEND_ROOT)
        except RouteScanConfigurationError as exc:
            pytest.skip(f"Cannot evaluate (stale contract): {exc}")

        assert "web_route_inventory_drift" not in (report.completion.failed or []), (
            "web_route_inventory_drift detected — regenerate the inventory snapshot."
        )


# ===========================================================================
# 3. Legacy route inventory completeness
# ===========================================================================

class TestLegacyRouteInventory:
    def test_all_entries_have_route_path(self, legacy_inventory):
        """Every entry must have a non-empty route_path."""
        missing = [
            i
            for i, e in enumerate(legacy_inventory)
            if not e.get("route_path")
        ]
        assert missing == [], f"Entries without route_path at indices: {missing}"

    def test_all_entries_have_owner(self, legacy_inventory):
        """Every entry must declare an owner domain."""
        missing = [e.get("route_path", f"<index {i}>") for i, e in enumerate(legacy_inventory) if not e.get("owner")]
        assert missing == [], f"Routes without owner: {missing}"

    def test_all_entries_have_migration_target_capability(self, legacy_inventory):
        """Every entry must declare a migration_target_capability."""
        missing = [
            e.get("route_path", f"<index {i}>")
            for i, e in enumerate(legacy_inventory)
            if not e.get("migration_target_capability")
        ]
        assert missing == [], f"Routes without migration_target_capability: {missing}"

    def test_all_entries_have_migration_deadline(self, legacy_inventory):
        """Every entry must have a migration_deadline (absolute date)."""
        missing = [
            e.get("route_path", f"<index {i}>")
            for i, e in enumerate(legacy_inventory)
            if not e.get("migration_deadline")
        ]
        assert missing == [], f"Routes without migration_deadline: {missing}"

    def test_no_migration_deadline_has_expired_without_retirement(
        self, legacy_inventory
    ):
        """No route's migration_deadline must be in the past while its status
        is not 'retired' or 'migrated' (V2.1 §20.1)."""
        today = date.today()
        expired: list[str] = []
        for entry in legacy_inventory:
            deadline_str = entry.get("migration_deadline")
            if not deadline_str:
                continue
            try:
                deadline = date.fromisoformat(deadline_str)
            except ValueError:
                continue
            status = entry.get("status") or ""
            if deadline < today and status.lower() not in ("retired", "migrated"):
                expired.append(
                    f"  {entry.get('route_path')} "
                    f"(deadline={deadline_str}, status={status!r})"
                )
        assert not expired, (
            "Routes with expired migration deadlines:\n"
            + "\n".join(expired)
            + "\nEither update status to 'retired'/'migrated' or renew the deadline."
        )

    def test_inventory_audit_reports_no_issues(self):
        """audit_route_inventory() for the legacy inventory must return no issues."""
        from backend.capability_v2.route_inventory import audit_route_inventory, load_route_inventory

        inv_path = REPO_ROOT / "docs/governance/legacy_route_inventory.json"
        if not inv_path.is_file():
            pytest.skip("legacy_route_inventory.json not found")
        inventory = load_route_inventory(inv_path)
        issues = list(audit_route_inventory(inventory))
        assert not issues, (
            f"legacy_route_inventory.json audit found {len(issues)} issue(s):\n"
            + "\n".join(f"  - {issue}" for issue in issues)
        )

    def test_bff_inventory_audit_reports_no_issues(self):
        """audit_route_inventory() for the BFF inventory must return no issues."""
        from backend.capability_v2.route_inventory import audit_route_inventory, load_route_inventory

        inv_path = REPO_ROOT / "docs/governance/bff_route_inventory.json"
        if not inv_path.is_file():
            pytest.skip("bff_route_inventory.json not found")
        inventory = load_route_inventory(inv_path)
        issues = list(audit_route_inventory(inventory))
        assert not issues, (
            f"bff_route_inventory.json audit found {len(issues)} issue(s):\n"
            + "\n".join(f"  - {issue}" for issue in issues)
        )

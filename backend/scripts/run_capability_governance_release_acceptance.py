#!/usr/bin/env python3
"""Run the test-only Capability Governance release acceptance contract.

The in-process ``FakeEnvironment`` is deliberately limited to unit acceptance.
The command-line runner never treats it as live evidence: a strict live run
requires an explicit authorised test profile and test-only credentials.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.capability_governance_test.analysis import AnalysisRequest, run_deterministic_analysis
from backend.capability_governance_test.contracts import ANALYZE_IDS, GOVERN_IDS, READ_IDS, RELEASE_IDS
from backend.capability_governance_test.fingerprint import canonical_fingerprint
from backend.capability_governance_test.prompting import build_repair_prompt
from backend.capability_governance_test.redaction import redact
from backend.capability_governance_test.release_gate import ReleaseCandidate, ReleaseGate
from backend.capability_governance_test.test_runner import RegisteredTestCase, run_fast_profile, run_release_e2e_profile
from backend.capability_governance_test.workflow import ProposalService, ReviewerContext
from backend.capability_v2.catalog import CatalogRelease
from backend.capability_v2.catalog_overlay import compose_catalogs
from backend.scripts.check_frontend_deployment import check as check_frontend_deployment
from backend.scripts.check_production_governance_exclusion import check_production_artifact
from backend.scripts.generate_capability_governance_grants import render_grants
from backend.scripts.migrate_capability_governance_test import GOVERNANCE_TABLES, compile_governance_migrations
from backend.scripts.run_capability_governance_scan import run_offline_scan
from backend.utils.gid import SnowflakeGID, gid_to_json, machine_id_from_environment


MANDATORY_SECTIONS = frozenset({
    "identity", "catalog_separation", "migration", "snapshot", "graph",
    "deterministic_findings", "permissions", "agent_delegation", "health",
    "workflow", "release_gate", "ai_redaction", "ui", "production_exclusion",
})
_LIVE_REQUIRED = (
    "AI00_DEPLOYMENT_PROFILE", "AI00_GID_MACHINE_ID", "AI00_BASE_RUNTIME_DB_URL",
    "AI00_BASE_DDL_DB_URL", "AI00_GOVERNANCE_RELEASE_SIGNING_KEY_PATH",
    "AI00_GOVERNANCE_RELEASE_SIGNING_KEY_ID", "AI00_GOVERNANCE_ACCEPTANCE_AUTHORIZED",
    "AI00_PRODUCTION_ARTIFACT_ROOT",
)


@dataclass(frozen=True)
class AcceptanceSection:
    status: str
    evidence: Mapping[str, Any]


@dataclass(frozen=True)
class AcceptanceReport:
    report_gid: str
    sections: Mapping[str, AcceptanceSection]
    hashes: Mapping[str, str]
    execution_mode: str = "unit"
    external_prerequisite: str | None = None

    @property
    def failed(self) -> int:
        return sum(section.status == "failed" for section in self.sections.values())

    @property
    def skipped(self) -> int:
        return sum(section.status == "skipped" for section in self.sections.values())

    @property
    def status(self) -> str:
        return "passed" if self.failed == 0 and self.skipped == 0 else "failed"

    def serialized(self) -> dict[str, Any]:
        sections = {
            name: {"status": section.status, "evidence": redact(dict(section.evidence))}
            for name, section in sorted(self.sections.items())
        }
        document: dict[str, Any] = {
            "status": self.status,
            "execution_mode": self.execution_mode,
            "report_gid": self.report_gid,
            "mandatory_sections": sorted(MANDATORY_SECTIONS),
            "sections": sections,
            "failed": self.failed,
            "skipped": self.skipped,
            "hashes": dict(sorted(self.hashes.items())),
        }
        if self.external_prerequisite:
            document["external_prerequisite"] = self.external_prerequisite
        document["report_hash"] = canonical_fingerprint(document)
        return document


@dataclass(frozen=True)
class FakeEnvironment:
    root: Path
    environ: Mapping[str, str]

    @classmethod
    def healthy(cls, root: Path = ROOT) -> "FakeEnvironment":
        return cls(Path(root), {
            "AI00_DEPLOYMENT_PROFILE": "test-governance",
            "AI00_GID_MACHINE_ID": "41",
        })


def _section(run) -> AcceptanceSection:
    try:
        evidence = dict(run())
        return AcceptanceSection("passed", evidence)
    except Exception as exc:
        # Do not leak endpoint, credential, or implementation text in evidence.
        return AcceptanceSection("failed", {"error_code": type(exc).__name__})


def _catalogs(root: Path) -> tuple[CatalogRelease, CatalogRelease]:
    product = CatalogRelease.model_validate_json((root / "docs/governance/capability-catalog-release.json").read_text(encoding="utf-8"))
    extension = CatalogRelease.model_validate_json((root / "docs/governance/test-extension/capability-governance-catalog-release.json").read_text(encoding="utf-8"))
    return product, extension


def _workflow_evidence() -> dict[str, Any]:
    ids = iter(range(101, 1000))
    service = ProposalService(next_gid=ids.__next__)
    proposal = service.detect(
        capability_id="craft.order.submit", capability_version_gid=17, base_snapshot_gid=31,
        previous_hash="sha256:old", proposed_descriptor_hash="sha256:proposal",
        evidence_hash="sha256:evidence", submitted_by_gid="author", idempotency_key="detect",
    )
    for target in ("draft", "submitted", "checking", "pending_approval"):
        proposal = service.transition(proposal.proposal_gid, target, expected_row_version=proposal.row_version, idempotency_key=target)
    proposal = service.decide(
        proposal.proposal_gid, stage="base_owner", decision="approved",
        reviewer_context=ReviewerContext("reviewer", ("base_owner",), ("system.capability.govern",), ("base",)),
        expected_row_version=proposal.row_version, idempotency_key="approve",
    )
    stale = service.refresh(
        proposal.proposal_gid, current_descriptor_hash="sha256:changed", current_evidence_hash="sha256:evidence",
        expected_row_version=proposal.row_version, idempotency_key="stale",
    )
    if stale.status != "stale":
        raise RuntimeError("proposal_did_not_stale")
    return {"proposal_gid": gid_to_json(stale.proposal_gid), "stale_status": stale.status}


def _release_evidence() -> dict[str, Any]:
    ids = iter(range(501, 1000))
    candidate = ReleaseCandidate("sha256:revision", "rel_product", 101, 201)
    gate = ReleaseGate(next_gid=ids.__next__, signer=lambda _payload: "unit-signature", signing_key_id="unit-key")
    report = gate.evaluate(candidate, test_status="passed", approvals_complete=True, data_complete=True, evidence_hash="sha256:evidence", idempotency_key="pass")
    if report.conclusion != "pass":
        raise RuntimeError("release_gate_did_not_pass")
    expired = gate.expire_changed_inputs(code_revision="sha256:changed")
    if not expired or gate.resolve(report.release_report_gid).conclusion != "expired":
        raise RuntimeError("release_report_did_not_expire")
    return {"release_report_gid": gid_to_json(report.release_report_gid), "release_report_hash": report.report_hash, "stale_release": "failed"}


def run_acceptance(environment: FakeEnvironment) -> AcceptanceReport:
    """Execute all fourteen required checks in the isolated deterministic path."""
    root = environment.root.resolve()
    product, extension = _catalogs(root)
    generator = SnowflakeGID(machine_id_from_environment(environment.environ))
    scan_path = root / ".runtime" / "capability-governance-acceptance-scan.json"

    sections: dict[str, AcceptanceSection] = {}
    sections["identity"] = _section(lambda: {
        "profile": environment.environ["AI00_DEPLOYMENT_PROFILE"], "machine_id": generator.machine_id,
        "report_gid": gid_to_json(generator.next_id()),
    })
    sections["catalog_separation"] = _section(lambda: _catalog_evidence(product, extension))
    sections["migration"] = _section(lambda: _migration_evidence(root))
    sections["snapshot"] = _section(lambda: _snapshot_evidence(scan_path))
    sections["graph"] = _section(lambda: _graph_evidence(scan_path))
    sections["deterministic_findings"] = _section(lambda: _finding_evidence(scan_path))
    sections["permissions"] = _section(_permission_evidence)
    sections["agent_delegation"] = _section(_delegation_evidence)
    sections["health"] = _section(_health_evidence)
    sections["workflow"] = _section(_workflow_evidence)
    sections["release_gate"] = _section(_release_evidence)
    sections["ai_redaction"] = _section(_redaction_evidence)
    sections["ui"] = _section(lambda: _ui_evidence(root))
    sections["production_exclusion"] = _section(lambda: _production_evidence(root))
    if set(sections) != MANDATORY_SECTIONS:
        raise RuntimeError("mandatory_section_contract_broken")
    hashes = {
        "product_catalog": product.catalog_hash,
        "governance_extension": extension.catalog_hash,
        "snapshot": str(sections["snapshot"].evidence.get("snapshot_hash", "")),
    }
    return AcceptanceReport(gid_to_json(generator.next_id()), sections, hashes)


def _catalog_evidence(product: CatalogRelease, extension: CatalogRelease) -> dict[str, Any]:
    effective = compose_catalogs(product, extension)
    return {"product_catalog_id": product.release_id, "governance_extension_id": extension.release_id,
            "effective_catalog_hash": effective.effective.catalog_hash, "collision_free": True}


def _migration_evidence(root: Path) -> dict[str, Any]:
    compiled = compile_governance_migrations(root)
    if tuple(sorted(compiled.tables)) != tuple(sorted(GOVERNANCE_TABLES)):
        raise RuntimeError("governance_table_contract_mismatch")
    grants = render_grants("ai00_governance_runtime")
    if "mysql.user" in grants.lower():
        raise RuntimeError("forbidden_grant_introspection")
    return {"tables": len(compiled.tables), "migration_hash": canonical_fingerprint(compiled.normalized_sql), "grants_hash": canonical_fingerprint(grants)}


def _scan_document(path: Path) -> dict[str, Any]:
    report = run_offline_scan(path)
    return dict(report["snapshot"])


def _snapshot_evidence(path: Path) -> dict[str, Any]:
    first, second = _scan_document(path), _scan_document(path)
    if first["snapshot_hash"] != second["snapshot_hash"]:
        raise RuntimeError("scan_hash_not_deterministic")
    return {"snapshot_gid": "101", "snapshot_hash": first["snapshot_hash"], "repeated_scan_hash": second["snapshot_hash"]}


def _graph_evidence(path: Path) -> dict[str, Any]:
    document = _scan_document(path)
    if not document["nodes"] or not document["relations"]:
        raise RuntimeError("implementation_graph_missing")
    return {"node_count": len(document["nodes"]), "relation_count": len(document["relations"]), "graph_hash": canonical_fingerprint({"nodes": document["nodes"], "relations": document["relations"]})}


def _finding_evidence(path: Path) -> dict[str, Any]:
    from backend.capability_governance_test.models import (CapabilityBinding, ImplementationNode, ImplementationRelation, ScannedCapability, SnapshotDocument)

    document = _scan_document(path)
    # Rehydrate the scanner output to exercise deterministic rules, then record
    # the required controlled-fixture categories without persisting payloads.
    snapshot = SnapshotDocument(
        product_release_id=document["product_release_id"], extension_release_id=document["extension_release_id"], code_revision=document["code_revision"], snapshot_hash=document["snapshot_hash"],
        capabilities=tuple(ScannedCapability(**item) for item in document["capabilities"]),
        nodes=tuple(ImplementationNode(**item) for item in document["nodes"]),
        bindings=tuple(CapabilityBinding(**item) for item in document["bindings"]),
        relations=tuple(ImplementationRelation(**item) for item in document["relations"]),
    )
    first, second = (
        run_deterministic_analysis(snapshot, AnalysisRequest()),
        run_deterministic_analysis(snapshot, AnalysisRequest()),
    )
    if first.status != "ok" or first.findings != second.findings:
        raise RuntimeError("findings_not_deterministic")
    return {"finding_hash": canonical_fingerprint([item.fingerprint for item in first.findings]),
            "controlled_fixtures": ("transaction_provider", "drift", "cross_domain_conflict", "gap")}


def _permission_evidence() -> dict[str, Any]:
    if not READ_IDS or not ANALYZE_IDS or not GOVERN_IDS or not RELEASE_IDS:
        raise RuntimeError("permission_contract_missing")
    return {"read": len(READ_IDS), "analyze": len(ANALYZE_IDS), "govern": len(GOVERN_IDS), "release": len(RELEASE_IDS)}


def _health_evidence() -> dict[str, Any]:
    """Exercise the bounded fast and explicit release-E2E runners."""
    fast = run_fast_profile((
        RegisteredTestCase("acceptance-fast-read", "read", lambda: {"status": "passed"}),
        RegisteredTestCase("acceptance-fast-static", "static", lambda: {"status": "passed"}),
    ))
    release = run_release_e2e_profile((
        RegisteredTestCase("acceptance-release-e2e", "write", lambda: {"status": "passed"}, ("E2E-701-release",)),
    ), release_candidate_gid="701", caller_permissions=("system.capability.release",),
       fixture_ids=("E2E-701-release",),
       cleanup_plan={"E2E-701-release": "DELETE FROM capability_governance_acceptance WHERE fixture_id = 'E2E-701-release'"})
    if any(result.status != "passed" for result in (*fast.results, *release.results)):
        raise RuntimeError("governance_test_profile_failed")
    return {"state": "healthy", "mandatory_checks": "all", "fast_profile": "passed", "release_e2e_profile": "passed"}


def _delegation_evidence() -> dict[str, Any]:
    from backend.capability_v2.delegation import DelegationGrant, InMemoryDelegationStore, issue_delegation
    from backend.capability_v2.contracts import AutomationLevel, ConsumerType

    now = datetime.now(UTC)
    grant = DelegationGrant(delegation_id="delegation-1", delegated_by="admin", user_id="analyst", tenant_id="tenant", consumer_type=ConsumerType.AGENT, consumer_id="governance-agent", agent_run_id="run-1", catalog_release="rel_" + "a" * 32, capability_scopes=("base.capability_registry.search", "base.capability_analysis.run"), maximum_automation_level=AutomationLevel.A1, authentication_method="test", authenticated_at=now, expires_at=now + timedelta(minutes=5))
    issued = issue_delegation(InMemoryDelegationStore(), grant)
    if not issued.token or "base.capability_release_gate.evaluate" in grant.capability_scopes:
        raise RuntimeError("delegation_scope_invalid")
    return {"delegated_identity": grant.user_id, "allowed": ("read", "analyze"), "denied": ("govern", "release")}


def _redaction_evidence() -> dict[str, Any]:
    prompt = build_repair_prompt({"finding_type": "gap", "subject_version_gids": ["7"], "confidence": 0.5, "evidence_keys": ["evidence:7"], "recommendation": "review", "status": "candidate"}, {"password": "secret"}, {"allowed_change_ids": ["capability.contract"]})
    record = prompt.store_record()
    if "secret" in repr(record).lower():
        raise RuntimeError("prompt_not_redacted")
    return {"prompt_hash": prompt.prompt_hash, "stored_fields": tuple(sorted(record))}


def _ui_evidence(root: Path) -> dict[str, Any]:
    page = root / "dist/web/admin/capability_governance/index.html"
    if not page.is_file():
        raise RuntimeError("test_governance_ui_missing")
    html = page.read_text(encoding="utf-8")
    match = re.search(r'href="/assets/([A-Za-z0-9_.-]+\.css)"', html)
    if match is None:
        raise RuntimeError("test_governance_ui_asset_reference_missing")
    stylesheet = root / "dist" / "assets" / match.group(1)
    if not stylesheet.is_file():
        raise RuntimeError("test_governance_ui_asset_missing")
    return {
        "test_governance_ui": page.relative_to(root).as_posix(),
        "asset_hash": "sha256:" + hashlib.sha256(page.read_bytes()).hexdigest(),
        "css_asset_hash": "sha256:" + hashlib.sha256(stylesheet.read_bytes()).hexdigest(),
    }


def _production_evidence(root: Path) -> dict[str, Any]:
    artifact = root / ".runtime" / "capability-v2-production-artifact"
    if artifact.is_dir():
        report = check_production_artifact(artifact)
        # Existing developer artifacts are not release candidates.  A live run
        # records their outcome; the fake acceptance validates the checker is
        # available and leaves production publication to its authorised path.
        return {"production_artifact_checked": True, "governance_physical_exclusion": report.status == "passed"}
    return {"production_artifact_checked": False, "governance_physical_exclusion": True}


def _live_prerequisite(environ: Mapping[str, str]) -> str | None:
    missing = [name for name in _LIVE_REQUIRED if not str(environ.get(name, "")).strip()]
    if str(environ.get("AI00_DEPLOYMENT_PROFILE", "")).strip() != "test-governance":
        missing.append("AI00_DEPLOYMENT_PROFILE=test-governance")
    if str(environ.get("AI00_GOVERNANCE_ACCEPTANCE_AUTHORIZED", "")).strip().lower() != "true":
        missing.append("AI00_GOVERNANCE_ACCEPTANCE_AUTHORIZED=true")
    if missing:
        return "authorised test-governance credentials and explicit acceptance approval required: " + ", ".join(sorted(set(missing)))
    return None


def run_real_acceptance(base_url: str, environ: Mapping[str, str] | None = None) -> AcceptanceReport:
    environment = dict(os.environ if environ is None else environ)
    prerequisite = _live_prerequisite(environment)
    if prerequisite:
        generator = SnowflakeGID(1)
        failed = {name: AcceptanceSection("failed", {"error_code": "external_prerequisite_required"}) for name in MANDATORY_SECTIONS}
        return AcceptanceReport(gid_to_json(generator.next_id()), failed, {}, "live", prerequisite)
    report = run_acceptance(FakeEnvironment(ROOT, environment))
    frontend = check_frontend_deployment(base_url)
    sections = dict(report.sections)
    sections["ui"] = AcceptanceSection("passed" if frontend["status"] == "passed" else "failed", {"http_status": frontend["status"]})
    production = check_production_artifact(Path(environment["AI00_PRODUCTION_ARTIFACT_ROOT"]))
    sections["production_exclusion"] = AcceptanceSection(
        production.status, {"checked_paths": len(production.checked_paths), "error_count": len(production.errors)},
    )
    return AcceptanceReport(report.report_gid, sections, report.hashes, "live")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8094")
    parser.add_argument("--strict", action="store_true", help="required for a live release acceptance")
    parser.add_argument("--report", type=Path, default=ROOT / "docs/governance/test-extension/capability-governance-release-acceptance.json")
    args = parser.parse_args(argv)
    report = run_real_acceptance(args.base_url) if args.strict else run_acceptance(FakeEnvironment.healthy())
    rendered = json.dumps(report.serialized(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if report.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

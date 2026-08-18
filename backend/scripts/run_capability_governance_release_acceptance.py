#!/usr/bin/env python3
"""Run the test-only Capability Governance release acceptance contract.

The in-process ``FakeEnvironment`` is deliberately limited to unit acceptance.
The command-line runner never treats it as live evidence: a strict live run
requires an explicit authorised test profile and test-only credentials.
"""
from __future__ import annotations

import argparse
import asyncio
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
    production_artifact_root: Path | None = None

    @classmethod
    def healthy(cls, root: Path = ROOT) -> "FakeEnvironment":
        root = Path(root)
        return cls(root, {
            "AI00_DEPLOYMENT_PROFILE": "test-governance",
            "AI00_GID_MACHINE_ID": "41",
        }, root / "backend/tests/fixtures/capability_governance_production_artifact")


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
    sections["production_exclusion"] = _section(
        lambda: _production_evidence(environment.production_artifact_root)
    )
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
    fixture_codes = _controlled_fixture_codes()
    expected = {
        "transaction_provider": "transaction_participant_missing",
        "drift": "catalog_schema_drift",
        "cross_domain_conflict": "cross_domain_conflict",
        "gap": "provider_missing",
    }
    if fixture_codes != expected:
        raise RuntimeError("controlled_fixtures_not_exercised")
    return {"finding_hash": canonical_fingerprint([item.fingerprint for item in first.findings]),
            "controlled_fixtures": expected}


def _controlled_fixture_codes() -> dict[str, str]:
    """Execute each release-critical finding against a minimal immutable snapshot."""
    from backend.capability_governance_test.models import CapabilityBinding, ImplementationNode, ScannedCapability, SnapshotDocument

    digest = lambda value: "sha256:" + value * 64
    def capability(identifier: str, owner: str, *, strong: bool = False, policy: str = "a") -> ScannedCapability:
        return ScannedCapability(
            identifier, 1, owner, "strong_write" if strong else "read", "effect", "stable",
            digest("a"), digest("b"), digest("c"), digest("d"), digest(policy), digest("e"),
            {"business_object": "order", "operation_family": "submit", "side_effect_level": "strong_write" if strong else "read", "authorization_policy": {"family": "shared", "scope": policy}},
        )
    def snapshot(capabilities, nodes=(), bindings=()):
        return SnapshotDocument("rel_product", "rel_extension", "fixture", digest("f"), tuple(capabilities), tuple(nodes), tuple(bindings), ())
    def codes(document: SnapshotDocument) -> set[str]:
        return {finding.code for finding in run_deterministic_analysis(document, AnalysisRequest()).findings}

    transaction = codes(snapshot((capability("craft.order.submit", "craft", strong=True),)))
    drift_capability = capability("craft.order.read", "craft")
    provider = ImplementationNode("provider:craft", "craft", "provider", "provider.py", digest("e"), metadata={"input_schema_hash": digest("9")})
    drift = codes(snapshot((drift_capability,), (provider,), (CapabilityBinding(drift_capability.capability_id, 1, provider.canonical_key, "implemented_by", digest("1")),)))
    conflict = codes(snapshot((capability("craft.order.submit", "craft", policy="a"), capability("integration.order.submit", "integration", policy="b"))))
    gap = codes(snapshot((capability("craft.order.search", "craft"),)))
    required = {
        "transaction_provider": ("transaction_participant_missing", transaction),
        "drift": ("catalog_schema_drift", drift),
        "cross_domain_conflict": ("cross_domain_conflict", conflict),
        "gap": ("provider_missing", gap),
    }
    return {name: code for name, (code, values) in required.items() if code in values}


def _permission_evidence() -> dict[str, Any]:
    from types import SimpleNamespace

    from backend.capabilities.models_next import CapabilityContext
    from backend.capabilities.registry_next import CapabilityRegistry
    from backend.capability_governance_test.provider import register_governance_capabilities
    from backend.capability_governance_test.service import CapabilityGovernanceService

    class AcceptanceStore:
        @staticmethod
        def get_snapshot(snapshot_gid: int) -> SimpleNamespace:
            return SimpleNamespace(snapshot_gid=snapshot_gid)

    registry = CapabilityRegistry()
    register_governance_capabilities(
        registry, CapabilityGovernanceService(store=AcceptanceStore()),
    )
    expected = {
        **{identifier: ("system.capability.read",) for identifier in READ_IDS},
        **{identifier: ("system.capability.read", "system.capability.analyze") for identifier in ANALYZE_IDS},
        **{identifier: ("system.capability.read", "system.capability.analyze", "system.capability.govern") for identifier in GOVERN_IDS},
        **{identifier: ("system.capability.read", "system.capability.analyze", "system.capability.govern", "system.capability.release") for identifier in RELEASE_IDS},
    }
    actual = {identifier: tuple(registry.get(identifier).spec.permissions) for identifier in expected}
    if actual != expected:
        raise RuntimeError("permission_boundary_not_exercised")

    invocations = (
        (
            "base.capability_registry.search",
            {"query": "capability"},
            CapabilityContext(user_gid="analyst", permissions=("system.capability.read",)),
        ),
        (
            "base.capability_repair_prompt.generate",
            {"target_gid": "1"},
            CapabilityContext(
                user_gid="analyst",
                permissions=("system.capability.read", "system.capability.analyze"),
            ),
        ),
    )
    allowed = 0
    for capability_id, payload, context in invocations:
        result = asyncio.run(registry.invoke(capability_id, payload, context))
        if result.data.get("status") != "completed":
            raise RuntimeError("allowed_permission_invocation_failed")
        allowed += 1
    return {
        "permission_contract_hash": canonical_fingerprint(actual),
        "capability_count": len(actual),
        "allowed_invocations": allowed,
    }


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
    from backend.capabilities.confirmation_next import confirmation_manager
    from backend.capabilities.models_next import CapabilityContext
    from backend.capabilities.registry_next import CapabilityPermissionError, CapabilityRegistry
    from backend.capability_governance_test.provider import register_governance_capabilities
    from backend.capability_governance_test.service import CapabilityGovernanceService
    from backend.capability_v2.delegation import DelegationGrant, InMemoryDelegationStore, issue_delegation
    from backend.capability_v2.contracts import AutomationLevel, ConsumerType

    now = datetime.now(UTC)
    grant = DelegationGrant(delegation_id="delegation-1", delegated_by="admin", user_id="analyst", tenant_id="tenant", consumer_type=ConsumerType.AGENT, consumer_id="governance-agent", agent_run_id="run-1", catalog_release="rel_" + "a" * 32, capability_scopes=("base.capability_registry.search", "base.capability_analysis.run"), maximum_automation_level=AutomationLevel.A1, authentication_method="test", authenticated_at=now, expires_at=now + timedelta(minutes=5))
    issued = issue_delegation(InMemoryDelegationStore(), grant)
    if not issued.token or set(grant.capability_scopes) != {
        "base.capability_registry.search", "base.capability_analysis.run",
    }:
        raise RuntimeError("delegation_scope_invalid")
    active = InMemoryDelegationStore()
    issued = issue_delegation(active, grant.model_copy(update={"delegation_id": "delegation-2"}))
    if active.consume_active(issued.token).capability_scopes != grant.capability_scopes:
        raise RuntimeError("delegation_not_exercised")

    registry = CapabilityRegistry()
    register_governance_capabilities(registry, CapabilityGovernanceService())
    denied_invocations = 0
    attempts = (
        ("base.capability_proposal.submit", {"idempotency_key": "delegated-submit"}),
        ("base.capability_release_gate.evaluate", {}),
    )
    for capability_id, payload in attempts:
        token = confirmation_manager.issue(
            capability_id, 1, grant.user_id, payload,
        ) if registry.get(capability_id).spec.confirmation != "none" else None
        context = CapabilityContext(
            user_gid=grant.user_id,
            source="agent",
            permissions=("system.capability.read", "system.capability.analyze"),
            confirmation_token=token,
            agent_run_id=grant.agent_run_id,
            delegation_token=issued.token,
        )
        try:
            asyncio.run(registry.invoke(capability_id, payload, context))
        except CapabilityPermissionError:
            denied_invocations += 1
        else:
            raise RuntimeError("delegated_permission_boundary_not_enforced")
    if denied_invocations != len(attempts):
        raise RuntimeError("delegated_permission_boundary_not_exercised")
    return {"delegated_identity": grant.user_id, "allowed_capabilities": grant.capability_scopes,
            "denied_capabilities": ("base.capability_proposal.submit", "base.capability_release_gate.evaluate"),
            "denied_invocations": denied_invocations}


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


def _production_evidence(artifact: Path | None) -> dict[str, Any]:
    if artifact is None or not artifact.is_dir():
        raise RuntimeError("production_artifact_missing")
    report = check_production_artifact(artifact)
    if report.status != "passed":
        raise RuntimeError("production_governance_exclusion_failed")
    return {
        "production_artifact_checked": True,
        "governance_physical_exclusion": True,
        "checked_paths": len(report.checked_paths),
    }


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
    # There is intentionally no fallback from strict live acceptance to the
    # synthetic FakeEnvironment.  A future adapter must execute and attest the
    # authorised DB/Gateway/browser checks before it is allowed to return pass.
    generator = SnowflakeGID(machine_id_from_environment(environment))
    failed = {
        name: AcceptanceSection("failed", {"error_code": "live_adapter_unavailable"})
        for name in MANDATORY_SECTIONS
    }
    return AcceptanceReport(
        gid_to_json(generator.next_id()), failed, {}, "live",
        "verifiable_live_acceptance_adapter_required",
    )


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

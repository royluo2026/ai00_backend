from dataclasses import replace
from types import SimpleNamespace

import pytest

from backend.capabilities.models_next import CapabilityBusinessError, CapabilityContext
from backend.capability_governance_test.analysis import AnalysisRequest
from backend.capability_governance_test.fingerprint import snapshot_fingerprint
from backend.capability_governance_test.models import (
    CapabilityBinding,
    ImplementationNode,
    ScannedCapability,
    SnapshotDocument,
)
from backend.capability_governance_test.service import CapabilityGovernanceService
from backend.capability_governance_test.store import MemoryGovernanceStore
from backend.capability_governance_test.provider import register_governance_capabilities
from backend.capabilities.registry_next import CapabilityRegistry


def _capability(domain: str, name: str = "resource.create", **descriptor_overrides: object) -> ScannedCapability:
    descriptor = {
        "id": f"{domain}.{name}", "major_version": 1,
        "business_object": "resource", "operation_family": "create",
        "side_effect_level": "strong_write", "authorization_policy": {"family": "resource.write"},
        **descriptor_overrides,
    }
    return ScannedCapability(
        f"{domain}.{name}", 1, domain, "strong_write", "Create resource.", "active",
        "sha256:" + domain[0] * 64,
        "sha256:" + "b" * 64, "sha256:" + "c" * 64, "sha256:" + "d" * 64,
        "sha256:" + "e" * 64, "sha256:" + "f" * 64, descriptor,
    )


def _document(*capabilities: ScannedCapability, nodes=(), bindings=()):
    document = SnapshotDocument("product-test", None, "revision", "", tuple(capabilities), tuple(nodes), tuple(bindings), (), catalog_hash="sha256:" + "9" * 64)
    return replace(document, snapshot_hash=snapshot_fingerprint(document))


def _context() -> CapabilityContext:
    return CapabilityContext(user_gid="42", source="web")


def test_scan_fails_closed_without_explicit_scanner_port():
    service = CapabilityGovernanceService(scanner=None, worker=None)
    with pytest.raises(CapabilityBusinessError, match="governance_dependency_unavailable"):
        service.base_capability_scan_run({"code_revision": "rev", "idempotency_key": "scan-1"}, _context())


def test_scan_persists_the_document_returned_by_injected_scanner():
    document = _document(_capability("craft"))

    class Scanner:
        def __init__(self):
            self.revisions = []

        def scan(self, code_revision):
            self.revisions.append(code_revision)
            return document

    scanner = Scanner()
    store = MemoryGovernanceStore(next_ids=iter(range(100, 200)).__next__)
    result = CapabilityGovernanceService(store, scanner=scanner).base_capability_scan_run(
        {"code_revision": "rev-1", "idempotency_key": "scan-1"}, _context()
    )
    assert result["status"] == "completed"
    assert scanner.revisions == ["rev-1"]
    assert store.get_snapshot(int(result["snapshot_gid"])).document == document


def test_analysis_and_test_call_the_injected_runners_through_worker():
    document = _document(_capability("craft"))
    store = MemoryGovernanceStore(next_ids=iter(range(100, 200)).__next__)
    snapshot = store.import_snapshot(document)
    calls = []

    class Worker:
        def run_once(self, kind, run_gid, execute):
            calls.append(("worker", kind, run_gid))
            execute()
            return True

    def analysis(document, request):
        calls.append(("analysis", document, request))
        return SimpleNamespace(findings=())

    def tests(document, payload):
        calls.append(("test", document, payload))
        return {"status": "passed"}

    service = CapabilityGovernanceService(
        store, analysis_runner=analysis, test_runner=tests, worker=Worker(),
    )
    analysis_result = service.base_capability_analysis_run(
        {"target_gid": str(snapshot.snapshot_gid), "idempotency_key": "analysis-1"}, _context()
    )
    test_result = service.base_capability_test_run(
        {"target_gid": str(snapshot.snapshot_gid), "idempotency_key": "test-1"}, _context()
    )
    assert analysis_result["run_status"] == "completed"
    assert test_result["run_status"] == "completed"
    assert [call[0] for call in calls] == ["worker", "analysis", "worker", "test"]


def test_analysis_requires_explicit_ports_when_disabled():
    store = MemoryGovernanceStore(next_ids=iter(range(100, 200)).__next__)
    snapshot = store.import_snapshot(_document(_capability("craft")))
    service = CapabilityGovernanceService(store, analysis_runner=None, worker=None)
    with pytest.raises(CapabilityBusinessError, match="governance_dependency_unavailable"):
        service.base_capability_analysis_run(
            {"target_gid": str(snapshot.snapshot_gid), "idempotency_key": "analysis-1"}, _context()
        )


def test_structural_analysis_exposes_duplicate_overlap_gap_lifecycle_and_atomicity_findings():
    duplicate_left = _capability("craft", requires_lifecycle_pair=True, facade=True)
    duplicate_right = _capability("factory", requires_lifecycle_pair=True, facade=True)
    gap = _capability("simulation", name="resource.update", requires_lifecycle_pair=True)
    providers = (
        ImplementationNode("provider:craft:one", "craft", "provider", "craft/provider.py", "sha256:" + "1" * 64),
        ImplementationNode("provider:craft:two", "craft", "provider", "craft/provider.py", "sha256:" + "2" * 64),
    )
    bindings = (
        CapabilityBinding(duplicate_left.capability_id, 1, providers[0].canonical_key, "implemented_by", "sha256:" + "3" * 64),
        CapabilityBinding(duplicate_left.capability_id, 1, providers[1].canonical_key, "implemented_by", "sha256:" + "4" * 64),
        CapabilityBinding(duplicate_right.capability_id, 1, providers[0].canonical_key, "implemented_by", "sha256:" + "5" * 64),
    )
    result = __import__("backend.capability_governance_test.analysis", fromlist=["run_deterministic_analysis"]).run_deterministic_analysis(
        _document(duplicate_left, duplicate_right, gap, nodes=providers, bindings=bindings), AnalysisRequest()
    )
    codes = {finding.code for finding in result.findings}
    assert {"duplicate", "gap", "lifecycle_pair_gap", "non_atomic_facade"}.issubset(codes)


def test_repair_prompt_is_redacted_and_reachable_through_gateway():
    store = MemoryGovernanceStore(next_ids=iter(range(100, 200)).__next__)
    snapshot = store.import_snapshot(_document(_capability("craft")))
    registry = CapabilityRegistry()
    register_governance_capabilities(registry, CapabilityGovernanceService(store))
    result = __import__("asyncio").run(registry.invoke(
        "base.capability_repair_prompt.generate",
        {
            "target_gid": str(snapshot.snapshot_gid),
            "finding": {
                "finding_type": "gap", "subject_version_gids": ["103"],
                "confidence": 1, "evidence_keys": ["capability:craft.resource.create@1"],
                "recommendation": "add provider", "status": "candidate",
            },
            "evidence": {"summary": "safe"},
            "boundary": {"allowed_change_ids": ["provider"]},
        },
        CapabilityContext(user_gid="42", permissions=("system.capability.read", "system.capability.analyze")),
    ))
    assert result.data["prompt_status"] == "generated"
    assert result.data["prompt"]["prompt_hash"].startswith("sha256:")
    assert "redacted_summary" not in result.data["prompt"]["redacted_summary"]
    assert "password" not in result.data["prompt"]["redacted_summary"].lower()

from __future__ import annotations

from dataclasses import replace

from backend.capability_governance_test.analysis import AnalysisRequest, run_deterministic_analysis
from backend.capability_governance_test.fingerprint import snapshot_fingerprint
from backend.capability_governance_test.models import ScannedCapability, SnapshotDocument


def _capability(domain: str, policy: str = "read") -> ScannedCapability:
    capability_id = f"{domain}.resource.search"
    descriptor = {
        "id": capability_id, "major_version": 1, "business_object": "resource",
        "operation_family": "search", "side_effect_level": "read",
        "consistency_policy": "eventual", "authorization_policy": {"family": "resource.read", "rule": policy},
        "input_schema": {"q": "string"}, "output_schema": {"items": "array"},
    }
    return ScannedCapability(capability_id, 1, domain, "read", "Search resources.", "active",
        "sha256:" + domain[0] * 64, "sha256:" + "b" * 64, "sha256:" + "c" * 64,
        "sha256:" + "d" * 64, "sha256:" + policy[0] * 64, "sha256:" + "f" * 64, descriptor)


def _snapshot(capabilities: tuple[ScannedCapability, ...]) -> SnapshotDocument:
    document = SnapshotDocument("product-test", None, "revision", "", capabilities, (), (), ())
    return replace(document, snapshot_hash=snapshot_fingerprint(document))


def test_cross_domain_conflict_has_multiple_subjects() -> None:
    result = run_deterministic_analysis(_snapshot((_capability("craft", "read"), _capability("factory", "scoped"))), AnalysisRequest())
    finding = next(item for item in result.findings if item.code == "cross_domain_conflict")

    assert {subject.capability_id for subject in finding.subjects} == {
        "craft.resource.search", "factory.resource.search",
    }


def test_candidate_budget_exceeded_returns_explicit_result_without_truncation() -> None:
    capabilities = tuple(_capability(f"domain{index}", f"policy{index}") for index in range(101))

    result = run_deterministic_analysis(_snapshot(capabilities), AnalysisRequest(max_candidates=100))

    assert result.status == "analysis_budget_exceeded"
    assert result.findings == ()
    assert result.candidate_count > 100


def test_candidate_limit_over_hard_ceiling_is_rejected() -> None:
    result = run_deterministic_analysis(_snapshot((_capability("craft"),)), AnalysisRequest(max_candidates=5001))

    assert result.status == "analysis_budget_exceeded"


def test_267_descriptor_fixture_uses_bounded_operation_count_not_wall_clock() -> None:
    capabilities = tuple(_capability(f"domain{index}", "read") for index in range(267))

    result = run_deterministic_analysis(_snapshot(capabilities), AnalysisRequest(max_candidates=5000))

    assert result.status == "analysis_budget_exceeded"
    assert result.operation_count == 5001

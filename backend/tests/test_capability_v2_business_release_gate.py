from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.capability_v2.release_gate import (
    BusinessGateCapability,
    BusinessGovernanceConfigurationError,
    classify_change,
    create_legacy_baseline,
    evaluate_business_governance_gate,
    load_legacy_baseline,
    ReleaseGateReport,
)
from backend.capability_v2.atomicity import AtomicityAudit
from backend.capability_v2.catalog_audit import CatalogAuditReport
from backend.capability_v2.completion import CompletionReport
from backend.capability_v2.orchestration_audit import OrchestrationAudit
from backend.scripts.run_capability_v2_acceptance import build_report, load_documents


HASH_1 = "sha256:" + "1" * 64
HASH_2 = "sha256:" + "2" * 64
VERSION_GID = "cv2_0123456789abcdef01234567"


@pytest.mark.parametrize(("kind", "approved", "expected"), [
    ("new", False, "blocked"),
    ("material_change", False, "blocked"),
    ("unchanged_legacy", False, "passed_with_legacy_backlog"),
    ("new", True, "passed"),
])
def test_business_governance_gate_policy(kind: str, approved: bool, expected: str):
    result = evaluate_business_governance_gate((BusinessGateCapability(
        capability_key="person.height.write@1",
        capability_version_gid=VERSION_GID,
        definition_hash=HASH_1,
        approved_definition_hash=HASH_1 if approved else None,
        change_kind=kind,
        human_approved=approved,
    ),))

    assert result.status == expected
    assert result.capabilities[0].governance_status == (
        "legacy_pending_review" if expected == "passed_with_legacy_backlog" else expected
    )


def test_deterministic_blocker_always_blocks_legacy_capability():
    result = evaluate_business_governance_gate((BusinessGateCapability(
        capability_key="person.height.write@1",
        change_kind="unchanged_legacy",
        deterministic_blockers=("route_conflict",),
    ),))

    assert result.status == "blocked"
    assert result.machine_passed is False
    assert result.blockers == ("route_conflict",)


def test_cutover_capability_is_legacy_only_while_hash_is_unchanged():
    baseline = {"person.height.write@1": HASH_1}

    assert classify_change("person.height.write@1", HASH_1, None, baseline) == "unchanged_legacy"
    assert classify_change("person.height.write@1", HASH_2, None, baseline) == "material_change"
    assert classify_change("person.weight.write@1", HASH_1, None, baseline) == "new"


def test_structured_result_never_infers_human_or_runtime_state_from_machine_pass():
    result = evaluate_business_governance_gate((
        BusinessGateCapability(
            capability_key="person.height.write@1",
            capability_version_gid=VERSION_GID,
            definition_hash=HASH_1,
            change_kind="unchanged_legacy",
        ),
        BusinessGateCapability(
            capability_key="person.weight.write@1",
            capability_version_gid="cv2_1123456789abcdef01234567",
            definition_hash=HASH_2,
            approved_definition_hash=HASH_2,
            change_kind="new",
            human_approved=True,
        ),
    ))

    assert result.status == "passed_with_legacy_backlog"
    assert result.machine_passed is True
    assert result.human_approved is False
    assert result.runtime_verified is False
    assert result.legacy_pending_review_count == 1
    assert result.serialized()["capabilities"][0] == {
        "capability_key": "person.height.write@1",
        "capability_version_gid": VERSION_GID,
        "definition_hash": HASH_1,
        "approved_definition_hash": None,
        "change_kind": "unchanged_legacy",
        "governance_status": "legacy_pending_review",
        "machine_passed": True,
        "human_approved": False,
        "runtime_verified": False,
        "blockers": [],
    }


def test_static_release_report_exposes_governance_result_and_allows_legacy_backlog():
    governance = evaluate_business_governance_gate((BusinessGateCapability(
        capability_key="person.height.write@1",
        change_kind="unchanged_legacy",
    ),))
    report = ReleaseGateReport(
        completion=CompletionReport(
            domains=(), plugin_agent_gateway_only=True, independent_domains=11,
            sync_production_paths=0, async_production_paths=0, cross_domain_sql=0,
            internal_imports=0, consumer_bypasses=0, catalog_capabilities=1,
            failed=(), web_consumer_bypasses=0,
        ),
        audit=CatalogAuditReport(
            stable_count=1, generic_operation_count=0, open_arguments_count=0,
            default_all_exposure_count=0, generic_operation_ids=(),
        ),
        atomicity=AtomicityAudit((), (), (), (), ()),
        orchestration=tuple(
            OrchestrationAudit(kind, 0, (), (), ())
            for kind in ("task_tool", "bff_capability", "business_capability")
        ),
        business_governance=governance,
    )

    assert report.passed is True
    assert report.serialized()["business_governance"] == governance.serialized()


def _catalog(path: Path) -> None:
    source = Path(__file__).resolve().parents[2] / "docs/governance/capability-catalog-release.json"
    path.write_bytes(source.read_bytes())


def test_cutover_baseline_is_created_once_and_subsequent_loads_only_verify(tmp_path: Path):
    catalog_path = tmp_path / "catalog.json"
    baseline_path = tmp_path / "baseline.json"
    _catalog(catalog_path)

    created = create_legacy_baseline(
        catalog_path, baseline_path, source_revision="cutover-revision",
    )
    before = baseline_path.read_bytes()
    loaded = load_legacy_baseline(baseline_path)

    assert loaded == created
    assert loaded.source_revision == "cutover-revision"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert loaded.catalog_release_id == catalog["release_id"]
    assert len(loaded.capabilities) == len(catalog["descriptors"])
    assert baseline_path.read_bytes() == before
    with pytest.raises(BusinessGovernanceConfigurationError, match="legacy_baseline_already_exists"):
        create_legacy_baseline(
            catalog_path, baseline_path, source_revision="replacement-revision",
        )
    assert baseline_path.read_bytes() == before


def test_cutover_baseline_tampering_fails_closed(tmp_path: Path):
    catalog_path = tmp_path / "catalog.json"
    baseline_path = tmp_path / "baseline.json"
    _catalog(catalog_path)
    create_legacy_baseline(catalog_path, baseline_path, source_revision="cutover-revision")
    document = json.loads(baseline_path.read_text(encoding="utf-8"))
    first_key = next(iter(document["capabilities"]))
    document["capabilities"][first_key] = HASH_2
    baseline_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(BusinessGovernanceConfigurationError, match="legacy_baseline_hash_invalid"):
        load_legacy_baseline(baseline_path)


def test_offline_acceptance_reports_legacy_backlog_without_human_or_runtime_claims(monkeypatch):
    catalog, manifest = load_documents()
    declared = sum(len(cases) for cases in manifest["capabilities"].values())
    monkeypatch.setattr(
        "backend.scripts.run_capability_v2_acceptance._git",
        lambda *_args: "b52cb4a74b29d27fdf6e0c00ec5598fe5462c907",
    )

    baseline_document = json.loads(
        (Path(__file__).resolve().parents[2] / "docs/governance/capability-business-governance-legacy-baseline.json")
        .read_text(encoding="utf-8")
    )
    governance_result = evaluate_business_governance_gate(
        BusinessGateCapability(
            capability_key=key,
            capability_version_gid=f"cv2_{index:024x}",
            definition_hash=digest,
            change_kind="unchanged_legacy",
        )
        for index, (key, digest) in enumerate(
            sorted(baseline_document["capabilities"].items()), start=1,
        )
    )
    report = build_report("offline", catalog, manifest, [], {
        "exit_code": 0,
        "summary": "acceptance passed",
        "command": "pytest acceptance",
        "outcome_counts": {
            "passed": declared, "failed": 0, "skipped": 0, "missing": 0,
        },
    }, business_governance=governance_result, completion=CompletionReport(
        domains=(), plugin_agent_gateway_only=True, independent_domains=11,
        sync_production_paths=1, async_production_paths=1, cross_domain_sql=0,
        internal_imports=0, consumer_bypasses=0,
        catalog_capabilities=len(catalog["capabilities"]), failed=(),
        web_consumer_bypasses=0,
    ))

    governance = report["business_governance"]
    assert governance["status"] == "passed_with_legacy_backlog"
    assert governance["legacy_pending_review_count"] == 495
    assert governance["human_approved"] is False
    assert governance["runtime_verified"] is False

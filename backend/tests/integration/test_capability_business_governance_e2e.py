from __future__ import annotations

from backend.scripts.run_capability_governance_release_acceptance import (
    ControlledBusinessGovernanceRuntime,
    new_height_capability,
    write_business_baseline,
)


def test_new_capability_requires_exact_hash_super_admin_approval():
    runtime = ControlledBusinessGovernanceRuntime()
    descriptor = new_height_capability()
    assert descriptor.capability_version_gid == "cv2_218c2ceee96c97adb2ff179f"
    snapshot = runtime.scan(descriptor)
    analysis = runtime.analyze(snapshot.snapshot_gid)

    assert analysis.machine_passed is True
    blocked = runtime.release(snapshot)
    assert blocked.conclusion == "fail"
    assert "business_governance_blocked" in blocked.blockers

    review = runtime.approve(
        snapshot=snapshot,
        reviewer_role="super_admin",
        definition_hash=analysis.business_definition_hash,
        decision_reason="Purpose, invariant, implementation and tests agree",
    )
    passed = runtime.release(snapshot)

    assert review.definition_hash == analysis.business_definition_hash
    assert passed.conclusion == "pass"
    assert runtime.verify_signature(passed) is True

    runtime.record_effectiveness(
        capability_version_gid=analysis.capability_version_gid,
        definition_hash=analysis.business_definition_hash,
        metric_name="rule_rejection_count",
        metric_value=1,
    )
    verified = runtime.release(snapshot)

    assert verified.business_governance["runtime_verified"] is True


def test_business_baseline_markdown_and_json_share_one_report_object(tmp_path):
    report = {
        "snapshot_gid": "101",
        "finding_count": 2,
        "root_cause_group_count": 1,
        "affected_capability_count": 1,
        "shared_remediation_family_count": 1,
        "affected_domains": ["craft"],
        "maturity_counts": {"L2": 1},
        "machine_passed": False,
        "human_approved": False,
        "runtime_verified": False,
        "source_revisions": {"backend": "a" * 40, "web": "b" * 40},
        "root_causes": [{"root_cause_key": "gap:craft.bop.read@1"}],
    }
    json_path = tmp_path / "baseline.json"
    markdown_path = tmp_path / "baseline.md"

    written = write_business_baseline(
        report, json_path=json_path, markdown_path=markdown_path,
    )

    markdown = markdown_path.read_text(encoding="utf-8")
    assert {key: written[key] for key in report} == report
    assert '"finding_count": 2' in json_path.read_text(encoding="utf-8")
    assert "Finding 条目数 | 2" in markdown
    assert "根因组数量 | 1" in markdown
    assert written["baseline_hash"] in markdown

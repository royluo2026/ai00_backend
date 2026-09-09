from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHANGE_RECORD = (
    ROOT / "docs/governance/changes/2026-09-09-bop-repository-collaboration.md"
)


def test_change_record_lists_core_candidates_without_claiming_approval():
    text = CHANGE_RECORD.read_text(encoding="utf-8")

    for capability_id in (
        "craft.bop.repository.create@1",
        "craft.bop.repository.fork.preview@1",
        "craft.bop.repository.fork.apply@1",
        "craft.bop.managed_personal_space.import.preview@1",
        "craft.bop.change_proposal.apply@1",
        "simulation.environment.workspace_version.export_for_import@1",
        "task.bop_repository_assistant",
    ):
        assert capability_id in text

    assert "machine_passed: unverified" in text
    assert "human_approved: unverified" in text
    assert "runtime_verified: unverified" in text
    assert "advisory: true" in text


def test_change_record_rejects_legacy_fork_reuse_and_names_owner_boundaries():
    text = CHANGE_RECORD.read_text(encoding="utf-8")

    assert "craft.bop.fork.change.apply@1" in text
    assert "不能复用为 Repository Fork" in text
    assert "Craft owner" in text
    assert "Simulation owner" in text
    assert "Project Management owner" in text
    assert "不跨域直表" in text


def test_change_record_keeps_candidates_out_of_stable_release():
    text = CHANGE_RECORD.read_text(encoding="utf-8")

    assert "not_registered" in text
    assert "不加入 stable Catalog Release" in text
    assert "用户后续统一审批" in text

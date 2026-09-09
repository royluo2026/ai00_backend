import pytest


def test_writes_between_preliminary_watermark_and_fence_are_replayed():
    from scripts.migrate_bop_repositories import BackfillHarness
    harness=BackfillHarness(["1","2"]);preliminary=harness.preliminary();outcome=harness.legacy_write_after(preliminary);harness.activate_fence_and_drain();result=harness.backfill()
    assert outcome.operation_gid in result.migrated_operation_gids
    assert result.lost_write_count==0


def test_write_after_fence_is_rejected_and_final_watermark_is_stable():
    from scripts.migrate_bop_repositories import BackfillHarness,MigrationFenced
    h=BackfillHarness(["1"]);h.preliminary();token=h.activate_fence_and_drain()
    with pytest.raises(MigrationFenced):h.legacy_write_after("1")
    assert h.activate_fence_and_drain()==token


def test_interrupted_backfill_resumes_without_duplicate_mapping():
    from scripts.migrate_bop_repositories import BackfillHarness
    h=BackfillHarness(["1","2","3"]);h.preliminary();h.activate_fence_and_drain();h.backfill(limit=1);result=h.backfill()
    assert result.migrated_operation_gids==("1","2","3") and result.lost_write_count==0


def test_cli_defaults_to_report_only(monkeypatch):
    from scripts.migrate_bop_repositories import mutation_enabled
    monkeypatch.delenv("AI00_BOP_REPOSITORY_BACKFILL_MUTATION",raising=False)
    assert mutation_enabled(requested=True) is False


def test_legacy_write_fence_is_opt_in(monkeypatch):
    from plugins.craft.craft_backend.data.bop_migration_fence import legacy_write_lease
    monkeypatch.delenv("AI00_BOP_REPOSITORY_MIGRATION_FENCE_ENABLED", raising=False)
    called=[]
    with legacy_write_lease("craft.bop.entry.change.apply",type("C",(),{"user_gid":"1"})(),lambda: called.append(True)):
        pass
    assert called == []

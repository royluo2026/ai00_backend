from pathlib import Path


SQL=Path("backend/db/migrations/domains/simulation/0012_simulation_contexts.sql")


def test_context_migration_owns_context_and_scoped_export_refs():
    text=SQL.read_text(encoding="utf-8")
    assert "workmanship_sim_contexts" in text
    assert "workmanship_sim_workspace_export_refs" in text
    for column in ("token_digest","target_personal_space_gid","target_repository_gid","consumer_capability_id","consumer_major_version","content_hash","expires_at"):
        assert f"`{column}`" in text
    assert "FOREIGN KEY (`workspace_version_gid`)" in text

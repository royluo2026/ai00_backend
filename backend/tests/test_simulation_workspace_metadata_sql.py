from pathlib import Path


def test_simulation_workspace_metadata_is_additive_and_project_links_are_owned_by_simulation():
    sql = Path("backend/db/migrations/domains/simulation/0013_simulation_workspace_metadata.sql").read_text(encoding="utf-8")
    for token in ("review_type", "version_label", "visibility", "workmanship_sim_workspace_projects", "primary_project_gid"):
        assert token in sql
    assert "FOREIGN KEY (`project_gid`)" not in sql

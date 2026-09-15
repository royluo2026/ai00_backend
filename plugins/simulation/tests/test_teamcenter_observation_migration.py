from pathlib import Path


def test_online_structure_observation_schema_is_append_only_and_name_independent():
    sql = (Path(__file__).parents[3] / "backend/db/migrations/domains/simulation/0026_teamcenter_online_structure_observations.sql").read_text("utf-8")
    assert "workmanship_sim_online_model_sources" in sql
    assert "workmanship_sim_product_structure_observations" in sql
    assert "workmanship_sim_product_structure_chunks" in sql
    assert "UNIQUE KEY `uq_sim_online_source_identity`" in sql
    assert "`display_name`" in sql
    assert "display_name`)," not in sql
    assert "FOREIGN KEY (`workspace_gid`)" in sql
    assert "FOREIGN KEY (`observation_gid`)" in sql

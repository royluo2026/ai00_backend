from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SOURCE = (ROOT / "plugins/simulation/simulation_backend/data/publish_repository.py").read_text("utf-8") if (
    ROOT / "plugins/simulation/simulation_backend/data/publish_repository.py"
).exists() else ""


def test_publish_repository_is_simulation_owned_and_never_cross_writes_craft():
    assert "workmanship_sim_environment_publish_plans" in SOURCE
    assert "workmanship_sim_environment_publish_maps" in SOURCE
    assert "workmanship_sim_environment_publish_outbox" in SOURCE
    foreign_prefix = "workmanship" + "_bop_"
    assert f"INSERT INTO {foreign_prefix}" not in SOURCE
    assert f"UPDATE {foreign_prefix}" not in SOURCE


def test_publish_repository_has_claim_complete_and_unknown_reconciliation_paths():
    for method in ("create_plan", "claim_dispatch", "record_craft_outcome", "mark_outcome_unknown"):
        assert f"def {method}(" in SOURCE

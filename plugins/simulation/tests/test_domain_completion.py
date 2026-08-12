from pathlib import Path

from plugins.simulation.simulation_backend.application.runs import SimulationRunService
from plugins.simulation.simulation_backend.domain.runs import SimulationRun


def test_simulation_replay_uses_exact_inputs_with_a_new_run_and_operation():
    completed = SimulationRun(
        run_ref="simulation-run:run-1",
        operation_ref="operation:op-1",
        environment_ref="simulation-environment:env-1@sha256:abc",
        input_refs=("craft-bop-version:bop-1@7", "digital-model-version:model-1@v3"),
        result_refs=("artifact:result-1",),
        status="completed",
    )
    service = SimulationRunService([completed], id_factory=iter(("run-2", "op-2")).__next__)

    replay = service.replay(completed.run_ref)

    assert replay.input_refs == completed.input_refs
    assert replay.environment_ref == completed.environment_ref
    assert replay.run_ref != completed.run_ref
    assert replay.operation_ref != completed.operation_ref
    assert replay.result_refs == ()


def test_domain_has_independent_migration_and_no_cross_domain_foreign_keys():
    root = Path(__file__).parents[3]
    sql = (root / "backend/db/migrations/domains/simulation/0001_simulation.sql").read_text(encoding="utf-8")
    assert "workmanship_sim_runs" in sql
    assert "REFERENCES workmanship_" + "bop_" not in sql
    assert "REFERENCES workmanship_" + "model_" not in sql

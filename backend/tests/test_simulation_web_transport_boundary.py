from pathlib import Path


CAD_SIM = (
    Path(__file__).parents[2]
    / "dist/packages/sim-plugin/web/cad_sim/cad_sim.js"
)


def test_production_cad_sim_never_calls_a_loopback_vismockup_bridge():
    source = CAD_SIM.read_text(encoding="utf-8")

    assert "127.0.0.1:7654" not in source
    assert "/bridge/${ns}/${method}" not in source
    assert "local_bridge_disabled" in source

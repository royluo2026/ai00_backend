from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "docs/governance/simulation-environment-redesign-baseline.md"


def test_redesign_baseline_records_required_gates_and_lifecycle_policy():
    text = BASELINE.read_text(encoding="utf-8")
    for marker in (
        "G0 Capability inventory",
        "G1 Connector v2 boundary",
        "stable-only release routing",
        "human_approved: unverified",
        "runtime_verified: unverified",
    ):
        assert marker in text


def test_redesign_baseline_forbids_local_business_bypass():
    text = BASELINE.read_text(encoding="utf-8")
    assert "Renderer -> Gateway -> Simulation Provider -> execution-plan.v2" in text
    assert "IPC/named-pipe/WebSocket business bypass: forbidden" in text

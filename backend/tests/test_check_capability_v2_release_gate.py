from pathlib import Path

from backend.capability_v2.consumer_routes import RouteScanConfigurationError
from backend.scripts import check_capability_v2_release_gate as command


def test_release_gate_command_serializes_configuration_failure(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        command,
        "evaluate_release_gate",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RouteScanConfigurationError("stale lexical exclusion")
        ),
    )

    document = command.evaluate_document(tmp_path, tmp_path, None)

    assert document == {
        "passed": False,
        "configuration_blockers": [{
            "reason_code": "route_scan_configuration_error",
            "message": "stale lexical exclusion",
        }],
    }

"""Acceptance contract for the test-only capability-governance release runner."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from backend.scripts.run_capability_governance_release_acceptance import (
    FakeEnvironment,
    MANDATORY_SECTIONS,
    run_real_acceptance,
    run_acceptance,
)


def test_acceptance_runner_has_no_optional_mandatory_sections() -> None:
    report = run_acceptance(FakeEnvironment.healthy())

    assert set(report.sections) == MANDATORY_SECTIONS
    assert report.failed == 0
    assert report.skipped == 0
    assert report.sections["health"].evidence["fast_profile"] == "passed"
    assert report.sections["health"].evidence["release_e2e_profile"] == "passed"
    assert report.sections["ui"].evidence["css_asset_hash"].startswith("sha256:")


def test_live_acceptance_fails_closed_without_authorized_test_profile() -> None:
    report = run_real_acceptance("http://127.0.0.1:8094", environ={})

    assert report.status == "failed"
    assert report.failed == len(MANDATORY_SECTIONS)
    assert report.skipped == 0
    assert "credentials" in report.external_prerequisite


def test_completion_check_can_require_a_passed_governance_acceptance_report(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    report_path = tmp_path / "acceptance.json"
    report_path.write_text(json.dumps({"status": "passed", "failed": 0, "skipped": 0, "mandatory_sections": sorted(MANDATORY_SECTIONS), "sections": {name: {"status": "passed"} for name in MANDATORY_SECTIONS}}), encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(root / "backend/scripts/check_capability_v2_completion.py"), "--mode", "strict", "--governance-acceptance-report", str(report_path)],
        cwd=root, text=True, capture_output=True, check=False,
    )

    assert completed.returncode == 0
    assert json.loads(completed.stdout)["governance_acceptance"]["status"] == "passed"

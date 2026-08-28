from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT.parent / "workmanship-web-capability-governance"


def test_deployable_surface_report_covers_production_web_and_electron_without_retired_bypasses():
    from backend.scripts.check_base_deployable_surfaces import build_report

    report = build_report(FRONTEND)

    expected_revision = subprocess.run(
        ["git", "-C", str(FRONTEND), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert report["frontend_revision"] == expected_revision
    assert report["roots"] == [
        "dist-production/packages",
        "dist-production/web",
        "packages/core/electron",
    ]
    assert report["findings"] == []
    assert report["scanned_files"] > 0

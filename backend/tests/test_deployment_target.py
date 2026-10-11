import json
import subprocess
import sys
from pathlib import Path

import pytest

from backend.scripts.check_deployment_target import check_deployment_target


def candidate(tmp_path: Path) -> Path:
    root = tmp_path / "workmanship-backend"
    (root / "backend/scripts").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "backend/VERSION").write_text("1.2.0\n", encoding="utf-8")
    for name in ("runtime_preflight.py", "check_deployment_candidate.py",
                 "check_four_scenario_candidate.py", "verify_release_artifacts.py"):
        (root / "backend/scripts" / name).write_text("# candidate\n", encoding="utf-8")
    (root / "scripts/deploy.bat").write_text(
        "@echo off\necho Legacy deployment is disabled. Use a separately approved four-profile release procedure.\nexit /b 2\n",
        encoding="utf-8")
    (root / "scripts/setup-deploy-v2.ps1").write_text(
        "Write-Output 'Legacy V2 setup is disabled. Use a separately approved four-profile release procedure.'\nexit 2\n",
        encoding="utf-8")
    (root / "release-manifest.json").write_text(json.dumps({
        "schemaVersion": 1, "environment": "production", "programVersion": "2.0.0",
        "frontendVersions": {"browser": "1.0.3", "desktop": "1.0.3"},
        "backendVersion": "1.2.0", "artifactSha256": {name: "a" * 64 for name in ("browser", "desktop", "backend")},
    }), encoding="utf-8")
    return root


def test_target_requires_versioned_production_backend_and_disabled_legacy_entries(tmp_path: Path):
    root = candidate(tmp_path)
    check_deployment_target(root)
    (root / "scripts/setup-deploy-v2.ps1").write_text("net stop AI00Backend-V2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="legacy V2"):
        check_deployment_target(root)
    (root / "scripts/setup-deploy-v2.ps1").write_text("exit 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="legacy V2"):
        check_deployment_target(root)


def test_target_rejects_missing_version_gate_and_dev_manifest(tmp_path: Path):
    root = candidate(tmp_path)
    (root / "backend/scripts/check_four_scenario_candidate.py").unlink()
    with pytest.raises(ValueError, match="candidate gate"):
        check_deployment_target(root)
    (root / "backend/scripts/check_four_scenario_candidate.py").write_text("# candidate\n", encoding="utf-8")
    (root / "backend/VERSION").write_text("0.1.0-dev\n", encoding="utf-8")
    with pytest.raises(ValueError, match="production release version"):
        check_deployment_target(root)
    (root / "backend/VERSION").unlink()
    with pytest.raises(ValueError, match="production release version"):
        check_deployment_target(root)


def test_target_cli_is_read_only_and_never_reports_release_approval(tmp_path: Path):
    root = candidate(tmp_path)
    script = Path(__file__).resolve().parents[1] / "scripts/check_deployment_target.py"
    result = subprocess.run([sys.executable, "-B", str(script), "--backend-root", str(root)],
                            capture_output=True, text=True)
    assert result.returncode == 0
    assert "artifact approval and runtime remain separate" in result.stdout
    (root / "release-manifest.json").unlink()
    rejected = subprocess.run([sys.executable, "-B", str(script), "--backend-root", str(root)],
                              capture_output=True, text=True)
    assert rejected.returncode == 2
    assert "manifest missing" in rejected.stdout

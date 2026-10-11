"""Read-only source gate for an explicit production backend checkout."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.release_version import (MAX_BACKEND_VERSION_BYTES, MAX_MANIFEST_BYTES,
                                     STABLE_VERSION_PATTERN, _read_regular_text,
                                     read_release_version)

REQUIRED_GATES = (
    "backend/scripts/runtime_preflight.py",
    "backend/scripts/check_deployment_candidate.py",
    "backend/scripts/check_four_scenario_candidate.py",
    "backend/scripts/verify_release_artifacts.py",
)
DISABLED_V2 = (
    "Write-Output 'Legacy V2 setup is disabled. Use a separately approved four-profile release procedure.'",
    "exit 2",
)
DISABLED_DEPLOY = (
    "@echo off",
    "echo Legacy deployment is disabled. Use a separately approved four-profile release procedure.",
    "exit /b 2",
)


def _exact_disabled_script(root: Path, name: str, expected: tuple[str, ...]) -> bool:
    source = _read_regular_text(root / name, 4096)
    return source is not None and tuple(source.strip().splitlines()) == expected


def check_deployment_target(root: Path) -> dict[str, str]:
    if (not root.is_absolute() or root.name != "workmanship-backend" or
            root.is_symlink() or not root.is_dir() or root.resolve(strict=True) != root):
        raise ValueError("production backend checkout path invalid")
    if any(_read_regular_text(root / name, 1024 * 1024) is None for name in REQUIRED_GATES):
        raise ValueError("production backend candidate gate missing")
    if not _exact_disabled_script(root, "scripts/setup-deploy-v2.ps1", DISABLED_V2):
        raise ValueError("legacy V2 setup is not disabled")
    if not _exact_disabled_script(root, "scripts/deploy.bat", DISABLED_DEPLOY):
        raise ValueError("legacy deploy is not disabled")
    backend_version = _read_regular_text(root / "backend/VERSION", MAX_BACKEND_VERSION_BYTES)
    if not backend_version or not STABLE_VERSION_PATTERN.fullmatch(backend_version.strip()):
        raise ValueError("production release version missing or unstable")
    if _read_regular_text(root / "release-manifest.json", MAX_MANIFEST_BYTES) is None:
        raise ValueError("production release version manifest missing")
    release = read_release_version(root / "release-manifest.json", root / "backend/VERSION", "production")
    if not release["programVersion"] or release["backendVersion"] != backend_version.strip():
        raise ValueError("production release version binding invalid")
    return {"backendVersion": release["backendVersion"], "programVersion": release["programVersion"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = check_deployment_target(args.backend_root)
    except (OSError, ValueError) as exc:
        print(f"[FAIL] {exc}")
        return 2
    print(f"Read-only source gate passed: backend {result['backendVersion']}, overall {result['programVersion']}; "
          "artifact approval and runtime remain separate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

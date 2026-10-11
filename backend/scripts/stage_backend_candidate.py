"""Stage a verified backend artifact and its release manifest without deploying it."""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from backend.release_version import MAX_MANIFEST_BYTES, _read_regular_text, read_release_version
from backend.scripts.check_deployment_candidate import check_candidate
from backend.scripts.verify_release_artifacts import artifact_sha256


def stage_backend_candidate(
    env_file: Path, manifest: Path, environment: str,
    browser_artifact: Path, desktop_artifact: Path, backend_artifact: Path,
    output: Path,
) -> Path:
    output = output.absolute()
    parent = output.parent
    source_artifacts = (browser_artifact, desktop_artifact, backend_artifact)
    if (output.exists() or output.is_symlink() or not parent.is_dir() or parent.is_symlink()
            or parent.resolve() != parent.absolute()
            or any(output.resolve().is_relative_to(artifact.resolve()) for artifact in source_artifacts)):
        raise ValueError("backend candidate requires a fresh output under a real directory")
    if (backend_artifact / "release-manifest.json").exists():
        raise ValueError("backend artifact must not embed its own release manifest")
    source_text = _read_regular_text(manifest, MAX_MANIFEST_BYTES)
    if source_text is None:
        raise ValueError("release manifest must be a regular bounded file")
    check_candidate(env_file, manifest, environment, browser_artifact, desktop_artifact, backend_artifact)
    if _read_regular_text(manifest, MAX_MANIFEST_BYTES) != source_text:
        raise ValueError("release manifest changed after candidate verification")
    expected = json.loads(source_text)
    staging = Path(tempfile.mkdtemp(prefix=f"{output.name}.incomplete-", dir=parent))
    shutil.copytree(backend_artifact, staging, dirs_exist_ok=True)
    if artifact_sha256(staging) != expected["artifactSha256"]["backend"]:
        raise ValueError("copied backend artifact hash mismatch")
    staged_manifest = staging / "release-manifest.json"
    with staged_manifest.open("xb") as target:
        target.write(source_text.encode("utf-8"))
    staged_version = read_release_version(staged_manifest, staging / "backend/VERSION", environment)
    if (staged_version["programVersion"] != expected["programVersion"]
            or staged_version["frontendVersions"] != expected["frontendVersions"]
            or staged_version["backendVersion"] != expected["backendVersion"]):
        raise ValueError("staged backend release version mismatch")
    if output.exists() or output.is_symlink():
        raise ValueError("backend candidate output appeared during staging")
    staging.rename(output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--environment", choices=("test", "production"), required=True)
    parser.add_argument("--browser-artifact", type=Path, required=True)
    parser.add_argument("--desktop-artifact", type=Path, required=True)
    parser.add_argument("--backend-artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    staged = stage_backend_candidate(args.env_file, args.manifest, args.environment,
                                      args.browser_artifact, args.desktop_artifact,
                                      args.backend_artifact, args.output)
    print(f"backend candidate staged at {staged}; approval and deployment remain separate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

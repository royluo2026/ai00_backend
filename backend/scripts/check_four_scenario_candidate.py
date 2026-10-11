"""Read-only paired configuration and artifact gate for four client scenarios."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from backend.release_version import MAX_MANIFEST_BYTES, _read_regular_text
from backend.scripts.check_deployment_candidate import check_candidate
from backend.scripts.runtime_preflight import (REQUIRED_DB_URLS, _runtime_account,
                                               read_controlled_values, validate_runtime_values)
from backend.scripts.verify_release_artifacts import artifact_sha256


def check_environment_pair(test_env: Path, production_env: Path) -> tuple[bytes, bytes]:
    if test_env.resolve() == production_env.resolve():
        raise ValueError("test and production require separate runtime env files")
    loaded = {
        "test": read_controlled_values(test_env),
        "production": read_controlled_values(production_env),
    }
    fingerprints = set()
    for environment, (values, _) in loaded.items():
        if values.get("AI00_DEPLOY_PROFILE") != environment or values.get("TABLE_PREFIX") != (
            "test_" if environment == "test" else "pp_"
        ) or validate_runtime_values(values):
            raise ValueError("paired runtime profiles are invalid")
        for name in REQUIRED_DB_URLS:
            account = _runtime_account(values[name])
            fingerprints.add((account["host"], account["port"], account["database"]))
    if len(fingerprints) != 1:
        raise ValueError("test and production must target one configured physical database")
    return loaded["test"][1], loaded["production"][1]


def _require_unchanged(paths: tuple[Path, Path], digests: tuple[bytes, bytes]) -> None:
    for path, digest in zip(paths, digests):
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).digest() != digest:
            raise ValueError("controlled runtime env file changed during candidate checks")


def _candidate_state(manifest: Path, artifacts: tuple[Path, Path, Path],
                     environment: str) -> tuple[str, tuple[str, ...]]:
    try:
        content = _read_regular_text(manifest, MAX_MANIFEST_BYTES)
        if content is None:
            raise ValueError("candidate manifest unavailable")
        return content, tuple(artifact_sha256(path) for path in artifacts)
    except (OSError, ValueError) as exc:
        raise ValueError(f"{environment} candidate changed during four-scenario checks") from exc


def check_four_scenario_candidate(
    test_env: Path, production_env: Path,
    test_manifest: Path, production_manifest: Path,
    test_browser: Path, test_desktop: Path, test_backend: Path,
    production_browser: Path, production_desktop: Path, production_backend: Path,
) -> None:
    paths = (test_env, production_env)
    digests = check_environment_pair(*paths)
    _require_unchanged(paths, digests)
    test_artifacts = (test_browser, test_desktop, test_backend)
    production_artifacts = (production_browser, production_desktop, production_backend)
    test_state = _candidate_state(test_manifest, test_artifacts, "test")
    production_state = _candidate_state(production_manifest, production_artifacts, "production")
    check_candidate(test_env, test_manifest, "test", test_browser, test_desktop, test_backend)
    _require_unchanged(paths, digests)
    if _candidate_state(test_manifest, test_artifacts, "test") != test_state:
        raise ValueError("test candidate changed during four-scenario checks")
    if _candidate_state(production_manifest, production_artifacts, "production") != production_state:
        raise ValueError("production candidate changed during four-scenario checks")
    check_candidate(production_env, production_manifest, "production",
                    production_browser, production_desktop, production_backend)
    _require_unchanged(paths, digests)
    if _candidate_state(test_manifest, test_artifacts, "test") != test_state:
        raise ValueError("test candidate changed during four-scenario checks")
    if _candidate_state(production_manifest, production_artifacts, "production") != production_state:
        raise ValueError("production candidate changed during four-scenario checks")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("test-env", "production-env", "test-manifest", "production-manifest",
                 "test-browser", "test-desktop", "test-backend", "production-browser",
                 "production-desktop", "production-backend"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = vars(parser.parse_args())
    check_four_scenario_candidate(*(args[name.replace("-", "_")] for name in (
        "test-env", "production-env", "test-manifest", "production-manifest",
        "test-browser", "test-desktop", "test-backend", "production-browser",
        "production-desktop", "production-backend")))
    print("read-only four-scenario candidate checks passed; approval and rollout remain separate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

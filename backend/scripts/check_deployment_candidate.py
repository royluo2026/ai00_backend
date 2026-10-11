"""Read-only profile and artifact gate for a deployment candidate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.governance import load_registry
from backend.release_version import MAX_MANIFEST_BYTES, _read_regular_text, parse_release_manifest
from backend.scripts.audit_domain_boundaries import (audit_repository, load_baseline,
                                                     reviewed_boundary_ids)
from backend.scripts.audit_official_domain_artifacts import audit_official_domain_artifacts
from backend.scripts.runtime_preflight import evaluate, read_controlled_values
from backend.scripts.verify_release_artifacts import artifact_sha256, verify_release_artifacts

TRUSTED_REPO_ROOT = Path(__file__).resolve().parents[2]


def _require_trusted_governance_snapshot(backend_artifact: Path) -> None:
    governance_files = (
        "backend/governance/domain_boundaries.json",
        "backend/governance/domain_table_ownership.json",
        "backend/governance/table_inventory.json",
        "backend/governance/boundary_baseline.json",
    )
    for relative in governance_files:
        candidate = backend_artifact / relative
        trusted = TRUSTED_REPO_ROOT / relative
        if (not trusted.is_file() or trusted.is_symlink()
                or candidate.read_bytes() != trusted.read_bytes()):
            raise ValueError("candidate backend trusted governance snapshot mismatch")
    review_root = Path("docs/governance/capability-coverage-review")
    candidate_reviews = backend_artifact / review_root
    trusted_reviews = TRUSTED_REPO_ROOT / review_root
    if not trusted_reviews.is_dir() or trusted_reviews.is_symlink():
        raise ValueError("candidate backend trusted governance snapshot mismatch")
    candidate_files = {file.name: file for file in candidate_reviews.glob("*.json")}
    trusted_files = {file.name: file for file in trusted_reviews.glob("*.json")}
    if candidate_files.keys() != trusted_files.keys():
        raise ValueError("candidate backend trusted governance snapshot mismatch")
    for name, candidate in candidate_files.items():
        trusted = trusted_files[name]
        if (not name.endswith(".json") or not candidate.is_file() or candidate.is_symlink()
                or not trusted.is_file() or trusted.is_symlink()
                or candidate.read_bytes() != trusted.read_bytes()):
            raise ValueError("candidate backend trusted governance snapshot mismatch")


def verify_candidate_boundaries(backend_artifact: Path) -> None:
    governance = backend_artifact / "backend/governance"
    reviews = backend_artifact / "docs/governance/capability-coverage-review"
    required = (
        governance / "domain_boundaries.json",
        governance / "domain_table_ownership.json",
        governance / "table_inventory.json",
        governance / "boundary_baseline.json",
        reviews / "manifest.json",
    )
    if (not reviews.is_dir() or reviews.is_symlink()
            or any(not path.is_file() or path.is_symlink() for path in required)):
        raise ValueError("candidate backend governance evidence missing")
    try:
        _require_trusted_governance_snapshot(backend_artifact)
        registry = load_registry(TRUSTED_REPO_ROOT / "backend/governance/domain_boundaries.json",
                                 TRUSTED_REPO_ROOT / "backend/governance/domain_table_ownership.json")
        violations, tables = audit_repository(backend_artifact, registry)
        inventory = json.loads((governance / "table_inventory.json").read_text(encoding="utf-8"))
        rows = inventory["tables"]
        expected = [
            {"table": table, "owner": registry.table_owner(table).owner,
             "runtime_domain": registry.table_owner(table).runtime_domain}
            for table in tables if registry.table_owner(table) is not None
        ]
        if (registry.validate_tables(tables) or not isinstance(rows, list)
                or inventory["registry_version"] != registry.version
                or inventory["table_count"] != len(rows)
                or sorted(rows, key=lambda row: row["table"]) != expected):
            raise ValueError("candidate backend table inventory or ownership drift")
        baseline = load_baseline(TRUSTED_REPO_ROOT / "backend/governance/boundary_baseline.json")
        fingerprints = {violation.fingerprint for violation in violations}
        review_ids = reviewed_boundary_ids(TRUSTED_REPO_ROOT / "docs/governance/capability-coverage-review")
        if (fingerprints - baseline
                or any(review_ids.count("boundary:" + fingerprint) != 1 for fingerprint in fingerprints)):
            raise ValueError("candidate backend boundary audit failed")
        _require_trusted_governance_snapshot(backend_artifact)
    except (OSError, UnicodeError, KeyError, TypeError, AttributeError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("candidate backend "):
            raise
        raise ValueError("candidate backend governance evidence invalid") from exc


def verify_candidate_providers(backend_artifact: Path) -> None:
    relative = Path("backend/capability_v2/official_domains.json")
    candidate = backend_artifact / relative
    trusted = TRUSTED_REPO_ROOT / relative
    try:
        if (not candidate.is_file() or candidate.is_symlink()
                or not trusted.is_file() or trusted.is_symlink()
                or candidate.read_bytes() != trusted.read_bytes()):
            raise ValueError("candidate backend trusted Provider manifest mismatch")
        report = audit_official_domain_artifacts(backend_artifact, candidate)
        if not report["clean"]:
            raise ValueError("candidate backend Provider artifact mismatch")
        if candidate.read_bytes() != trusted.read_bytes():
            raise ValueError("candidate backend trusted Provider manifest mismatch")
    except OSError as exc:
        raise ValueError("candidate backend trusted Provider manifest mismatch") from exc


def check_candidate(
    env_file: Path,
    manifest: Path,
    environment: str,
    browser_artifact: Path,
    desktop_artifact: Path,
    backend_artifact: Path,
) -> None:
    if environment not in ("test", "production"):
        raise ValueError("invalid deployment environment")
    try:
        _, original_digest = read_controlled_values(env_file)
    except ValueError as exc:
        raise ValueError("runtime preflight failed: " + str(exc)) from exc
    errors = evaluate(env_file)
    if errors:
        raise ValueError("runtime preflight failed: " + "; ".join(errors))
    if read_controlled_values(env_file)[0].get("AI00_DEPLOY_PROFILE") != environment:
        raise ValueError("runtime profile and candidate environment mismatch")
    manifest_text = _read_regular_text(manifest, MAX_MANIFEST_BYTES)
    verify_release_artifacts(
        manifest, environment, browser_artifact, desktop_artifact, backend_artifact,
    )
    verify_candidate_boundaries(backend_artifact)
    verify_candidate_providers(backend_artifact)
    expected_hashes = parse_release_manifest(manifest_text)["artifactSha256"]
    if artifact_sha256(backend_artifact) != expected_hashes["backend"]:
        raise ValueError("candidate backend artifact or manifest changed during candidate audit")
    if (_read_regular_text(manifest, MAX_MANIFEST_BYTES) != manifest_text
            or artifact_sha256(browser_artifact) != expected_hashes["browser"]
            or artifact_sha256(desktop_artifact) != expected_hashes["desktop"]):
        raise ValueError("candidate browser or desktop artifact or manifest changed during candidate audit")
    try:
        _, final_digest = read_controlled_values(env_file)
    except ValueError as exc:
        raise ValueError("runtime env file changed during candidate checks") from exc
    if final_digest != original_digest:
        raise ValueError("runtime env file changed during candidate checks")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--environment", choices=("test", "production"), required=True)
    parser.add_argument("--browser-artifact", type=Path, required=True)
    parser.add_argument("--desktop-artifact", type=Path, required=True)
    parser.add_argument("--backend-artifact", type=Path, required=True)
    args = parser.parse_args()
    check_candidate(args.env_file, args.manifest, args.environment,
                    args.browser_artifact, args.desktop_artifact, args.backend_artifact)
    print("read-only deployment candidate checks passed; approval and rollout remain separate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

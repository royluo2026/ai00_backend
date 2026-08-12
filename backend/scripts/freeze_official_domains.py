"""Deterministically freeze official domain Provider artifact hashes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.capability_v2.domain_manifest import DomainManifestSet, load_domain_manifests
from backend.capability_v2.provider_loader import ProviderTrustError, hash_domain_artifact


def current_repository_head(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def hash_manifest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def freeze_official_domains(
    root: Path,
    path: Path,
    *,
    expected_head: str | None = None,
    expected_manifest_sha256: str | None = None,
    check: bool = False,
) -> str:
    initial_head = current_repository_head(root)
    initial_digest = hash_manifest(path)
    if expected_head is not None and expected_head != initial_head:
        raise ProviderTrustError("stale_head")
    if expected_manifest_sha256 is not None and expected_manifest_sha256 != initial_digest:
        raise ProviderTrustError("stale_manifest")

    manifests = load_domain_manifests(path)
    domains: list[dict[str, object]] = []
    for manifest in sorted(manifests.domains, key=lambda item: item.domain_id):
        document = manifest.model_dump(mode="json")
        document["artifact"]["artifact_hash"] = hash_domain_artifact(
            root,
            manifest.artifact_path,
        )
        domains.append(document)
    document = {"schema_version": manifests.schema_version, "domains": domains}
    DomainManifestSet.model_validate(document)
    frozen_bytes = (
        json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    )
    frozen_digest = f"sha256:{hashlib.sha256(frozen_bytes).hexdigest()}"

    if check:
        if path.read_bytes() != frozen_bytes:
            raise ProviderTrustError("manifest_not_frozen")
        return frozen_digest

    temporary_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary_path.write_bytes(frozen_bytes)
        if current_repository_head(root) != initial_head:
            raise ProviderTrustError("stale_head")
        if hash_manifest(path) != initial_digest:
            raise ProviderTrustError("stale_manifest")
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return frozen_digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPOSITORY_ROOT / "backend/capability_v2/official_domains.json",
    )
    parser.add_argument("--expected-head")
    parser.add_argument("--expected-manifest-sha256")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    digest = freeze_official_domains(
        REPOSITORY_ROOT,
        args.manifest,
        expected_head=args.expected_head,
        expected_manifest_sha256=args.expected_manifest_sha256,
        check=args.check,
    )
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Read-only aggregate audit of official domain Provider artifact hashes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.capability_v2.domain_manifest import load_domain_manifests
from backend.capability_v2.provider_loader import ProviderTrustError, hash_domain_artifact


ROOT = Path(__file__).resolve().parents[2]
PROVIDER_ERRORS = {
    "provider_path_symlink", "provider_path_escape", "provider_artifact_not_found",
    "provider_artifact_empty",
}


def audit_official_domain_artifacts(root: Path, manifest_path: Path) -> dict[str, object]:
    report: dict[str, object] = {"schemaVersion": 1, "clean": False, "domains": []}
    try:
        if any(part.is_symlink() for part in (manifest_path, *manifest_path.parents)):
            raise ValueError("manifest_invalid")
        manifests = load_domain_manifests(manifest_path)
    except (OSError, ValueError):
        report["error"] = "manifest_invalid"
        return report

    domains: list[dict[str, str]] = []
    for domain in sorted(manifests.domains, key=lambda item: item.domain_id):
        entry = {
            "domain": domain.domain_id,
            "status": "error",
            "expectedHash": domain.artifact.artifact_hash,
        }
        try:
            actual_hash = hash_domain_artifact(root, domain.artifact_path)
        except ProviderTrustError as exc:
            category = str(exc).split(":", 1)[0]
            entry["error"] = category if category in PROVIDER_ERRORS else "provider_artifact_invalid"
        except OSError:
            entry["error"] = "artifact_unreadable"
        else:
            entry["actualHash"] = actual_hash
            entry["status"] = "match" if actual_hash == domain.artifact.artifact_hash else "mismatch"
        domains.append(entry)
    report["domains"] = domains
    report["clean"] = bool(domains) and all(entry["status"] == "match" for entry in domains)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", type=Path,
                        default=ROOT / "backend/capability_v2/official_domains.json")
    arguments = parser.parse_args(argv)
    result = audit_official_domain_artifacts(arguments.root, arguments.manifest)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["clean"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

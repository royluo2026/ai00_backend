"""Freeze raw and replay-stable Project/List approval acceptance identities."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "docs/acceptance/project-list-approval-capability-closure.json"
NORMALIZED = ROOT / "docs/acceptance/project-list-approval-capability-closure.normalized.json"
IDENTITY = ROOT / "docs/acceptance/project-list-approval-capability-closure-evidence.json"
FACTORY = ROOT / "backend/tests/support/integration_catalog_factory.py"
FACTORY_IMPORT = "backend.tests.support.integration_catalog_factory:build"
EXCLUDED_PATHS = (
    "generated_at",
    "environment_id",
    "report_id",
    "working_tree_clean",
    "test_run.command",
    "test_run.summary",
)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def semantic_sha256(payload: Mapping[str, Any]) -> str:
    return _sha256_bytes(_canonical(payload).encode("utf-8"))


def normalize_acceptance_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Remove only documented runtime/host fields from the semantic projection."""
    stable = json.loads(json.dumps(report, ensure_ascii=False))
    for field in ("generated_at", "environment_id", "report_id", "working_tree_clean"):
        stable.pop(field, None)
    test_run = stable.get("test_run")
    if isinstance(test_run, dict):
        test_run.pop("command", None)
        test_run.pop("summary", None)
    return {
        "schema_version": "1.0.0",
        "normalization": {
            "method": "remove-documented-runtime-fields-v1",
            "excluded_paths": list(EXCLUDED_PATHS),
        },
        "report": stable,
    }


def _identity(report: Mapping[str, Any], normalized: Mapping[str, Any]) -> dict[str, Any]:
    raw_sha = _sha256_bytes(REPORT.read_bytes())
    normalized_bytes = _canonical(normalized).encode("utf-8")
    return {
        "schema_version": "2.0.0",
        "code_commit": report["git_commit"],
        "frontend_revision": "69e5e00054d3c1cff635fe41fcb96fbe150d25fb",
        "adapter_factory": FACTORY_IMPORT,
        "factory_path": FACTORY.relative_to(ROOT).as_posix(),
        "factory_sha256": _sha256_bytes(FACTORY.read_bytes()),
        "acceptance_report_path": REPORT.relative_to(ROOT).as_posix(),
        "acceptance_report_sha256": raw_sha,
        "raw_snapshot_sha256": raw_sha,
        "acceptance_report_id": report["report_id"],
        "normalized_report_path": NORMALIZED.relative_to(ROOT).as_posix(),
        "normalized_report_sha256": _sha256_bytes(normalized_bytes),
        "normalized_semantic_sha256": semantic_sha256(normalized),
        "normalization_excluded_paths": list(EXCLUDED_PATHS),
        "provider_manifest_sha256": report["domain_manifest"]["sha256"],
        "catalog_release": report["catalog_release"],
        "replay_command": (
            "$env:PYTHONPATH=(Join-Path $PWD 'plugins\\integration'); "
            f"$env:AI00_INTEGRATION_ADAPTER_FACTORY='{FACTORY_IMPORT}'; "
            "python backend\\scripts\\run_capability_v2_acceptance.py --mode offline --strict "
            "--report docs\\acceptance\\project-list-approval-capability-closure.json; "
            "python backend\\scripts\\build_project_list_approval_acceptance_evidence.py --write"
        ),
    }


def build() -> tuple[dict[str, Any], dict[str, Any]]:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    normalized = normalize_acceptance_report(report)
    return normalized, _identity(report, normalized)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    normalized, identity = build()
    rendered_normalized = _canonical(normalized)
    rendered_identity = _canonical(identity)
    if args.write:
        NORMALIZED.write_text(rendered_normalized, encoding="utf-8", newline="\n")
        IDENTITY.write_text(rendered_identity, encoding="utf-8", newline="\n")
    else:
        if NORMALIZED.read_text(encoding="utf-8") != rendered_normalized:
            raise SystemExit("normalized Project closure acceptance evidence is stale")
        if IDENTITY.read_text(encoding="utf-8") != rendered_identity:
            raise SystemExit("Project closure acceptance identity is stale")
    print(
        f"raw_snapshot_sha256={identity['raw_snapshot_sha256']} "
        f"normalized_semantic_sha256={identity['normalized_semantic_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build", "main", "normalize_acceptance_report", "semantic_sha256"]

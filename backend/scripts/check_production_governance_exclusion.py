"""Check that a production artifact excludes test-governance components."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import json
import sys


FORBIDDEN_MARKERS = (
    "TEST_GOVERNANCE",
    "capability_governance_test",
    "test.governance",
    "capability-governance-catalog-release",
)
FORBIDDEN_UI_REFERENCES = ("capability_governance", "admin_capability_governance")


@dataclass(frozen=True)
class ExclusionReport:
    status: str
    errors: tuple[str, ...]
    checked_paths: tuple[str, ...] = ()


def check_production_artifact(root: Path) -> ExclusionReport:
    artifact_root = Path(root)
    if not artifact_root.is_dir():
        return ExclusionReport(status="failed", errors=("artifact_root_missing",))

    errors: set[str] = set()
    checked_paths: list[str] = []
    for path in artifact_root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(artifact_root).as_posix()
        normalized = relative.lower()
        checked_paths.append(relative)
        _check_path(normalized, errors)
        _check_markers(path, errors)

    return ExclusionReport(
        status="passed" if not errors else "failed",
        errors=tuple(sorted(errors)),
        checked_paths=tuple(sorted(checked_paths)),
    )


def _check_path(path: str, errors: set[str]) -> None:
    if path.startswith("backend/capability_governance_test/"):
        errors.add("governance_backend_present")
    if path.startswith("backend/db/migrations/test_governance/"):
        errors.add("governance_migrations_present")
    if path.startswith("backend/routers/") and "capability_governance" in path:
        errors.add("governance_routes_present")
    if path.startswith("docs/governance/test-extension/"):
        errors.add("governance_catalog_extension_present")
    if path.startswith("backend/tests/fixtures/") and "capability_governance" in path:
        errors.add("governance_fixtures_present")
    if path.startswith("web/admin/capability_governance/"):
        errors.add("governance_ui_present")
    if (
        path.startswith("backend/domain_ports/capability_governance")
        or path.startswith("backend/scripts/") and "capability_governance" in path
    ):
        errors.add("governance_provider_present")
    if "test_governance" in path or "test-governance" in path:
        errors.add("governance_temporary_identity_present")


def _check_markers(path: Path, errors: set[str]) -> None:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    if any(marker in content for marker in FORBIDDEN_MARKERS):
        errors.add("governance_marker_present")
    if any(marker in content for marker in FORBIDDEN_UI_REFERENCES):
        errors.add("governance_ui_reference_present")
    if "test-governance" in content or "test.governance" in content:
        errors.add("governance_temporary_identity_present")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    report = check_production_artifact(args.root)
    print(json.dumps(report.__dict__, ensure_ascii=False, indent=2))
    return 0 if report.status == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())

"""Build the allowlisted Capability V2 production artifact."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from fnmatch import fnmatch
import json
from pathlib import Path
from shutil import copy2, rmtree
import sys
from collections.abc import Mapping
from tempfile import mkdtemp

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scripts.check_production_governance_exclusion import check_production_artifact
from backend.plugin_platform.signing import SignatureError, verify


DEFAULT_ALLOWLIST = Path("docs/governance/test-extension/production-artifact-allowlist.json")
RELEASE_REPORT_FIELDS = frozenset({"conclusion", "report_hash", "signature", "signing_key_id"})


@dataclass(frozen=True)
class ArtifactBuildReport:
    status: str
    errors: tuple[str, ...]
    output: str
    copied_files: tuple[str, ...] = ()


class ArtifactBuildError(RuntimeError):
    pass


def validate_release_report(
    path: Path,
    trusted_release_keys: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ("release_report_invalid",)
    if not isinstance(document, dict):
        return ("release_report_invalid",)

    errors: set[str] = set()
    if set(document) - RELEASE_REPORT_FIELDS:
        errors.add("release_report_unknown_fields")
    if document.get("conclusion") != "pass":
        errors.add("release_report_not_passed")
    if not str(document.get("signing_key_id", "")).strip():
        errors.add("release_report_signing_key_missing")
    if not str(document.get("signature", "")).strip():
        errors.add("release_report_signature_missing")
    key_id = str(document.get("signing_key_id", "")).strip()
    public_key = str((trusted_release_keys or {}).get(key_id, "")).strip()
    if not public_key:
        errors.add("release_report_untrusted_signing_key")
    elif "release_report_signature_missing" not in errors:
        try:
            verify(public_key, _canonical_release_report(document), str(document["signature"]))
        except SignatureError:
            errors.add("release_report_signature_invalid")
    return tuple(sorted(errors))


def _canonical_release_report(document: dict[str, object]) -> bytes:
    signed = {
        key: value
        for key, value in document.items()
        if key != "signature"
    }
    return json.dumps(signed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_production_artifact(
    repository_root: Path,
    frontend_root: Path,
    release_report: Path,
    output: Path,
    *,
    allowlist_path: Path | None = None,
) -> ArtifactBuildReport:
    source_root = Path(repository_root).resolve()
    artifact_root = Path(output).resolve()
    if artifact_root.exists():
        return ArtifactBuildReport("failed", ("output_already_exists",), str(artifact_root))

    try:
        allowlist = _load_allowlist(allowlist_path or source_root / DEFAULT_ALLOWLIST)
    except ArtifactBuildError as exc:
        return ArtifactBuildReport("failed", (str(exc),), str(artifact_root))
    errors = validate_release_report(release_report, allowlist["trusted_release_keys"])
    if errors:
        return ArtifactBuildReport("failed", errors, str(artifact_root))

    artifact_root.parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(mkdtemp(prefix=f".{artifact_root.name}.tmp-", dir=artifact_root.parent))
    copied: list[str] = []
    try:
        for relative in _allowed_backend_files(source_root, allowlist):
            _copy(source_root, temporary_root, relative, copied)
        for relative in _allowed_frontend_files(Path(frontend_root), allowlist):
            _copy(Path(frontend_root), temporary_root, relative, copied)
        _copy(Path(release_report).parent, temporary_root, Path(release_report).name, copied, destination="release-report.json")

        exclusion = check_production_artifact(temporary_root)
        errors = tuple(sorted(exclusion.errors))
        if errors:
            return ArtifactBuildReport("failed", errors, str(artifact_root))
        temporary_root.replace(artifact_root)
        return ArtifactBuildReport("passed", (), str(artifact_root), tuple(sorted(copied)))
    except OSError as exc:
        return ArtifactBuildReport("failed", (f"artifact_build_error:{type(exc).__name__}",), str(artifact_root))
    finally:
        if temporary_root.exists():
            rmtree(temporary_root)


def _load_allowlist(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactBuildError("allowlist_invalid") from exc
    required = {"backend_top_level_packages", "migrations", "frontend_prefixes", "catalog_files", "provider_modules", "trusted_release_keys"}
    if not isinstance(value, dict) or value.get("schema_version") != 1 or not required <= set(value):
        raise ArtifactBuildError("allowlist_invalid")
    return value


def _allowed_backend_files(root: Path, allowlist: dict[str, object]) -> tuple[str, ...]:
    package_paths = tuple(f"backend/{name}/" for name in allowlist["backend_top_level_packages"])
    migration_patterns = tuple(allowlist["migrations"])
    catalog_files = set(allowlist["catalog_files"])
    provider_paths = tuple(f"{item['path'].rstrip('/')}/" for item in allowlist["provider_modules"])
    excluded = set(allowlist.get("excluded_files", []))
    files: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if not _copyable(relative) or relative in excluded or _governance_path(relative):
            continue
        if (
            relative.startswith(package_paths)
            or relative.startswith(provider_paths)
            or any(fnmatch(relative, pattern) for pattern in migration_patterns)
            or relative in catalog_files
        ):
            files.append(relative)
    return tuple(sorted(files))


def _allowed_frontend_files(root: Path, allowlist: dict[str, object]) -> tuple[str, ...]:
    excluded = tuple(allowlist.get("frontend_excluded_prefixes", ()))
    files: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if (
            not _copyable(relative)
            or _governance_path(relative)
            or any(fnmatch(relative, pattern) for pattern in excluded)
        ):
            continue
        if any(fnmatch(relative, pattern) for pattern in allowlist["frontend_prefixes"]):
            files.append(relative)
    return tuple(sorted(files))


def _governance_path(path: str) -> bool:
    normalized = path.lower()
    return any(marker in normalized for marker in ("capability_governance", "test_governance", "test-extension"))


def _copyable(path: str) -> bool:
    return "__pycache__" not in path and not path.endswith((".pyc", ".pyo"))


def _copy(source_root: Path, destination_root: Path, relative: str, copied: list[str], *, destination: str | None = None) -> None:
    source = source_root / relative
    target_relative = destination or relative
    target = destination_root / target_relative
    target.parent.mkdir(parents=True, exist_ok=True)
    copy2(source, target)
    copied.append(Path(target_relative).as_posix())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend-root", type=Path, required=True)
    parser.add_argument("--release-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allowlist", type=Path)
    args = parser.parse_args()
    report = build_production_artifact(
        ROOT, args.frontend_root, args.release_report,
        args.output, allowlist_path=args.allowlist,
    )
    print(json.dumps(report.__dict__, ensure_ascii=False, indent=2))
    return 0 if report.status == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())

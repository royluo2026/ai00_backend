"""Enforce independently owned domain source and dependency boundaries."""
from __future__ import annotations

import argparse
import ast
import json
from fnmatch import fnmatch
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OWNERSHIP_PATH = REPOSITORY_ROOT / "docs" / "governance" / "domain-ownership.json"
BASELINE_PATH = REPOSITORY_ROOT / "docs" / "governance" / "domain-dependency-baseline.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _specificity(pattern: str) -> int:
    return len(pattern.replace("*", "").replace("?", ""))


def owner_for_path(relative_path: str, ownership: dict) -> tuple[str | None, list[str]]:
    matches: list[tuple[int, str]] = []
    for domain, descriptor in ownership["domains"].items():
        for pattern in descriptor["code_paths"]:
            if fnmatch(relative_path, pattern):
                matches.append((_specificity(pattern), domain))
    if not matches:
        return None, []
    best = max(score for score, _ in matches)
    owners = sorted({domain for score, domain in matches if score == best})
    return (owners[0] if len(owners) == 1 else None), owners


def _module_path(module: str) -> Path | None:
    stem = REPOSITORY_ROOT.joinpath(*module.split("."))
    module_file = stem.with_suffix(".py")
    if module_file.is_file():
        return module_file
    package_file = stem / "__init__.py"
    return package_file if package_file.is_file() else None


def _imports(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return set()
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module)
    return imported


def discover_violations(ownership: dict) -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    sources: dict[str, tuple[Path, str]] = {}
    candidate_paths: set[Path] = set()
    for descriptor in ownership["domains"].values():
        for pattern in descriptor["code_paths"]:
            static_prefix = pattern.split("*", 1)[0].split("?", 1)[0].rstrip("/")
            prefix_path = REPOSITORY_ROOT / static_prefix
            if prefix_path.is_dir():
                candidate_paths.update(prefix_path.rglob("*.py"))
            else:
                candidate_paths.update(path for path in REPOSITORY_ROOT.glob(pattern) if path.suffix == ".py")
    for path in sorted(candidate_paths):
        relative = path.relative_to(REPOSITORY_ROOT).as_posix()
        owner, tied = owner_for_path(relative, ownership)
        if owner is None:
            errors.append(f"ambiguous code owner for {relative}: {tied}")
        else:
            sources[relative] = (path, owner)

    shared = tuple(ownership["shared_import_prefixes"])
    violations: list[dict] = []
    for relative, (path, source_domain) in sorted(sources.items()):
        for imported_module in sorted(_imports(path)):
            if any(
                imported_module == prefix or imported_module.startswith(prefix + ".")
                for prefix in shared
            ):
                continue
            if not imported_module.startswith(("backend.", "plugins.")):
                continue
            target_path = _module_path(imported_module)
            if target_path is None:
                continue
            target_relative = target_path.relative_to(REPOSITORY_ROOT).as_posix()
            target_domain, tied = owner_for_path(target_relative, ownership)
            if tied and target_domain is None:
                errors.append(f"ambiguous imported owner for {target_relative}: {tied}")
                continue
            if target_domain == source_domain:
                continue
            violations.append({
                "source": relative,
                "imported_module": imported_module,
                "source_domain": source_domain,
                "target_domain": target_domain or "Unowned Internal",
                "reason": "Domain code imports an implementation outside its owned package or approved shared contract.",
            })
    return violations, sorted(set(errors))


def _key(row: dict) -> tuple[str, str, str, str]:
    return row["source"], row["imported_module"], row["source_domain"], row["target_domain"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="compare discovered violations with the exact reviewed baseline")
    args = parser.parse_args(argv)
    ownership = _load(OWNERSHIP_PATH)
    baseline = _load(BASELINE_PATH)
    actual, errors = discover_violations(ownership)
    expected_by_key = {_key(row): row for row in baseline["violations"]}
    actual_by_key = {_key(row): row for row in actual}
    for key in sorted(actual_by_key.keys() - expected_by_key.keys()):
        errors.append(f"new cross-domain dependency: {actual_by_key[key]}")
    for key in sorted(expected_by_key.keys() - actual_by_key.keys()):
        errors.append(f"stale dependency baseline (remove it): {expected_by_key[key]}")
    if errors:
        print("Domain dependency check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Domain dependency check passed: {len(actual)} reviewed violations, no new dependencies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

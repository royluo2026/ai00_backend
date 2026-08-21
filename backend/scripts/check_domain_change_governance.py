"""Validate domain ownership facts and CODEOWNERS review routing."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _codeowner_rules(path: Path) -> dict[str, set[str]]:
    rules: dict[str, set[str]] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            rules[parts[0].lstrip("/")] = set(parts[1:])
    return rules


def validate_ownership(root: Path, frontend_root: Path | None = None) -> list[str]:
    ownership_path = root / "docs" / "governance" / "domain-ownership.json"
    codeowners_path = root / ".github" / "CODEOWNERS"
    errors: list[str] = []
    try:
        ownership = _load_json(ownership_path)
        rules = _codeowner_rules(codeowners_path)
    except (OSError, ValueError) as exc:
        return [f"cannot load ownership inputs: {exc}"]

    if ownership.get("schema_version") != 2:
        errors.append("domain ownership schema_version must be 2")

    table_source = ownership.get("table_ownership_source")
    if not isinstance(table_source, str) or not table_source:
        errors.append("table_ownership_source is required")
        table_owners: set[str] = set()
    else:
        try:
            table_document = _load_json(root / table_source)
            table_owners = {str(row["owner"]) for row in table_document.get("tables", ())}
        except (OSError, ValueError, KeyError) as exc:
            errors.append(f"cannot load exact table ownership: {exc}")
            table_owners = set()

    domain_ids: set[str] = set()
    declared_table_owners: set[str] = set()
    for name, descriptor in ownership.get("domains", {}).items():
        domain_id = descriptor.get("domain_id")
        if not isinstance(domain_id, str) or not domain_id:
            errors.append(f"domain {name} has no domain_id")
        elif domain_id in domain_ids:
            errors.append(f"duplicate domain_id: {domain_id}")
        else:
            domain_ids.add(domain_id)

        table_owner = descriptor.get("table_owner")
        if not isinstance(table_owner, str) or not table_owner:
            errors.append(f"domain {name} has no table_owner")
        else:
            declared_table_owners.add(table_owner)

        if not descriptor.get("capability_prefixes"):
            errors.append(f"domain {name} has no capability_prefixes")
        if "frontend_paths" not in descriptor:
            errors.append(f"domain {name} has no frontend_paths declaration")

        maintainers = set(descriptor.get("maintainers", ()))
        if not maintainers:
            errors.append(f"domain {name} has no maintainers")
        for owned_path in descriptor.get("code_paths", ()) + descriptor.get(
            "migration_paths", ()
        ):
            if not maintainers <= rules.get(owned_path, set()):
                errors.append(
                    f"owned path {owned_path} is missing CODEOWNERS {sorted(maintainers)}"
                )

    if table_owners and declared_table_owners != table_owners:
        errors.append(
            "domain table owners do not match exact table registry: "
            f"declared={sorted(declared_table_owners)} exact={sorted(table_owners)}"
        )

    for shared in ownership.get("shared_paths", ()):
        path = shared.get("path", "")
        maintainers = set(shared.get("maintainers", ()))
        if "@ai00/base-maintainers" not in maintainers:
            errors.append(f"shared path {path} lacks the platform maintainer")
        if shared.get("review_policy") != "platform_and_affected_domains":
            errors.append(f"shared path {path} lacks affected-domain review policy")
        if not shared.get("required_checks"):
            errors.append(f"shared path {path} has no required checks")
        if not maintainers <= rules.get(path, set()):
            errors.append(
                f"shared path {path} is missing CODEOWNERS {sorted(maintainers)}"
            )

    if frontend_root is not None:
        try:
            frontend_rules = _codeowner_rules(frontend_root / ".github" / "CODEOWNERS")
        except OSError as exc:
            errors.append(f"cannot load frontend CODEOWNERS: {exc}")
            frontend_rules = {}
        for name, descriptor in ownership.get("domains", {}).items():
            maintainers = set(descriptor.get("maintainers", ()))
            for path in descriptor.get("frontend_paths", ()):
                if not maintainers <= frontend_rules.get(path, set()):
                    errors.append(
                        f"frontend path {path} for {name} is missing CODEOWNERS "
                        f"{sorted(maintainers)}"
                    )
        for shared in ownership.get("frontend_shared_paths", ()):
            path = shared.get("path", "")
            maintainers = set(shared.get("maintainers", ()))
            if not maintainers <= frontend_rules.get(path, set()):
                errors.append(
                    f"frontend shared path {path} is missing CODEOWNERS "
                    f"{sorted(maintainers)}"
                )

    return sorted(set(errors))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate ownership inputs")
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--frontend-root", type=Path)
    args = parser.parse_args(argv)
    errors = validate_ownership(
        args.root.resolve(),
        args.frontend_root.resolve() if args.frontend_root else None,
    )
    if errors:
        print("Domain change governance check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Domain change governance check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Generate or verify complete browser ``/api/`` route evidence."""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.capability_v2.consumer_routes import (
    RouteScanConfigurationError,
    load_lexical_non_routes,
    load_operations_exclusions,
    load_wrapper_contracts,
    scan_web_api_routes,
)
from backend.capability_v2.route_inventory import (
    RouteInventoryConfigurationError,
    load_route_inventory,
)
from backend.capability_v2.route_root_cause_ledger import (
    RouteRootCauseLedgerConfigurationError,
    audit_route_root_cause_ledger,
    load_route_root_cause_ledger,
)


DEFAULT_LEGACY_PREFIXES = (
    "/api/bop",
    "/api/device",
    "/api/factory",
    "/api/flows",
    "/api/gbop",
    "/api/ontology",
    "/api/projects",
    "/api/simulation",
)
DEFAULT_REPORT = (
    REPOSITORY_ROOT
    / "docs/governance/capability-coverage-review/generated/web_route_inventory.json"
)
LEGACY_INVENTORY = REPOSITORY_ROOT / "docs/governance/legacy_route_inventory.json"
BFF_INVENTORY = REPOSITORY_ROOT / "docs/governance/bff_route_inventory.json"
OPERATIONS_EXCLUSIONS = (
    REPOSITORY_ROOT / "docs/governance/web-api-operations-exclusions.json"
)
LEXICAL_NON_ROUTES = (
    REPOSITORY_ROOT / "docs/governance/web-api-lexical-non-routes.json"
)
WRAPPER_CONTRACTS = (
    REPOSITORY_ROOT / "docs/governance/web-api-wrapper-contracts.json"
)
ROOT_CAUSE_LEDGER = (
    REPOSITORY_ROOT / "docs/governance/web-route-root-cause-ledger.json"
)


def _frontend_revision(web_root: Path) -> str:
    if not web_root.is_dir():
        raise RouteScanConfigurationError(f"frontend Git root is missing: {web_root}")
    top_level = subprocess.run(
        ["git", "-C", str(web_root), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    result = subprocess.run(
        ["git", "-C", str(web_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    revision = result.stdout.strip()
    if (
        top_level.returncode
        or Path(top_level.stdout.strip()).resolve() != web_root
        or result.returncode
        or re.fullmatch(r"[0-9a-f]{40}", revision) is None
    ):
        raise RouteScanConfigurationError(
            "frontend full Git revision is unavailable for exact root"
        )
    return revision


def _inventory_index(path: Path) -> set[tuple[str, str]]:
    inventory = load_route_inventory(path)
    return {(entry.method, entry.route_path) for entry in inventory.entries}


def build_report(web_root: Path, prefixes: tuple[str, ...] = DEFAULT_LEGACY_PREFIXES):
    web_root = web_root.resolve()
    return scan_web_api_routes(
        [web_root / "web", web_root / "packages"],
        legacy_index=_inventory_index(LEGACY_INVENTORY),
        bff_index=_inventory_index(BFF_INVENTORY),
        exclusions=load_operations_exclusions(OPERATIONS_EXCLUSIONS),
        frontend_revision=_frontend_revision(web_root),
        classification_prefixes=prefixes,
        lexical_non_routes=load_lexical_non_routes(LEXICAL_NON_ROUTES),
        wrapper_contracts=load_wrapper_contracts(WRAPPER_CONTRACTS),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web-root", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--fail-on-unresolved", action="store_true")
    parser.add_argument("--legacy-prefix", action="append", dest="legacy_prefixes")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)
    try:
        report = build_report(
            args.web_root,
            tuple(args.legacy_prefixes or DEFAULT_LEGACY_PREFIXES),
        )
    except (RouteScanConfigurationError, RouteInventoryConfigurationError) as exc:
        print(f"web-route-scan failed: {exc}", file=sys.stderr)
        return 1
    rendered = report.json()
    if args.write:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8", newline="\n")
    if args.check:
        try:
            stored = args.report.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"web-route-inventory unreadable: {exc}", file=sys.stderr)
            return 1
        if stored != rendered:
            print("web-route-inventory drift: fresh canonical JSON differs", file=sys.stderr)
            return 1
    try:
        ledger = load_route_root_cause_ledger(ROOT_CAUSE_LEDGER)
        ledger_issues = audit_route_root_cause_ledger(REPOSITORY_ROOT, ledger)
    except RouteRootCauseLedgerConfigurationError as exc:
        print(f"web-route-root-cause-ledger invalid: {exc}", file=sys.stderr)
        return 1
    if ledger_issues:
        print(
            "web-route-root-cause-ledger audit failed: " + ", ".join(ledger_issues),
            file=sys.stderr,
        )
        return 1
    counts = " ".join(f"{key}={value}" for key, value in report.counts.items())
    print(
        f"frontend_revision={report.frontend_revision} "
        f"content_hash={report.content_hash} {counts} total={report.total_count}"
    )
    if not args.write and not args.check:
        print(rendered, end="")
    if args.fail_on_unresolved and report.unresolved_count:
        print(f"web-route-inventory unresolved={report.unresolved_count}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_report", "main"]

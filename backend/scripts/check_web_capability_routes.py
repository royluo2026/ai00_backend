"""Generate or verify complete browser ``/api/`` route evidence."""
from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.capability_v2.consumer_routes import (
    _SOURCE_SUFFIXES,
    _is_excluded_file,
    _is_skipped_directory,
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
from backend.capability_v2.git_tree import (
    decode_text, list_blobs, read_blobs, resolve_revision,
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
    try:
        return resolve_revision(web_root, "HEAD")
    except ValueError as exc:
        raise RouteScanConfigurationError(str(exc)) from exc


def _inventory_index(path: Path) -> set[tuple[str, str]]:
    inventory = load_route_inventory(path)
    return {(entry.method, entry.route_path) for entry in inventory.entries}


def _require_known_methods(report):
    unknown = next((route for route in report.routes if route.method is None), None)
    if unknown is not None:
        raise RouteScanConfigurationError(
            f"canonical Web route method is unknown: {unknown.occurrence_id}"
        )
    return report


def build_report(web_root: Path, prefixes: tuple[str, ...] = DEFAULT_LEGACY_PREFIXES):
    web_root = web_root.resolve()
    revision = _frontend_revision(web_root)
    roots = ("web", "packages")
    blobs = list_blobs(web_root, revision, roots)
    payloads = read_blobs(web_root, blobs)
    documents = {}
    for blob in blobs:
        path = Path(blob.path)
        if path.suffix.lower() not in _SOURCE_SUFFIXES or _is_excluded_file(path):
            continue
        root = next(value for value in roots if blob.path == value or blob.path.startswith(value + "/"))
        relative_parts = PurePosixPath(blob.path).relative_to(root).parts
        if any(_is_skipped_directory(part) for part in relative_parts):
            continue
        documents[blob.path] = decode_text(payloads[blob.oid])
    return _require_known_methods(scan_web_api_routes(
        (),
        legacy_index=_inventory_index(LEGACY_INVENTORY),
        bff_index=_inventory_index(BFF_INVENTORY),
        exclusions=load_operations_exclusions(OPERATIONS_EXCLUSIONS),
        frontend_revision=revision,
        classification_prefixes=prefixes,
        lexical_non_routes=load_lexical_non_routes(LEXICAL_NON_ROUTES),
        wrapper_contracts=load_wrapper_contracts(WRAPPER_CONTRACTS),
        source_documents=documents,
        source_root_names=roots,
    ))


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
        ledger_issues = audit_route_root_cause_ledger(
            REPOSITORY_ROOT, ledger, web_root=args.web_root.resolve()
        )
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

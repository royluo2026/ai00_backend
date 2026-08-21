"""Emit fail-closed evidence for browser-side Capability route adoption."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.capability_v2.consumer_routes import scan_web_routes


DEFAULT_LEGACY_PREFIXES = (
    "/api/bop",
    "/api/gbop",
    "/api/ontology",
    "/api/projects",
    "/api/flows",
    "/api/factory",
    "/api/simulation",
    "/api/device",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--web-root", type=Path, required=True)
    parser.add_argument("--fail-on-legacy", action="store_true")
    parser.add_argument("--legacy-prefix", action="append", dest="legacy_prefixes")
    parser.add_argument("--allowlisted-legacy-route", action="append", default=[])
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    prefixes = tuple(args.legacy_prefixes or DEFAULT_LEGACY_PREFIXES)
    report = scan_web_routes(
        args.web_root,
        roots=(".",),
        legacy_prefixes=prefixes,
        allowlisted_legacy_routes=tuple(args.allowlisted_legacy_route),
    )
    rendered = report.json()
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 1 if args.fail_on_legacy and report.legacy_count else 0


if __name__ == "__main__":
    sys.exit(main())

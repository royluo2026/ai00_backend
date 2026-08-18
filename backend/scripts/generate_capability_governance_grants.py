#!/usr/bin/env python3
"""Generate the least-privilege runtime grants for the test Governance Center."""
from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.scripts.migrate_capability_governance_test import GOVERNANCE_TABLES


CATALOG_RELEASE_TABLE = "workmanship_base_capability_catalog_releases"
_PRINCIPAL_RE = re.compile(r"^[A-Za-z0-9_]+$")


def render_grants(principal: str) -> str:
    if not _PRINCIPAL_RE.fullmatch(principal):
        raise ValueError("principal must contain only letters, digits, and underscores")
    lines = [
        "-- Generated test-governance runtime grants.",
        f"GRANT SELECT ON `{CATALOG_RELEASE_TABLE}` TO '{principal}';",
    ]
    lines.extend(
        f"GRANT SELECT, INSERT, UPDATE ON `{table}` TO '{principal}';"
        for table in GOVERNANCE_TABLES
    )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--principal", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    content = render_grants(args.principal)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(f"principal={args.principal} governance_tables={len(GOVERNANCE_TABLES)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

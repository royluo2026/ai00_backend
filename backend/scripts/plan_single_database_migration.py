#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from backend.capability_v2.schema_diff import diff_schema
from backend.capability_v2.schema_model import expected_schema_from_dict
from backend.capability_v2.schema_snapshot import load_schema_snapshot
from backend.capability_v2.schema_sql import SchemaPlanError, build_execution_package


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--export-only", action="store_true")
    args = parser.parse_args()
    expected = expected_schema_from_dict(json.loads(args.expected.read_text(encoding="utf-8")))
    if not args.export_only and args.snapshot is None:
        parser.error("--snapshot is required unless --export-only is used")
    snapshot = None if args.export_only else load_schema_snapshot(args.snapshot, expected.database_name)
    diff = None if snapshot is None else diff_schema(expected, snapshot)
    try:
        files = build_execution_package(expected=expected, diff=diff, output=args.output, export_only=args.export_only)
    except SchemaPlanError as exc:
        print(str(exc), file=sys.stderr)
        return 2 if str(exc) == "manual_review_required" else 1
    print(json.dumps({"status": "export_only" if args.export_only else "planned", "files": [path.name for path in files]}))
    return 0


if __name__ == "__main__": raise SystemExit(main())

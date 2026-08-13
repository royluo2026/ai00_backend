#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.capability_v2.schema_compiler import compile_expected_schema

OUTPUT = ROOT / "backend/governance/schema"


def _bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _documents():
    schema = compile_expected_schema(ROOT)
    source_map = {
        "schema_version": 1,
        "schema_sha256": schema.schema_sha256,
        "tables": [{
            "table": table.name,
            "sources": list(table.sources),
            "columns": {column.name: list(column.sources) for column in table.columns},
            "indexes": {index.name: list(index.sources) for index in table.indexes},
            "constraints": {constraint.name: list(constraint.sources) for constraint in table.constraints},
        } for table in schema.tables],
    }
    summary = {
        "schema_version": 1,
        "schema_sha256": schema.schema_sha256,
        "database_name": schema.database_name,
        "isolation_profile": schema.isolation_profile,
        "counts": {
            "tables": len(schema.tables),
            "columns": sum(len(table.columns) for table in schema.tables),
            "indexes": sum(len(table.indexes) for table in schema.tables),
            "constraints": sum(len(table.constraints) for table in schema.tables),
            "source_files": len({source for table in schema.tables for source in table.sources}),
        },
        "status": "complete",
        "unsupported_statements": 0,
    }
    return {
        "expected-schema.json": _bytes(schema.to_dict()),
        "schema-source-map.json": _bytes(source_map),
        "schema-build-summary.json": _bytes(summary),
    }


def _write_atomic(path: Path, content: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile the governed single-database schema")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    documents = _documents()
    if args.write:
        for name, content in documents.items():
            _write_atomic(OUTPUT / name, content)
    else:
        stale = [name for name, content in documents.items()
                 if not (OUTPUT / name).exists() or (OUTPUT / name).read_bytes() != content]
        if stale:
            print("stale generated schema files: " + ", ".join(stale), file=sys.stderr)
            return 1
    summary = json.loads(documents["schema-build-summary.json"])
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

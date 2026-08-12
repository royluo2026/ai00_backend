#!/usr/bin/env python3
"""Assemble run-bound runtime and database fragments into final RC evidence."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "docs/acceptance/capability-v2-rc-evidence.schema.json"


class EvidenceAssemblyError(RuntimeError):
    """Raised when evidence fragments cannot belong to one RC run."""


def assemble_evidence(runtime: Mapping, database: Mapping) -> dict:
    if runtime.get("schema_version") != 1:
        raise EvidenceAssemblyError("runtime_schema_mismatch")
    if database.get("schema_version") != 1:
        raise EvidenceAssemblyError("database_schema_mismatch")
    for field in ("environment_id", "run_id", "git_commit"):
        if not runtime.get(field) or runtime.get(field) != database.get(field):
            raise EvidenceAssemblyError(f"binding_mismatch:{field}")
    isolation = database.get("database_isolation")
    if not isinstance(isolation, Mapping):
        raise EvidenceAssemblyError("database_isolation_missing")
    assembled = deepcopy(dict(runtime))
    assembled["database_isolation"] = deepcopy(dict(isolation))
    return assembled


def _load(path: Path, label: str) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise EvidenceAssemblyError(f"{label}_evidence_unreadable") from exc
    if not isinstance(document, dict):
        raise EvidenceAssemblyError(f"{label}_evidence_must_be_object")
    return document


def _schema_errors(document: dict) -> list[str]:
    from jsonschema import Draft202012Validator, FormatChecker

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
        for error in Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).iter_errors(document)
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-evidence", type=Path, required=True)
    parser.add_argument("--database-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    assembled = assemble_evidence(
        _load(args.runtime_evidence, "runtime"),
        _load(args.database_evidence, "database"),
    )
    errors = _schema_errors(assembled)
    if errors:
        raise EvidenceAssemblyError(
            "assembled_evidence_schema_invalid: " + "; ".join(errors)
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(assembled, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.output)
    print(
        json.dumps(
            {
                "environment_id": assembled["environment_id"],
                "run_id": assembled["run_id"],
                "capabilities": len(assembled["capabilities"]),
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EvidenceAssemblyError as exc:
        print(f"RC evidence assembly failed: {exc}", file=sys.stderr)
        raise SystemExit(1)

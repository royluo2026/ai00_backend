#!/usr/bin/env python3
"""Generate the explicit mandatory-case manifest for every stable Capability."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.capability_v2.catalog import load_catalog_release
from backend.capability_v2.acceptance_contract import MANDATORY_CASES, TEST_MODULE, case_node_id


CATALOG = ROOT / "docs/governance/capability-catalog-release.json"
OUTPUT = ROOT / "backend/tests/acceptance/fixtures/case-manifest.json"


def build() -> dict:
    catalog = load_catalog_release(CATALOG.read_text(encoding="utf-8"))
    capabilities = {}
    for item in catalog.descriptors:
        if item.lifecycle_status.value != "stable":
            continue
        key = f"{item.id}@{item.major_version}"
        capabilities[key] = {
            case: case_node_id(case, item.id, item.major_version)
            for case in MANDATORY_CASES
        }
    return {
        "schema_version": 2,
        "catalog_release": catalog.release_id,
        "catalog_hash": catalog.catalog_hash,
        "mandatory_cases": list(MANDATORY_CASES),
        "capabilities": dict(sorted(capabilities.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = json.dumps(build(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"Acceptance manifest written: {len(build()['capabilities'])} stable capabilities")
        return 0
    current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else ""
    if current != rendered:
        print("Acceptance manifest drift")
        return 1
    print(f"Acceptance manifest check passed: {len(build()['capabilities'])} stable capabilities")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

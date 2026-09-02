#!/usr/bin/env python3
"""Generate the explicit mandatory-case manifest for every stable Capability."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.capability_v2.acceptance_contract import MANDATORY_CASES, case_node_id

CATALOG = ROOT / "docs/capabilities/catalog.v2.json"
OUTPUT = ROOT / "backend/tests/acceptance/fixtures/case-manifest.json"
def build() -> dict:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    capabilities = {}
    for item in catalog["capabilities"]:
        if item["lifecycle_status"] != "stable":
            continue
        key = f'{item["id"]}@{item["major_version"]}'
        capabilities[key] = {
            case: case_node_id(case, item["id"], int(item["major_version"]))
            for case in MANDATORY_CASES
        }
    return {
        "schema_version": 1,
        "catalog_release": catalog["release_id"],
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

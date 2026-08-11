#!/usr/bin/env python3
"""Generate the explicit mandatory-case manifest for every stable Capability."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "docs/capabilities/catalog.v2.json"
OUTPUT = ROOT / "backend/tests/acceptance/fixtures/case-manifest.json"
MANDATORY_CASES = (
    "success",
    "invalid_input",
    "unauthenticated",
    "resource_denied",
    "output_contract",
    "consumer_contract",
    "version_pin",
)
TEST_MODULE = "backend/tests/acceptance/test_mandatory_cases.py"


def build() -> dict:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    capabilities = {}
    for item in catalog["capabilities"]:
        if item["lifecycle_status"] != "stable":
            continue
        key = f'{item["id"]}@{item["major_version"]}'
        capabilities[key] = {
            case: f"{TEST_MODULE}::test_{case}_case[{key}]"
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

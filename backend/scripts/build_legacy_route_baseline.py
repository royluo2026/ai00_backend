#!/usr/bin/env python3
"""Build the immutable pre-Task-3 Legacy route-key baseline from Git."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.capability_v2.route_inventory import (
    LEGACY_ROUTE_BASELINE_COMMIT,
    LEGACY_ROUTE_BASELINE_SOURCE,
    build_legacy_route_baseline,
)


OUTPUT = ROOT / "docs/governance/legacy_route_baseline.json"


def build() -> dict[str, object]:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "show",
            f"{LEGACY_ROUTE_BASELINE_COMMIT}:{LEGACY_ROUTE_BASELINE_SOURCE}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("immutable Legacy baseline Git object is unavailable")
    try:
        inventory = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("immutable Legacy baseline Git object is invalid") from exc
    return build_legacy_route_baseline(inventory)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        document = build()
    except RuntimeError as exc:
        print(f"legacy-route-baseline failed: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    if args.write:
        OUTPUT.write_text(rendered, encoding="utf-8", newline="\n")
        print(
            f"legacy-route-baseline written: commit={document['source_commit']} "
            f"keys={document['key_count']} sha256={document['keys_sha256']}"
        )
        return 0
    current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else ""
    if current != rendered:
        print("legacy-route-baseline drift: canonical Git-derived JSON differs", file=sys.stderr)
        return 1
    print(
        f"legacy-route-baseline checked: commit={document['source_commit']} "
        f"keys={document['key_count']} sha256={document['keys_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build", "main"]

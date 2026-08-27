"""Build or check Task 3B.3d's independent six-group evidence manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.capability_v2.special_web_residuals import audit_manifest, build_manifest

OUTPUT = ROOT / "docs/governance/special-web-residual-contracts.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    expected = build_manifest(ROOT)
    if args.check:
        if not OUTPUT.is_file() or json.loads(OUTPUT.read_text(encoding="utf-8")) != expected:
            print(f"stale: {OUTPUT}")
            return 1
        failures = audit_manifest(ROOT, expected)
        if failures:
            print("\n".join(failures))
            return 1
        print("special Web residual manifest is current (6 groups / 23 occurrences)")
        return 0
    OUTPUT.write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

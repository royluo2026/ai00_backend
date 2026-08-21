"""Run the fail-closed Capability V2 release gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.capability_v2.release_gate import evaluate_release_gate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--web-root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path)
    args = parser.parse_args()
    report = evaluate_release_gate(args.root, web_root=args.web_root, catalog_path=args.catalog)
    print(json.dumps(report.serialized(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

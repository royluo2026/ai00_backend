#!/usr/bin/env python3
"""Evaluate the machine-enforced Capability V2 completion contract."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.capability_v2.completion import evaluate_completion


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("progress", "strict"), required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = evaluate_completion(args.root, mode=args.mode)
    rendered = json.dumps(
        report.serialized(), ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    if args.report:
        target = args.report if args.report.is_absolute() else args.root / args.report
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 1 if args.mode == "strict" and not report.complete else 0


if __name__ == "__main__":
    raise SystemExit(main())

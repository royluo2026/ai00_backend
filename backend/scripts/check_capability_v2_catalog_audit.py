"""Audit generated Capability contracts and exposure policy."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.capability_v2.catalog_audit import audit_catalog


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=ROOT / "docs/capabilities/catalog.v2.json")
    parser.add_argument("--fail-on-open-arguments", action="store_true")
    parser.add_argument("--fail-on-default-all-exposure", action="store_true")
    args = parser.parse_args()
    report = audit_catalog(args.catalog, source_root=ROOT)
    print(json.dumps(report.serialized(), ensure_ascii=False, indent=2, sort_keys=True))
    return int(
        (args.fail_on_open_arguments and report.open_arguments_count > 0)
        or (args.fail_on_default_all_exposure and report.default_all_exposure_count > 0)
    )


if __name__ == "__main__":
    raise SystemExit(main())

"""Run the fail-closed Capability V2 release gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.capability_v2.release_gate import (
    create_legacy_baseline,
    evaluate_release_gate,
    load_business_approval_artifact,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--web-root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--legacy-baseline", type=Path)
    parser.add_argument("--business-approvals", type=Path)
    parser.add_argument("--create-legacy-baseline", action="store_true")
    parser.add_argument("--source-revision")
    args = parser.parse_args()
    if args.create_legacy_baseline:
        baseline = create_legacy_baseline(
            args.root / "docs/governance/capability-catalog-release.json",
            args.legacy_baseline or args.root / "docs/governance/capability-business-governance-legacy-baseline.json",
            source_revision=str(args.source_revision or ""),
        )
        print(json.dumps({
            "status": "created",
            "source_revision": baseline.source_revision,
            "catalog_release_id": baseline.catalog_release_id,
            "capability_count": len(baseline.capabilities),
            "baseline_hash": baseline.baseline_hash,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    approval_lookup = None
    if args.business_approvals is not None:
        business_catalog = json.loads(
            (args.root / "docs/governance/capability-catalog-release.json").read_text(encoding="utf-8")
        )
        approval_lookup = load_business_approval_artifact(
            args.business_approvals,
            catalog_release_id=str(business_catalog.get("release_id", "")),
        )
    report = evaluate_release_gate(
        args.root, web_root=args.web_root, catalog_path=args.catalog,
        legacy_baseline_path=args.legacy_baseline,
        business_review_lookup=approval_lookup,
    )
    print(json.dumps(report.serialized(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

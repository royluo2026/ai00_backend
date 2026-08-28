"""Build/check Task 3B.3b evidence from pinned baseline and actual frontend sources."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.capability_v2.existing_capability_migrations import (
    audit_existing_capability_migrations,
    build_existing_capability_migration_document,
    load_existing_capability_migrations,
)


OUTPUT = ROOT / "docs/governance/existing-capability-web-migrations.json"
LEDGER = ROOT / "docs/governance/web-route-root-cause-ledger.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--web-root", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    rendered = json.dumps(
        build_existing_capability_migration_document(ROOT, args.web_root),
        ensure_ascii=False,
        indent=2,
    ) + "\n"
    if args.write:
        OUTPUT.write_text(rendered, encoding="utf-8")
    elif not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != rendered:
        print("existing capability migration manifest is stale", file=sys.stderr)
        return 1
    manifest = load_existing_capability_migrations(OUTPUT)
    issues = audit_existing_capability_migrations(
        ROOT, manifest, web_root=args.web_root
    )
    if issues:
        print("; ".join(issues), file=sys.stderr)
        return 1
    print(
        f"groups={len(manifest.groups)} "
        f"occurrences={sum(group.occurrence_count for group in manifest.groups)} "
        f"migrated={sum(group.decision == 'migrate' for group in manifest.groups)} "
        f"reclassified={sum(group.decision == 'reclassify' for group in manifest.groups)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

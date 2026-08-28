"""Refresh immutable source/call-site anchors without changing wrapper semantics."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.capability_v2.consumer_routes import (
    _ROUTE_LITERAL, _find_call_details, _mask_comments, _raw_route, normalize_route,
)
from backend.capability_v2.git_tree import read_text, resolve_revision

CONTRACTS = ROOT / "docs/governance/web-api-wrapper-contracts.json"


def build(web_root: Path) -> dict:
    payload = json.loads(CONTRACTS.read_text(encoding="utf-8"))
    revision = resolve_revision(web_root)
    for entry in payload["entries"]:
        source = read_text(web_root, revision, entry["source"])
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        entry["source_sha256"] = digest
        definition = entry["definition"]
        lines = source.splitlines(keepends=True)
        anchored = "".join(lines[definition["start_line"] - 1:definition["end_line"]])
        definition["sha256"] = hashlib.sha256(anchored.encode("utf-8")).hexdigest()
        masked = _mask_comments(source)
        call_sites = []
        for match in _ROUTE_LITERAL.finditer(masked):
            call = _find_call_details(masked, match.start())
            if call is None or call[0] != entry["callee"]:
                continue
            fragment = source[match.start("route"):match.end("route")]
            raw_route = _raw_route(source, match.end(), fragment)
            offset = match.start("route")
            line = source.count("\n", 0, offset) + 1
            column = offset - source.rfind("\n", 0, offset)
            call_sites.append({
                "source_path": entry["source"], "line": line, "column": column,
                "raw_route": raw_route, "normalized_route": normalize_route(raw_route),
                "source_sha256": digest,
            })
        entry["call_sites"] = call_sites
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--web-root", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = json.dumps(build(args.web_root.resolve()), ensure_ascii=False, indent=2) + "\n"
    if args.write:
        CONTRACTS.write_text(rendered, encoding="utf-8")
    if args.check or not args.write:
        if CONTRACTS.read_text(encoding="utf-8") != rendered:
            raise SystemExit("Web wrapper contracts are stale")
    print("wrapper contracts current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

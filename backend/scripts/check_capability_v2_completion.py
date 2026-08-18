#!/usr/bin/env python3
"""Evaluate the machine-enforced Capability V2 completion contract."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.capability_v2.completion import evaluate_completion
from backend.capability_governance_test.fingerprint import canonical_fingerprint


GOVERNANCE_ACCEPTANCE_SECTIONS = frozenset({
    "identity", "catalog_separation", "migration", "snapshot", "graph",
    "deterministic_findings", "permissions", "agent_delegation", "health",
    "workflow", "release_gate", "ai_redaction", "ui", "production_exclusion",
})
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_GID = re.compile(r"^[0-9]{1,19}$")
_REQUIRED_HASHES = frozenset({"product_catalog", "governance_extension", "snapshot"})
_REQUIRED_EVIDENCE_GIDS = {
    "snapshot": "snapshot_gid",
    "health": "test_run_gid",
    "release_gate": "release_report_gid",
}


def _governance_acceptance(path: Path) -> dict[str, object]:
    """Validate only the machine-readable completion predicates, never secrets."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"status": "failed", "error_code": "acceptance_report_invalid"}
    if not isinstance(document, dict):
        return {"status": "failed", "error_code": "acceptance_report_invalid"}
    sections = document.get("sections")
    names = set(sections) if isinstance(sections, dict) else set()
    hashes = document.get("hashes")
    report_hash = document.get("report_hash")
    canonical = dict(document)
    canonical.pop("report_hash", None)
    provenance = document.get("provenance")
    section_values = sections if isinstance(sections, dict) else {}
    evidence_gids = {
        name: section_values.get(section, {}).get("evidence", {}).get(field)
        for section, (name, field) in {
            "snapshot": ("snapshot", "snapshot_gid"),
            "test_run": ("health", "test_run_gid"),
            "release_report": ("release_gate", "release_report_gid"),
        }.items()
    }
    passed = (
        document.get("execution_mode") == "live"
        and document.get("status") == "passed"
        and document.get("failed") == 0
        and document.get("skipped") == 0
        and "external_prerequisite" not in document
        and isinstance(document.get("report_gid"), str)
        and _GID.fullmatch(document["report_gid"]) is not None
        and isinstance(hashes, dict)
        and set(hashes) >= _REQUIRED_HASHES
        and all(isinstance(hashes.get(name), str) and _SHA256.fullmatch(hashes[name]) for name in _REQUIRED_HASHES)
        and isinstance(report_hash, str)
        and _SHA256.fullmatch(report_hash) is not None
        and report_hash == canonical_fingerprint(canonical)
        and isinstance(provenance, dict)
        and provenance.get("adapter") == "AI00Backend-CapabilityV2"
        and isinstance(provenance.get("signature"), str)
        and len(provenance["signature"]) >= 32
        and all(isinstance(value, str) and _GID.fullmatch(value) for value in evidence_gids.values())
        and set(document.get("mandatory_sections", ())) == GOVERNANCE_ACCEPTANCE_SECTIONS
        and names == GOVERNANCE_ACCEPTANCE_SECTIONS
        and all(isinstance(value, dict) and value.get("status") == "passed" for value in (sections or {}).values())
    )
    return {"status": "passed" if passed else "failed", "report_path": path.name}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("progress", "strict"), required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--governance-acceptance-report", type=Path)
    args = parser.parse_args()
    report = evaluate_completion(args.root, mode=args.mode)
    rendered_report = report.serialized()
    governance_acceptance = None
    if args.governance_acceptance_report:
        governance_acceptance = _governance_acceptance(args.governance_acceptance_report)
        rendered_report["governance_acceptance"] = governance_acceptance
    rendered = json.dumps(
        rendered_report, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    if args.report:
        target = args.report if args.report.is_absolute() else args.root / args.report
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    failed = not report.complete or (governance_acceptance is not None and governance_acceptance["status"] != "passed")
    return 1 if args.mode == "strict" and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

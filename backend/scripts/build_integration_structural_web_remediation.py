"""Build the independent Task 3B.3e Integration structural evidence manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scripts.check_web_capability_routes import build_report


BASELINE = "ffc281cb141999433c188d4b3b9fb12b9670f8c4"
LEDGER_PATH = "docs/governance/web-route-root-cause-ledger.json"
ATOMIC_PATH = ROOT / "docs/governance/atomic-web-capability-contracts.json"
OUTPUT = ROOT / "docs/governance/integration-structural-web-remediation.json"
PROVIDER_SOURCE = "plugins/integration/integration_backend/capabilities/provider.py"
SCOPE = {
    ("GET", "/api/ext-datasources"),
    ("POST", "/api/ext-datasources"),
    ("PATCH", "/api/ext-datasources/{dynamic}"),
    ("GET", "/api/ext-datasources/{dynamic}/tables"),
    ("POST", "/api/ext-datasources/{dynamic}/test"),
    ("GET", "/api/ext-field-mappings"),
    ("PUT", "/api/ext-field-mappings/batch"),
    ("GET", "/api/ext-mappings"),
    ("POST", "/api/ext-mappings"),
    ("GET", "/api/ext-mappings/{dynamic}/columns"),
    ("POST", "/api/ext-mappings/{dynamic}/import"),
    ("GET", "/api/ext-mappings/{dynamic}/preview"),
}
CANDIDATES = {
    ("GET", "/api/ext-datasources"): "integration.connector.search@1",
    ("POST", "/api/ext-datasources"): "integration.connector.create@1",
    ("PATCH", "/api/ext-datasources/{dynamic}"): "integration.connector.update@1",
    ("GET", "/api/ext-datasources/{dynamic}/tables"): "integration.connector.schema.discover@1",
    ("POST", "/api/ext-datasources/{dynamic}/test"): "integration.connector.connection.test@1",
    ("GET", "/api/ext-field-mappings"): "integration.mapping.get@1",
    ("PUT", "/api/ext-field-mappings/batch"): "integration.mapping.update@1",
    ("GET", "/api/ext-mappings"): "integration.mapping.search@1",
    ("POST", "/api/ext-mappings"): "integration.mapping.create@1",
    ("GET", "/api/ext-mappings/{dynamic}/columns"): "integration.connector.schema.discover@1",
    ("POST", "/api/ext-mappings/{dynamic}/import"): "integration.sync.start@1",
    ("GET", "/api/ext-mappings/{dynamic}/preview"): "integration.mapping.preview@1",
}
EXTERNAL_OUTCOME_UNKNOWN = {
    ("GET", "/api/ext-datasources/{dynamic}/tables"),
    ("POST", "/api/ext-datasources/{dynamic}/test"),
    ("GET", "/api/ext-mappings/{dynamic}/columns"),
    ("POST", "/api/ext-mappings/{dynamic}/import"),
    ("GET", "/api/ext-mappings/{dynamic}/preview"),
}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _baseline() -> tuple[Mapping[str, Any], bytes]:
    result = subprocess.run(
        ["git", "show", f"{BASELINE}:{LEDGER_PATH}"], cwd=ROOT,
        check=True, capture_output=True,
    )
    return json.loads(result.stdout), result.stdout


def _current_contracts() -> dict[tuple[str, str], Mapping[str, Any]]:
    payload = json.loads(ATOMIC_PATH.read_text(encoding="utf-8"))
    return {
        (item["method"], item["normalized_route"]): item
        for item in payload["entries"]
        if (item["method"], item["normalized_route"]) in SCOPE
    }


def _build_manifest(web_root: Path) -> dict[str, Any]:
    ledger, ledger_blob = _baseline()
    baseline_entries = {
        (item["method"], item["normalized_route"]): item
        for item in ledger["entries"]
        if (item["method"], item["normalized_route"]) in SCOPE
    }
    if set(baseline_entries) != SCOPE:
        raise ValueError("pinned Integration structural scope drift")
    contracts = _current_contracts()
    if set(contracts) != SCOPE:
        raise ValueError("Integration atomic contract scope drift")
    provider_path = ROOT / PROVIDER_SOURCE
    provider_hash = _sha256(provider_path.read_bytes())
    report = json.loads(build_report(web_root.resolve()).json())
    unresolved = {
        (item["method"], item["normalized_route"])
        for item in report["routes"] if item["disposition"] == "unresolved"
    }
    if not SCOPE <= unresolved:
        raise ValueError("Integration final inventory no longer preserves unresolved scope")

    entries: list[dict[str, Any]] = []
    for key in sorted(SCOPE):
        source, contract = baseline_entries[key], contracts[key]
        if (
            contract.get("final_disposition") != "domain_design_required"
            or contract.get("provider_anchor") != PROVIDER_SOURCE
            or contract.get("provider_source_sha256") != provider_hash
            or contract.get("reclassification_reason")
            != "The legacy endpoint has no production handler; the governed Integration provider has a non-equivalent contract."
        ):
            raise ValueError(f"Integration provider evidence drift: {key}")
        old_evidence = source["backend_evidence"]
        if old_evidence.get("handler_status") != "absent":
            raise ValueError(f"Integration old-route lifecycle changed: {key}")
        entries.append({
            "method": key[0],
            "normalized_route": key[1],
            "occurrences": source["occurrences"],
            "old_route_evidence": old_evidence,
            "candidate_capability": CANDIDATES[key],
            "provider_anchor": PROVIDER_SOURCE,
            "provider_source_sha256": provider_hash,
            "authorization_and_scope": "not proven equivalent: old handler is absent; provider owner/team scoping cannot be substituted for legacy behavior",
            "credential_handling": "legacy plaintext credentials are not represented; governed inputs accept only credential_ref",
            "external_outcome": "unknown_without_provider_equivalence" if key in EXTERNAL_OUTCOME_UNKNOWN else "not_applicable",
            "confirmation_policy": "unresolved: legacy confirmation cannot be proven equivalent",
            "idempotency_policy": "unresolved: legacy replay semantics cannot be proven equivalent",
            "input_output_contract": "unresolved: legacy route contract is absent and governed closed schema is not response-equivalent",
            "final_disposition": "unresolved",
            "unresolved_reason": contract["reclassification_reason"],
            "final_inventory_mapping": "unresolved",
        })
    counts = {
        "groups": len(entries),
        "occurrences": sum(len(item["occurrences"]) for item in entries),
        "migrated_groups": 0,
        "migrated_occurrences": 0,
        "unresolved_groups": len(entries),
        "unresolved_occurrences": sum(len(item["occurrences"]) for item in entries),
    }
    if counts != {
        "groups": 12, "occurrences": 12, "migrated_groups": 0,
        "migrated_occurrences": 0, "unresolved_groups": 12, "unresolved_occurrences": 12,
    }:
        raise ValueError(f"Integration structural count drift: {counts}")
    manifest = {
        "schema_version": "1.0.0",
        "artifact_id": "task-3b3e-integration-structural-remediation",
        "source_ledger": LEDGER_PATH,
        "source_ledger_revision": BASELINE,
        "source_ledger_sha256": _sha256(ledger_blob),
        "frontend_revision": report["frontend_revision"],
        "frontend_content_hash": report["content_hash"],
        "atomic_contract_manifest_sha256": _sha256(ATOMIC_PATH.read_bytes()),
        "counts": counts,
        "entries": entries,
    }
    manifest["content_sha256"] = _sha256(_canonical(manifest).encode())
    return manifest


def build_manifest(web_root: Path) -> dict[str, Any]:
    return _build_manifest(web_root)


def validate_manifest_against_expected(
    payload: Mapping[str, Any], expected: Mapping[str, Any],
) -> tuple[str, ...]:
    """Compare stored evidence to one independently rebuilt expected manifest."""
    issues: list[str] = []
    entries = payload.get("entries")
    if not isinstance(entries, list) or len(entries) != len(expected["entries"]):
        return ("entry_scope_mismatch",)
    actual = {(item.get("method"), item.get("normalized_route")): item for item in entries if isinstance(item, Mapping)}
    expected_entries = {(item["method"], item["normalized_route"]): item for item in expected["entries"]}
    if set(actual) != set(expected_entries):
        return ("entry_scope_mismatch",)
    for key, expected_entry in expected_entries.items():
        entry = actual[key]
        if entry.get("candidate_capability") != expected_entry["candidate_capability"]:
            issues.append("candidate_target_mismatch")
        if entry.get("provider_source_sha256") != expected_entry["provider_source_sha256"]:
            issues.append("provider_hash_mismatch")
        if entry.get("final_inventory_mapping") != "unresolved":
            issues.append("final_inventory_mismatch")
        if entry.get("occurrences") != expected_entry["occurrences"]:
            issues.append("source_occurrence_mismatch")
        if entry.get("old_route_evidence") != expected_entry["old_route_evidence"]:
            issues.append("old_route_evidence_mismatch")
    actual_without_hash = dict(payload)
    supplied_hash = actual_without_hash.pop("content_sha256", None)
    if supplied_hash != _sha256(_canonical(actual_without_hash).encode()):
        issues.append("content_hash_mismatch")
    expected_without_hash = dict(expected)
    expected_without_hash.pop("content_sha256")
    if actual_without_hash != expected_without_hash:
        issues.append("manifest_evidence_mismatch")
    return tuple(sorted(set(issues)))


def validate_manifest(payload: Mapping[str, Any], web_root: Path) -> tuple[str, ...]:
    """Validate every pinned target, provider, source occurrence, and final inventory."""
    try:
        return validate_manifest_against_expected(payload, _build_manifest(web_root))
    except (OSError, KeyError, TypeError, ValueError, subprocess.CalledProcessError) as exc:
        return (f"evidence_build_failed:{type(exc).__name__}",)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web-root", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    payload = build_manifest(args.web_root)
    rendered = _canonical(payload)
    if args.write:
        OUTPUT.write_text(rendered, encoding="utf-8", newline="\n")
    if args.check:
        try:
            stored = json.loads(OUTPUT.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raise SystemExit("Integration structural remediation manifest is unreadable")
        issues = validate_manifest_against_expected(stored, payload)
        if issues or _canonical(stored) != rendered:
            raise SystemExit("Integration structural remediation manifest is stale: " + ", ".join(issues or ("rendered_mismatch",)))
    print(" ".join(f"{key}={value}" for key, value in payload["counts"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

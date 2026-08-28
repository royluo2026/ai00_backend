"""Build final Craft, Agent, and Project structural-remediation evidence."""
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
from backend.capability_v2.git_tree import read_path


BASELINE = "2db07be4"
LEDGER_PATH = "docs/governance/web-route-root-cause-ledger.json"
ATOMIC_PATH = ROOT / "docs/governance/atomic-web-capability-contracts.json"
OUTPUT = ROOT / "docs/governance/craft-agent-project-structural-web-remediation.json"
SCOPE = {
    ("GET", "/api/rule-engine/check-entry"),
    ("PUT", "/api/rules/{dynamic}"),
    ("POST", "/api/rules/{dynamic}/activate"),
    ("POST", "/api/rules/{dynamic}/deviations"),
    ("POST", "/api/rules/{dynamic}/suspend"),
    ("DELETE", "/api/craft_lib/equipments/{dynamic}"),
    ("DELETE", "/api/craft_lib/fixtures/{dynamic}"),
    ("POST", "/api/flows/test-node"),
    ("POST", "/api/skills/canvas-options"),
    ("POST", "/api/skills/execute-canvas"),
    ("POST", "/api/skills/resume-canvas"),
    ("GET", "/api/lists"),
    ("DELETE", "/api/lists/{dynamic}"),
    ("POST", "/api/approval/orders/{dynamic}/reject"),
}
BOP_KEYS = {("GET", "/api/lists"), ("DELETE", "/api/lists/{dynamic}")}
AGENT_KEYS = {
    ("POST", "/api/flows/test-node"),
    ("POST", "/api/skills/canvas-options"),
    ("POST", "/api/skills/execute-canvas"),
    ("POST", "/api/skills/resume-canvas"),
}
BOP_REASON = "The BOP conditional branch is a Craft version lifecycle outcome, not a Project list operation or direct SQL dispatch."
LISTS_SOURCE = "plugins/craft/craft_backend/routers/lists.py"
APPROVAL_SOURCE = "plugins/craft/craft_backend/routers/approval.py"
PROJECT_SERVICE_SOURCE = "plugins/project_management/project_management_backend/application/service.py"
PROJECT_PROVIDER_SOURCE = "plugins/project_management/project_management_backend/capabilities/provider.py"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _anchor(source_path: str, start_line: int, end_line: int, *needles: str) -> dict[str, Any]:
    """Bind reviewed source semantics to both a line range and full-file content."""
    path = ROOT / source_path
    data = path.read_bytes()
    lines = data.decode("utf-8").splitlines(keepends=True)
    selected = "".join(lines[start_line - 1:end_line])
    if not selected or any(needle not in selected for needle in needles):
        raise ValueError(f"source anchor drift: {source_path}:{start_line}-{end_line}")
    return {
        "source_path": source_path,
        "start_line": start_line,
        "end_line": end_line,
        "source_sha256": _sha256(data),
        "snippet_sha256": _sha256(selected.encode("utf-8")),
    }


def _bop_lifecycle_evidence(key: tuple[str, str]) -> dict[str, Any]:
    if key == ("GET", "/api/lists"):
        return {
            "source": _anchor(LISTS_SOURCE, 123, 140, 'item_type == "bop_version"', '"craft.bop.version.list"'),
            "selector": 'item_type == "bop_version"',
            "capability_id": "craft.bop.version.list",
            "closed_arguments": {"include_archived": False, "page_size": 100},
            "expected_revision_required": False,
            "direct_sql": False,
            "lifecycle_outcome": "Read bounded non-archived Craft BOP versions through the exact owner capability.",
        }
    if key == ("DELETE", "/api/lists/{dynamic}"):
        return {
            "source": _anchor(LISTS_SOURCE, 170, 184, 'item_type == "bop_version"', "expected_revision is required for bop_version", '"craft.bop.version.archive"'),
            "selector": 'item_type == "bop_version"',
            "capability_id": "craft.bop.version.archive",
            "closed_arguments": {"version_gid": "route gid", "expected_revision": "required query integer"},
            "expected_revision_required": True,
            "direct_sql": False,
            "lifecycle_outcome": "Archive the selected Craft BOP version only with its optimistic-concurrency revision.",
            "write_envelope": _anchor(LISTS_SOURCE, 70, 85, "idempotency_key", "approval_reference"),
        }
    raise ValueError(f"not a BOP lifecycle route: {key}")


def _approval_reject_evidence() -> dict[str, Any]:
    text = (ROOT / APPROVAL_SOURCE).read_text(encoding="utf-8")
    if '@router.post("/orders/{gid}/reject")' in text:
        raise ValueError("approval reject route unexpectedly registered")
    return {
        "legacy_reject_route_registered": False,
        "reject_function": _anchor(APPROVAL_SOURCE, 92, 93, "async def reject_order", '"approval.orders.reject"'),
        "adapter_notification": {
            "anchor": _anchor(APPROVAL_SOURCE, 44, 60, "notification = data.pop", "publish_notification"),
            "behavior": "The compatibility adapter removes notification from the response and publishes it after the Project result.",
        },
        "project_operation": _anchor(PROJECT_SERVICE_SOURCE, 148, 148, "approval.orders.reject"),
        "project_audit_policy": {
            "anchor": _anchor(PROJECT_PROVIDER_SOURCE, 66, 71, '"audit_policy": "standard"'),
            "value": "standard",
        },
        "unresolved_gap": "No registered legacy reject route ties the Project transition, standard audit, and adapter notification delivery into one proved idempotent outcome.",
    }


def _baseline() -> tuple[dict[str, Any], bytes]:
    result = subprocess.run(
        ["git", "show", f"{BASELINE}:{LEDGER_PATH}"], cwd=ROOT,
        check=True, capture_output=True,
    )
    return json.loads(result.stdout), result.stdout


def _final_occurrence(
    raw: Mapping[str, Any], web_root: Path, revision: str
) -> dict[str, Any]:
    source = raw.get("source")
    if not isinstance(source, str):
        raise ValueError("final source missing")
    return {
        "occurrence_id": raw.get("occurrence_id"),
        "source": source,
        "line": raw.get("line"),
        "column": raw.get("column"),
        "source_sha256": hashlib.sha256(read_path(web_root, revision, source)).hexdigest(),
    }


def _non_equivalence(source: Mapping[str, Any], key: tuple[str, str]) -> dict[str, str]:
    if key in BOP_KEYS:
        return {"input": BOP_REASON, "output": BOP_REASON, "side_effects": BOP_REASON}
    details = source.get("disposition_details", {})
    mismatch = details.get("contract_mismatch") if isinstance(details, Mapping) else None
    if isinstance(mismatch, Mapping) and set(mismatch) == {"input", "output", "side_effects"}:
        return dict(mismatch)
    reason = details.get("no_stable_target_reason") if isinstance(details, Mapping) else None
    if not isinstance(reason, str) or not reason:
        raise ValueError(f"non-equivalence evidence missing: {key}")
    return {"input": reason, "output": reason, "side_effects": reason}


def _entry(
    key: tuple[str, str], source: Mapping[str, Any], contract: Mapping[str, Any] | None,
    final_occurrences: list[dict[str, Any]],
) -> dict[str, Any]:
    details = source.get("disposition_details", {})
    if key in BOP_KEYS:
        provider = source["backend_evidence"]["source_path"]
        provider_hash = _sha256((ROOT / provider).read_bytes())
        candidate = None
        unresolved = BOP_REASON
    else:
        if not contract or contract.get("final_disposition") != "domain_design_required":
            raise ValueError(f"unsafe contract drift: {key}")
        provider = contract["provider_anchor"]
        provider_hash = contract["provider_source_sha256"]
        candidate = details.get("candidate_target_capability") if isinstance(details, Mapping) else None
        unresolved = contract.get("reclassification_reason")
    if not isinstance(unresolved, str) or not unresolved:
        raise ValueError(f"unresolved reason missing: {key}")
    return {
        "method": key[0],
        "normalized_route": key[1],
        "owner_domain": source["owner_domain"],
        "old_occurrences": source["occurrences"],
        "old_route_evidence": source["backend_evidence"],
        "authorization_and_scope": "No public owner service proves legacy actor, tenant, object, or workspace scope equivalence.",
        "candidate_capability": candidate,
        "provider_anchor": provider,
        "provider_source_sha256": provider_hash,
        "input_output_contract": _non_equivalence(source, key),
        "non_equivalence": _non_equivalence(source, key),
        "lifecycle_confirmation_idempotency": "Unresolved: no exact provider proves lifecycle, confirmation, idempotency, rollback, or outcome recovery equivalence.",
        "runtime_execution": "unresolved_no_bounded_runtime_service" if key in AGENT_KEYS else "not_applicable",
        "bop_conditional_branch": key in BOP_KEYS,
        "lifecycle_evidence": _bop_lifecycle_evidence(key) if key in BOP_KEYS else None,
        "approval_reject_evidence": _approval_reject_evidence() if key == ("POST", "/api/approval/orders/{dynamic}/reject") else None,
        "final_occurrences": final_occurrences,
        "final_disposition": "unresolved",
        "unresolved_reason": unresolved,
        "final_inventory_mapping": "unresolved",
    }


def _build_manifest(web_root: Path) -> dict[str, Any]:
    ledger, ledger_blob = _baseline()
    sources = {
        (item["method"], item["normalized_route"]): item for item in ledger["entries"]
        if (item["method"], item["normalized_route"]) in SCOPE
    }
    if set(sources) != SCOPE:
        raise ValueError("pinned Craft/Agent/Project scope drift")
    atomic = json.loads(ATOMIC_PATH.read_text(encoding="utf-8"))
    contracts = {(item["method"], item["normalized_route"]): item for item in atomic["entries"]}
    if any(key not in contracts for key in SCOPE - BOP_KEYS):
        raise ValueError("atomic contract scope drift")
    report = json.loads(build_report(web_root.resolve()).json())
    final_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for raw in report["routes"]:
        key = raw["method"], raw["normalized_route"]
        if key in SCOPE and raw["disposition"] == "unresolved":
            final_by_key.setdefault(key, []).append(
                _final_occurrence(raw, web_root, report["frontend_revision"])
            )
    if set(final_by_key) != SCOPE or sum(map(len, final_by_key.values())) != 17:
        raise ValueError("final three-domain inventory drift")
    entries = [
        _entry(key, sources[key], contracts.get(key), sorted(final_by_key[key], key=lambda item: item["occurrence_id"]))
        for key in sorted(SCOPE)
    ]
    counts = {
        "groups": len(entries), "occurrences": sum(len(item["final_occurrences"]) for item in entries),
        "migrated_groups": 0, "migrated_occurrences": 0,
        "unresolved_groups": len(entries), "unresolved_occurrences": sum(len(item["final_occurrences"]) for item in entries),
    }
    if counts != {"groups": 14, "occurrences": 17, "migrated_groups": 0, "migrated_occurrences": 0, "unresolved_groups": 14, "unresolved_occurrences": 17}:
        raise ValueError(f"three-domain count drift: {counts}")
    manifest = {
        "schema_version": "1.0.0",
        "artifact_id": "task-3b3e-craft-agent-project-structural-remediation",
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


def validate_manifest_against_expected(payload: Mapping[str, Any], expected: Mapping[str, Any]) -> tuple[str, ...]:
    issues: list[str] = []
    actual = {(item.get("method"), item.get("normalized_route")): item for item in payload.get("entries", []) if isinstance(item, Mapping)}
    wanted = {(item["method"], item["normalized_route"]): item for item in expected["entries"]}
    if set(actual) != set(wanted):
        return ("entry_scope_mismatch",)
    for key, wanted_entry in wanted.items():
        entry = actual[key]
        if entry.get("provider_source_sha256") != wanted_entry["provider_source_sha256"]:
            issues.append("provider_hash_mismatch")
        if entry.get("non_equivalence") != wanted_entry["non_equivalence"]:
            issues.append("non_equivalence_evidence_mismatch")
        if entry.get("lifecycle_evidence") != wanted_entry["lifecycle_evidence"]:
            issues.append("lifecycle_evidence_mismatch")
        if entry.get("approval_reject_evidence") != wanted_entry["approval_reject_evidence"]:
            issues.append("approval_evidence_mismatch")
        if entry.get("final_occurrences") != wanted_entry["final_occurrences"]:
            issues.append("final_occurrence_mismatch")
        if entry.get("final_disposition") != "unresolved" or entry.get("final_inventory_mapping") != "unresolved":
            issues.append("final_inventory_mismatch")
    without_hash = dict(payload)
    supplied_hash = without_hash.pop("content_sha256", None)
    if supplied_hash != _sha256(_canonical(without_hash).encode()):
        issues.append("content_hash_mismatch")
    expected_without_hash = dict(expected)
    expected_without_hash.pop("content_sha256")
    if (
        without_hash.get("source_ledger_revision") != expected_without_hash["source_ledger_revision"]
        or without_hash.get("source_ledger_sha256") != expected_without_hash["source_ledger_sha256"]
    ):
        issues.append("source_ledger_evidence_mismatch")
    if without_hash != expected_without_hash:
        issues.append("manifest_evidence_mismatch")
    return tuple(sorted(set(issues)))


def validate_manifest(payload: Mapping[str, Any], web_root: Path) -> tuple[str, ...]:
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
            raise SystemExit("Craft/Agent/Project structural remediation manifest is unreadable")
        issues = validate_manifest_against_expected(stored, payload)
        if issues or _canonical(stored) != rendered:
            raise SystemExit("Craft/Agent/Project structural remediation manifest is stale: " + ", ".join(issues or ("rendered_mismatch",)))
    print(" ".join(f"{key}={value}" for key, value in payload["counts"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

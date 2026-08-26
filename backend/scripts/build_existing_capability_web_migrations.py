"""Build/check the reviewed Task 3B.3b migration manifest from the root-cause ledger."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.capability_v2.existing_capability_migrations import (
    audit_existing_capability_migrations,
    load_existing_capability_migrations,
)


LEDGER = ROOT / "docs/governance/web-route-root-cause-ledger.json"
OUTPUT = ROOT / "docs/governance/existing-capability-web-migrations.json"

MIGRATIONS = {
    ("DELETE", "/api/knowledges/{dynamic}"),
    ("GET", "/api/knowledge/entries"),
    ("GET", "/api/knowledges/{dynamic}"),
    ("PATCH", "/api/knowledges/{dynamic}"),
    ("POST", "/api/knowledges"),
    ("PUT", "/api/knowledge/entries"),
    ("PUT", "/api/knowledges/{dynamic}"),
    ("GET", "/api/tasks/{dynamic}/entries"),
    ("PUT", "/api/tasks/{dynamic}/entries"),
    ("PUT", "/api/tasks"),
    ("PUT", "/api/issues"),
    ("PUT", "/api/rules/{dynamic}"),
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source(path: str) -> dict[str, str]:
    return {"source_path": path, "sha256": _sha(ROOT / path)}


def _migration_details(method: str, route: str) -> tuple[str, str, list[dict[str, str]]]:
    if "knowledge" in route:
        operation = {
            "DELETE": "gid -> entries_delete payload",
            "GET": "list filters or gid -> exact Knowledge read payload",
            "PATCH": "gid + patch -> entries_update {gid,updates}",
            "POST": "record -> entries_create payload",
            "PUT": "gid + changes -> entries_update {gid,updates}",
        }[method]
        response = "unwrap CapabilityResultV2 and preserve the legacy {success,data} envelope"
        sources = [_source("plugins/knowledge/knowledge_backend/api/knowledge_entries_legacy.py")]
    elif route.startswith("/api/tasks/{dynamic}/entries"):
        operation = "task gid and entries -> atomic {arguments:{item_type:'task',item_gid,entries?}}"
        response = "unwrap Project atomic data; GET preserves data as the entries array"
        sources = [_source("plugins/craft/craft_backend/routers/item_entries.py")]
    elif route in {"/api/tasks", "/api/issues"}:
        item = "task" if route == "/api/tasks" else "issue"
        operation = f"{item} gid plus changed fields -> atomic {{arguments:{{gid,updates}}}}"
        response = "unwrap Project atomic data; callers preserve their existing refresh/error behavior"
        sources = [_source("plugins/craft/craft_backend/routers/promotion.py")]
    else:
        operation = "rule gid plus changed fields -> {operation:'update',gid,record}"
        response = "unwrap Craft rule-library result and preserve the existing promise/error behavior"
        sources = [_source("plugins/craft/craft_backend/routers/rules.py")]
    return operation, response, sources


def _reclassification(entry: dict) -> tuple[str, str, str]:
    route = entry["normalized_route"]
    target = (
        entry["disposition_details"].get("candidate_target_capability")
        or entry["disposition_details"]["target_capability"]
    )
    if route.startswith("/api/approval/"):
        return "adapter_side_effect_missing", "The REST adapter publishes the returned approval notification; direct Gateway invocation does not perform that composition.", "bff_review"
    if route.startswith("/api/ext-"):
        return "contract_shape_mismatch", "The legacy UI payload/result uses datasource, mapping, synchronous import, or field-mapping shapes that the stable Integration contract does not accept or return.", "atomic_capability_review"
    if target.startswith("identity.principal.search"):
        return "projection_mismatch", "The stable shared search returns bounded principal references, not the administrative/full user projection consumed by these routes.", "atomic_capability_review"
    if target.startswith("plugin."):
        return "contract_shape_mismatch", "URL installation and unrestricted uninstall are not equivalent to the signed release lifecycle contract and state preconditions.", "atomic_capability_review"
    if target.startswith("agent.run"):
        return "outcome_mismatch", "Skill-canvas execute/resume semantics and pause tokens are not Agent run resource changes.", "atomic_capability_review"
    if target.startswith(("craft.rule.engine", "craft.rule.release", "craft.rule.waiver")):
        return "outcome_mismatch", "The candidate input/result does not cover the entry audit, release lifecycle, or deviation workflow consumed by the UI.", "atomic_capability_review"
    if target.startswith("base.notification.preference"):
        return "state_model_mismatch", "The stable preference capability uses versioned Base collaboration state while the REST route reads the legacy user projection.", "provider_adapter_review"
    return "provider_equivalence_missing", "The stable descriptor is registered through an unbound reviewed Base outcome port or lacks an adapter proving the legacy projection and side effects.", "provider_adapter_review"


def build_document() -> dict:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    entries = [entry for entry in ledger["entries"] if entry["disposition"] in {
        "existing_capability_migration_required", "existing_capability_migrated",
        "existing_capability_reclassified",
    }]
    groups = []
    for entry in entries:
        key = (entry["method"], entry["normalized_route"])
        target = (
            entry["disposition_details"].get("target_capability")
            or entry["disposition_details"].get("candidate_target_capability")
        )
        target_id, major = target.rsplit("@", 1)
        if key in MIGRATIONS:
            request, response, sources = _migration_details(*key)
            equivalence = {
                "proof_kind": "provider_equivalent_adapter",
                "finding": "An existing owner-domain compatibility adapter invokes this exact stable target and proves the request/result transformation.",
                "sources": sources,
            }
            reclassification = None
            decision = "migrate"
        else:
            reason, finding, followup = _reclassification(entry)
            request = "not applied: the candidate request contract is not provider-equivalent"
            response = "not applied: preserve the unresolved UI behavior until the reviewed follow-up exists"
            sources = [_source(entry["backend_evidence"]["source_path"])]
            equivalence = None
            reclassification = {"reason_code": reason, "finding": finding, "followup": followup, "sources": sources}
            decision = "reclassify"
        groups.append({
            "method": key[0], "normalized_route": key[1],
            "occurrence_count": entry["occurrence_count"], "occurrences": entry["occurrences"],
            "target_capability_id": target_id, "target_major_version": int(major),
            "owner_domain": entry["owner_domain"], "transport_evidence": entry["backend_evidence"],
            "request_transform": request, "response_transform": response, "decision": decision,
            "equivalence_evidence": equivalence, "reclassification": reclassification,
        })
    return {
        "schema_version": "1.0", "artifact_id": "existing-capability-web-migrations",
        "source_ledger": "docs/governance/web-route-root-cause-ledger.json",
        "groups": groups,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    rendered = json.dumps(build_document(), ensure_ascii=False, indent=2) + "\n"
    if args.write:
        OUTPUT.write_text(rendered, encoding="utf-8")
    elif not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != rendered:
        print("existing capability migration manifest is stale", file=sys.stderr)
        return 1
    issues = audit_existing_capability_migrations(ROOT, load_existing_capability_migrations(OUTPUT))
    if issues:
        print("; ".join(issues), file=sys.stderr)
        return 1
    manifest = load_existing_capability_migrations(OUTPUT)
    print(f"groups={len(manifest.groups)} occurrences={sum(g.occurrence_count for g in manifest.groups)} migrated={sum(g.decision == 'migrate' for g in manifest.groups)} reclassified={sum(g.decision == 'reclassify' for g in manifest.groups)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

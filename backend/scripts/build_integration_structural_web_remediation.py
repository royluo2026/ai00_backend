"""Build immutable evidence for the governed Integration Web migration."""
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

from backend.capability_v2.git_tree import read_path
from backend.scripts.check_web_capability_routes import build_report
from plugins.integration.integration_backend.capabilities.contracts import INPUT_SCHEMAS, OUTPUT_SCHEMAS
from plugins.integration.integration_backend.capabilities.descriptors import specs
from plugins.integration.integration_backend.capabilities.provider import descriptor_for


BASELINE = "ffc281cb141999433c188d4b3b9fb12b9670f8c4"
LEDGER_PATH = "docs/governance/web-route-root-cause-ledger.json"
ATOMIC_PATH = ROOT / "docs/governance/atomic-web-capability-contracts.json"
OUTPUT = ROOT / "docs/governance/integration-structural-web-remediation.json"
FRONTEND_SOURCE = "web/ext_datasource/ext_ds.js"
FRONTEND_DIST = "dist-production/web/ext_datasource/ext_ds.js"
PROVIDER_SOURCE = "plugins/integration/integration_backend/capabilities/provider.py"
SERVICE_SOURCE = "plugins/integration/integration_backend/application/service.py"
CONTRACTS_SOURCE = "plugins/integration/integration_backend/capabilities/contracts.py"
TARGET_CATALOG_SOURCE = "plugins/integration/integration_backend/infrastructure/target_catalog.py"
TARGET_CATALOG_MIGRATION = "backend/db/migrations/domains/integration/0004_integration_target_catalog.sql"

CANDIDATES = {
    ("GET", "/api/ext-datasources"): "integration.connector.search@1",
    ("POST", "/api/ext-datasources"): "integration.connector.create@1",
    ("PATCH", "/api/ext-datasources/{dynamic}"): "integration.connector.update@1",
    ("GET", "/api/ext-datasources/{dynamic}/tables"): "integration.connector.schema.discover@1",
    ("POST", "/api/ext-datasources/{dynamic}/test"): "integration.connector.connection.test@1",
    ("GET", "/api/ext-field-mappings"): "integration.field_mapping.search@1",
    ("PUT", "/api/ext-field-mappings/batch"): "integration.field_mapping.batch.update@1",
    ("GET", "/api/ext-mappings"): "integration.mapping.search@1",
    ("POST", "/api/ext-mappings"): "integration.mapping.create@1",
    ("GET", "/api/ext-mappings/{dynamic}/columns"): "integration.mapping.source_columns.discover@1",
    ("POST", "/api/ext-mappings/{dynamic}/import"): "integration.mapping.import.start@1",
    ("GET", "/api/ext-mappings/{dynamic}/preview"): "integration.mapping.preview@1",
}
SCOPE = frozenset(CANDIDATES)
DESCRIPTORS = {item.id: descriptor_for(item) for item in specs()}
RUNTIME = {
    "integration.connector.connection.test", "integration.connector.schema.discover",
    "integration.mapping.source_columns.discover", "integration.mapping.preview",
}
SERVICE_NEEDLES = {
    "integration.connector.connection.test": "async def _connector_outcome",
    "integration.connector.schema.discover": "async def _connector_outcome",
    "integration.mapping.source_columns.discover": "async def _mapping_read",
    "integration.mapping.preview": "async def _mapping_read",
}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _line_anchor(source_path: str, needle: str, occurrence: int = 0) -> dict[str, Any]:
    lines = (ROOT / source_path).read_text(encoding="utf-8").splitlines(keepends=True)
    matches = [index for index, line in enumerate(lines) if needle in line]
    if len(matches) <= occurrence:
        raise ValueError(f"evidence anchor missing: {source_path}:{needle}")
    index = matches[occurrence]
    return {
        "source_path": source_path,
        "start_line": index + 1,
        "end_line": index + 1,
        "sha256": hashlib.sha256(lines[index].encode("utf-8")).hexdigest(),
    }


def _git_blob(web_root: Path, revision: str, path: str) -> str:
    return subprocess.run(
        ["git", "rev-parse", f"{revision}:{path}"], cwd=web_root,
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _frontend_anchor(web_root: Path, revision: str, capability: str) -> dict[str, Any]:
    source = read_path(web_root, revision, FRONTEND_SOURCE).decode("utf-8")
    lines = source.splitlines(keepends=True)
    matches = [index for index, line in enumerate(lines) if f"'{capability}'" in line]
    if not matches:
        raise ValueError(f"frontend capability anchor missing: {capability}")
    index = matches[-1]
    return {
        "source_path": FRONTEND_SOURCE,
        "line": index + 1,
        "sha256": hashlib.sha256(lines[index].encode("utf-8")).hexdigest(),
        "blob": _git_blob(web_root, revision, FRONTEND_SOURCE),
    }


def _baseline() -> tuple[Mapping[str, Any], bytes]:
    result = subprocess.run(
        ["git", "show", f"{BASELINE}:{LEDGER_PATH}"], cwd=ROOT,
        check=True, capture_output=True,
    )
    return json.loads(result.stdout), result.stdout


def _candidate_policy(capability: str) -> dict[str, str]:
    candidate = capability.removesuffix("@1")
    descriptor = DESCRIPTORS[candidate]
    external = (
        "asynchronous_import" if candidate == "integration.mapping.import.start"
        else "connector_runtime" if candidate in RUNTIME else "none"
    )
    return {
        "authorization_scope": "CapabilityContext actor_gid and team_gid",
        "confirmation": descriptor.confirmation_policy,
        "idempotency": descriptor.idempotency_policy,
        "external_side_effect": external,
        "timeout": "15_seconds" if external == "connector_runtime" else "not_applicable",
        "outcome_recovery": "durable accepted/failed/succeeded/outcome_unknown operation",
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

    report = json.loads(build_report(web_root.resolve()).json())
    revision = report["frontend_revision"]
    source = read_path(web_root, revision, FRONTEND_SOURCE)
    dist = read_path(web_root, revision, FRONTEND_DIST)
    if source != dist:
        raise ValueError("Integration official source/dist drift")
    text = source.decode("utf-8")
    forbidden = ("/api/ext-datasources", "/api/ext-mappings", "/api/ext-field-mappings")
    if any(token in text for token in forbidden):
        raise ValueError("Integration legacy route fallback remains")
    if any(token in text.casefold() for token in ("password", "credentials", "filter_sql")):
        raise ValueError("Integration secret or arbitrary SQL browser field remains")

    unresolved = [item for item in report["routes"] if item["disposition"] == "unresolved"]
    remainder = {
        "groups": len({(item["method"], item["normalized_route"]) for item in unresolved}),
        "occurrences": len(unresolved),
    }
    if remainder != {"groups": 14, "occurrences": 17}:
        raise ValueError(f"canonical remainder drift: {remainder}")
    if any((item["method"], item["normalized_route"]) in SCOPE for item in unresolved):
        raise ValueError("Integration unresolved route remains")

    provider_anchor = _line_anchor(PROVIDER_SOURCE, "def descriptor_for")
    target_catalog = {
        "adapter_anchor": _line_anchor(TARGET_CATALOG_SOURCE, "class IntegrationTargetCatalog"),
        "migration_sha256": _sha256((ROOT / TARGET_CATALOG_MIGRATION).read_bytes()),
        "migration_path": TARGET_CATALOG_MIGRATION,
        "scope": "owner_gid and team_gid required; missing binding or Catalog release fails closed",
    }
    entries = []
    for key in sorted(SCOPE):
        capability = CANDIDATES[key]
        candidate = capability.removesuffix("@1")
        entries.append({
            "method": key[0],
            "normalized_route": key[1],
            "occurrences": baseline_entries[key]["occurrences"],
            "old_route_evidence": baseline_entries[key]["backend_evidence"],
            "candidate_capability": capability,
            "provider_anchor": provider_anchor,
            "provider_source_sha256": _sha256((ROOT / PROVIDER_SOURCE).read_bytes()),
            "service_anchor": _line_anchor(
                SERVICE_SOURCE, SERVICE_NEEDLES.get(candidate, candidate)
            ),
            "contract_evidence": {
                "input_anchor": _line_anchor(CONTRACTS_SOURCE, f'"{candidate}"', 0),
                "output_anchor": _line_anchor(CONTRACTS_SOURCE, f'"{candidate}"', 1),
                "input_schema": INPUT_SCHEMAS[candidate],
                "output_schema": OUTPUT_SCHEMAS[candidate],
            },
            "frontend_capability_evidence": _frontend_anchor(web_root, revision, candidate),
            "candidate_policy": _candidate_policy(capability),
            "legacy_route_absent": True,
            "plaintext_credentials_absent": True,
            "arbitrary_sql_absent": True,
            "final_disposition": "migrated",
            "final_inventory_mapping": "capability",
        })
        entries[-1]["owner_service_evidence"] = entries[-1]["service_anchor"]
        entries[-1]["frontend_call_sites"] = [entries[-1]["frontend_capability_evidence"]]

    manifest = {
        "schema_version": "2.0.0",
        "artifact_id": "integration-structural-remediation",
        "source_ledger": LEDGER_PATH,
        "source_ledger_revision": BASELINE,
        "source_ledger_sha256": _sha256(ledger_blob),
        "frontend_revision": revision,
        "frontend_content_hash": report["content_hash"],
        "frontend_source": {
            "path": FRONTEND_SOURCE, "blob": _git_blob(web_root, revision, FRONTEND_SOURCE),
            "sha256": _sha256(source),
        },
        "frontend_dist": {
            "path": FRONTEND_DIST, "blob": _git_blob(web_root, revision, FRONTEND_DIST),
            "sha256": _sha256(dist),
        },
        "atomic_contract_manifest_sha256": _sha256(ATOMIC_PATH.read_bytes()),
        "target_catalog": target_catalog,
        "canonical_remainder": remainder,
        "counts": {
            "groups": 12, "occurrences": 12,
            "migrated_groups": 12, "migrated_occurrences": 12,
            "unresolved_groups": 0, "unresolved_occurrences": 0,
        },
        "entries": entries,
    }
    manifest["content_sha256"] = _sha256(_canonical(manifest).encode())
    return manifest


def build_manifest(web_root: Path) -> dict[str, Any]:
    return _build_manifest(web_root)


def validate_manifest_against_expected(
    payload: Mapping[str, Any], expected: Mapping[str, Any],
) -> tuple[str, ...]:
    issues: list[str] = []
    entries = payload.get("entries")
    expected_entries = expected.get("entries")
    if not isinstance(entries, list) or not isinstance(expected_entries, list) or len(entries) != len(expected_entries):
        return ("entry_scope_mismatch",)
    actual = {(item.get("method"), item.get("normalized_route")): item for item in entries}
    wanted = {(item.get("method"), item.get("normalized_route")): item for item in expected_entries}
    if set(actual) != set(wanted):
        return ("entry_scope_mismatch",)
    for key, wanted_entry in wanted.items():
        item = actual[key]
        if item.get("candidate_capability") != wanted_entry.get("candidate_capability"):
            issues.append("candidate_target_mismatch")
        if item.get("final_inventory_mapping") != "capability":
            issues.append("final_inventory_mismatch")
        if item.get("service_anchor") != wanted_entry.get("service_anchor"):
            issues.append("service_evidence_mismatch")
        if item.get("contract_evidence") != wanted_entry.get("contract_evidence"):
            issues.append("contract_evidence_mismatch")
        if item.get("frontend_capability_evidence") != wanted_entry.get("frontend_capability_evidence"):
            issues.append("frontend_evidence_mismatch")
    actual_without_hash = dict(payload)
    supplied_hash = actual_without_hash.pop("content_sha256", None)
    if supplied_hash != _sha256(_canonical(actual_without_hash).encode()):
        issues.append("content_hash_mismatch")
    expected_without_hash = dict(expected)
    expected_without_hash.pop("content_sha256", None)
    if actual_without_hash != expected_without_hash:
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
            raise SystemExit("Integration structural remediation manifest is unreadable")
        issues = validate_manifest_against_expected(stored, payload)
        if issues or _canonical(stored) != rendered:
            raise SystemExit("Integration structural remediation manifest is stale: " + ", ".join(issues or ("rendered_mismatch",)))
    print(" ".join(f"{key}={value}" for key, value in payload["counts"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

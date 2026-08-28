from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import subprocess
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.capability_v2.atomic_web_contracts import (
    EXAMPLES, EXAMPLE_OUTPUTS, ROUTE_CAPABILITIES, UNSAFE_REASONS,
)
from backend.capabilities.registry_next import CapabilityRegistry
from backend.base.web_atomic import register_atomic_web_capabilities
from plugins.integration.integration_backend.capabilities.descriptors import specs as integration_specs
from plugins.integration.integration_backend.capabilities.provider import descriptor_for as integration_descriptor


LEDGER = ROOT / "docs/governance/web-route-root-cause-ledger.json"
OUTPUT = ROOT / "docs/governance/atomic-web-capability-contracts.json"
SOURCE_REVISION = "5cc460e5ed0aa0227549f7eca3017707777d51a5"
SCOPE = {"existing_capability_reclassified", "new_atomic_capability_required"}
OWNER_PREFIX = {"project_management": "project"}
INTEGRATION_ROUTES = {
    ("GET", "/api/ext-datasources"): "integration.connector.search",
    ("POST", "/api/ext-datasources"): "integration.connector.create",
    ("PATCH", "/api/ext-datasources/{dynamic}"): "integration.connector.update",
    ("GET", "/api/ext-datasources/{dynamic}/tables"): "integration.connector.schema.discover",
    ("POST", "/api/ext-datasources/{dynamic}/test"): "integration.connector.connection.test",
    ("GET", "/api/ext-field-mappings"): "integration.field_mapping.search",
    ("PUT", "/api/ext-field-mappings/batch"): "integration.field_mapping.batch.update",
    ("GET", "/api/ext-mappings"): "integration.mapping.search",
    ("POST", "/api/ext-mappings"): "integration.mapping.create",
    ("GET", "/api/ext-mappings/{dynamic}/columns"): "integration.mapping.source_columns.discover",
    ("POST", "/api/ext-mappings/{dynamic}/import"): "integration.mapping.import.start",
    ("GET", "/api/ext-mappings/{dynamic}/preview"): "integration.mapping.preview",
}


def _schema_example(schema: dict[str, Any]) -> Any:
    if schema.get("oneOf") and not schema.get("type"):
        return _schema_example(schema["oneOf"][0])
    if schema.get("anyOf"):
        branch = next((item for item in schema["anyOf"] if item.get("type") != "null"), schema["anyOf"][0])
        return _schema_example(branch)
    kind = schema.get("type")
    if kind == "object":
        required = schema.get("required", ())
        result = {name: _schema_example(schema["properties"][name]) for name in required}
        if schema.get("oneOf"):
            for name in schema["oneOf"][0].get("required", ()):
                result[name] = _schema_example(schema["properties"][name])
        return result
    if kind == "array":
        count = max(int(schema.get("minItems", 0)), 1 if schema.get("minItems") else 0)
        return [_schema_example(schema["items"]) for _ in range(count)]
    if kind == "integer":
        return max(int(schema.get("minimum", 1)), 1)
    if kind == "number":
        return max(float(schema.get("minimum", 1)), 1)
    if kind == "boolean":
        return False
    if kind == "null":
        return None
    enum = schema.get("enum")
    return enum[0] if enum else "example"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def build_manifest() -> dict[str, Any]:
    ledger_blob = subprocess.run(
        ["git", "show", f"{SOURCE_REVISION}:docs/governance/web-route-root-cause-ledger.json"],
        cwd=ROOT, check=True, capture_output=True,
    ).stdout
    ledger = json.loads(ledger_blob.decode("utf-8"))
    scoped = [entry for entry in ledger["entries"] if entry["disposition"] in SCOPE]
    registry = CapabilityRegistry()
    register_atomic_web_capabilities(registry)
    integration_by_id = {item.id: item for item in integration_specs()}
    entries = []
    for source in scoped:
        key = (source["method"], source["normalized_route"])
        integration_id = INTEGRATION_ROUTES.get(key)
        reviewed = {"id": integration_id} if integration_id else ROUTE_CAPABILITIES.get(key)
        unsafe_reason = None if integration_id else UNSAFE_REASONS.get(key)
        if (reviewed is None) == (unsafe_reason is None):
            raise ValueError(f"scope key must have exactly one reviewed conclusion: {key}")
        owner = source["owner_domain"]
        capability_id = reviewed["id"] if reviewed else None
        provider = registry.get(capability_id) if reviewed and not integration_id else None
        integration_spec = integration_by_id.get(capability_id) if integration_id else None
        descriptor = integration_descriptor(integration_spec) if integration_spec else (provider.descriptor if provider else None)
        provider_anchor = (
            "plugins/project_management/project_management_backend/capabilities/reviewed.py:def register_reviewed_capabilities"
            if reviewed and owner == "project_management"
            else (
                "plugins/integration/integration_backend/capabilities/provider.py:def descriptor_for"
                if integration_id else
                "backend/base/web_atomic.py:HANDLERS: dict" if reviewed and owner == "base"
                else source["backend_evidence"]["source_path"]
            )
        )
        provider_source_path = provider_anchor.partition(":")[0]
        provider_blob = (ROOT / provider_source_path).read_bytes()
        is_write = bool(descriptor and descriptor.side_effect_level.value != "read")
        entry = {
            "method": source["method"],
            "normalized_route": source["normalized_route"],
            "owner_domain": owner,
            "owner_prefix": OWNER_PREFIX.get(owner, owner),
            "baseline_disposition": source["disposition"],
            "occurrences": source["occurrences"],
            "provider_anchor": provider_anchor,
            "provider_source_sha256": "sha256:" + hashlib.sha256(provider_blob).hexdigest(),
            "handler_evidence": source["backend_evidence"],
            "capability_id": capability_id,
            "major_version": 1 if reviewed else None,
            "input_schema": dict((integration_spec or provider.spec).input_schema) if reviewed else {"type": "object", "properties": {}, "additionalProperties": False},
            "output_schema": dict((integration_spec or provider.spec).output_schema) if reviewed else {"type": "object", "properties": {}, "additionalProperties": False},
            "example_input": _schema_example(dict(integration_spec.input_schema)) if integration_spec else (EXAMPLES[capability_id] if reviewed else {}),
            "example_output": _schema_example(dict(integration_spec.output_schema)) if integration_spec else (EXAMPLE_OUTPUTS[capability_id] if reviewed else {}),
            "side_effects": [descriptor.side_effects] if descriptor else [],
            "atomicity_class": (
                "read" if not is_write else
                "single_transaction" if descriptor.consistency_policy == "strong" and (integration_id in {"integration.mapping.create", "integration.field_mapping.batch.update"} or getattr(getattr(provider, "handler", None), "__capability_transactional__", False))
                else "external"
            ),
            "consistency_policy": descriptor.consistency_policy if descriptor else None,
            "authorization_policy": descriptor.authorization_policy if descriptor else None,
            "required_permissions": list((integration_spec or provider.spec).permissions) if reviewed else [],
            "confirmation_policy": descriptor.confirmation_policy if descriptor else None,
            "idempotency_policy": descriptor.idempotency_policy if descriptor else None,
            "final_disposition": "migrated" if reviewed else "domain_design_required",
            "reclassification_reason": None if reviewed else unsafe_reason,
            "review_reference": "task-3b3c:exact-provider-review",
        }
        entries.append(entry)
    entries.sort(key=lambda item: (item["owner_domain"], item["normalized_route"], item["method"]))
    counts = {}
    for owner in sorted({item["owner_domain"] for item in entries}):
        owned = [item for item in entries if item["owner_domain"] == owner]
        counts[owner] = {"groups": len(owned), "occurrences": sum(len(item["occurrences"]) for item in owned)}
    manifest = {
        "schema_version": "1.0.0",
        "artifact_id": "task-3b3c-atomic-web-contracts",
        "source_ledger": str(LEDGER.relative_to(ROOT)).replace("\\", "/"),
        "source_ledger_revision": SOURCE_REVISION,
        "source_ledger_sha256": "sha256:" + hashlib.sha256(ledger_blob).hexdigest(),
        "baseline_frontend_revision": ledger["final_evidence"]["frontend_revision"],
        "counts_by_owner": counts,
        "entries": entries,
    }
    manifest["content_sha256"] = "sha256:" + hashlib.sha256(_canonical(manifest).encode()).hexdigest()
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = _canonical(build_manifest())
    if args.write:
        OUTPUT.write_text(rendered, encoding="utf-8")
    if args.check or not args.write:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != rendered:
            raise SystemExit("atomic Web contract manifest is stale")
    payload = json.loads(rendered)
    migrated = sum(item["final_disposition"] == "migrated" for item in payload["entries"])
    print(f"groups={len(payload['entries'])} occurrences={sum(len(x['occurrences']) for x in payload['entries'])} migrated={migrated} reclassified={len(payload['entries']) - migrated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend/scripts/build_base_structural_web_remediation.py"


def _module():
    spec = importlib.util.spec_from_file_location("base_structural_manifest", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_conserves_pinned_base_scope_and_keeps_plugins_unresolved():
    payload = _module().build_manifest(ROOT.parent / "workmanship-web-capability-governance")
    assert payload["counts"] == {"groups": 16, "occurrences": 33, "migrated_groups": 5, "migrated_occurrences": 17, "unresolved_groups": 11, "unresolved_occurrences": 16}
    entries = {(item["method"], item["normalized_route"]): item for item in payload["entries"]}
    for key in (("POST", "/api/plugin/install"), ("DELETE", "/api/plugin/uninstall/{dynamic}")):
        assert entries[key]["final_disposition"] == "unresolved"
        assert "signed" in entries[key]["unresolved_reason"] or "lifecycle" in entries[key]["unresolved_reason"]
    for entry in entries.values():
        assert entry["occurrences"]
        assert entry["old_route_evidence"]["source_path"]
        assert entry["final_inventory_mapping"] in {"capability", "unresolved"}

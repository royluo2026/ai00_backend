from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from backend.base.file_store_public_config import (
    PUBLIC_CONFIG_CAPABILITY_ID,
    public_file_store_config,
    register_file_store_public_config_capability,
)
from backend.capabilities.registry_next import CapabilityRegistry
from backend.capabilities.validation_next import validate_payload
from backend.capability_v2.special_web_residuals import audit_manifest


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/governance/special-web-residual-contracts.json"
CATALOG = ROOT / "docs/capabilities/catalog.v2.json"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_conserves_six_groups_and_twenty_three_occurrences() -> None:
    manifest = _manifest()
    assert len(manifest["entries"]) == 6
    assert sum(len(entry["baseline_occurrences"]) for entry in manifest["entries"]) == 23
    assert manifest["counts"] == {
        "conditional_dispatch": {"groups": 3, "occurrences": 20},
        "truthful_bff": {"groups": 2, "occurrences": 2},
        "file_store_capability": {"groups": 1, "occurrences": 1},
    }
    assert audit_manifest(ROOT, manifest) == ()


@pytest.mark.parametrize("mutation", ["occurrence", "source_hash", "target", "inventory_hash"])
def test_manifest_mutations_fail_closed(mutation: str) -> None:
    manifest = copy.deepcopy(_manifest())
    if mutation == "occurrence":
        manifest["entries"][0]["baseline_occurrences"].pop()
    elif mutation == "source_hash":
        manifest["entries"][0]["baseline_occurrences"][0]["source_sha256"] = "0" * 64
    elif mutation == "target":
        manifest["entries"][0]["branch_capabilities"][0] = "project.fake@1"
    else:
        manifest["final_inventory_sha256"] = "sha256:" + "0" * 64
    assert audit_manifest(ROOT, manifest)


def test_file_store_capability_uses_closed_public_projection(monkeypatch) -> None:
    from backend.platform_sdk import file_store_config

    monkeypatch.setattr(file_store_config, "read_runtime_file_store_config", lambda: {
        "source": "db", "access_key": "abcdefghijkl", "secret_key": "top-secret",
        "endpoint": "https://s3.example", "bucket": "ai00", "public_url": "https://cdn.example",
        "internal_path": "C:/secret", "ois": {"identify": "tenant", "idaas_client_secret": "ois-secret"},
        "ois_source": "db",
    })
    admin = type("Context", (), {"active_roles": ("team_admin",), "user_gid": "u1"})()
    output = public_file_store_config({}, admin)
    assert output["success"] is True
    assert output["is_admin"] is True
    assert output["key_preview"] == "abcd••••ijkl"
    assert "secret_key" not in json.dumps(output)
    assert "idaas_client_secret" not in json.dumps(output)
    assert "internal_path" not in json.dumps(output)

    registry = CapabilityRegistry()
    register_file_store_public_config_capability(registry)
    item = registry.get(PUBLIC_CONFIG_CAPABILITY_ID, 1)
    assert item.spec.owner == "base"
    assert item.spec.permissions == ()
    assert item.descriptor.authorization_policy == "base.v2:authenticated"
    assert item.descriptor.lifecycle_status == "stable"
    assert item.spec.input_schema == {"type": "object", "properties": {}, "additionalProperties": False}
    validate_payload(dict(item.spec.output_schema), output, label="output")
    with pytest.raises(ValueError, match="unknown field"):
        validate_payload(dict(item.spec.output_schema), {**output, "secret_key": "leak"}, label="output")


def test_catalog_contains_exact_file_store_capability() -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    descriptor = next(item for item in catalog["capabilities"] if item["id"] == PUBLIC_CONFIG_CAPABILITY_ID)
    assert descriptor["owner_domain"] == "base"
    assert descriptor["lifecycle_status"] == "stable"
    assert descriptor["side_effect_level"] == "read"
    assert descriptor["input_schema"]["additionalProperties"] is False
    assert descriptor["output_schema"]["additionalProperties"] is False


def test_bff_registry_names_exact_constituents_and_binds_sources() -> None:
    registry = json.loads((ROOT / "docs/governance/bff_capability_registry.json").read_text(encoding="utf-8"))
    entries = {entry["route_path"]: entry for entry in registry["entries"]}
    assert entries["/api/workbench/home"]["constituents"] == [
        {"capability_id": "project.project.read.atomic.projects_search", "major_version": 1},
        {"capability_id": "project.follow.read.atomic.follows_list", "major_version": 1},
    ]
    assert entries["/api/workbench/panel1"]["constituents"] == [
        {"capability_id": "project.task.read.atomic.tasks_search", "major_version": 1},
        {"capability_id": "project.issue.read.atomic.issues_search", "major_version": 1},
    ]
    for entry in entries.values():
        source = ROOT / entry["source"]
        assert entry["source_sha256"] == "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
        assert entry["executor"] == "backend.routers.workbench_home:execute_constituents"
        assert entry["partial_failure_policy"] == "continue_in_declared_order_omit_failed"

from __future__ import annotations

import copy
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from starlette.requests import Request

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
    assert manifest["final_outcomes"] == {
        "fully_governed": {"groups": 4, "baseline_occurrences": 9},
        "mixed_gateway_and_reclassified_rest": {"groups": 2, "baseline_occurrences": 14},
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
    serialized = json.dumps(output)
    assert "key_preview" not in output
    assert "secret_preview" not in serialized
    assert "top-secret" not in serialized
    assert "ois-secret" not in serialized
    assert "abcdefghijkl" not in serialized
    assert "secret_key" not in serialized
    assert "idaas_client_secret" not in serialized
    assert "internal_path" not in serialized

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


def test_file_store_rest_get_delegates_to_exact_gateway_capability() -> None:
    import backend.routers.file_store as route

    class Gateway:
        catalog_release = "rel_test"
        envelopes = []

        async def invoke(self, envelope):
            self.envelopes.append(envelope)
            return type("Result", (), {"ok": True, "data": {"data": {"success": True}}, "error": None})()

    gateway = Gateway()
    request = Request({"type": "http", "method": "GET", "path": "/api/file-store/config", "headers": []})
    principal = type("Principal", (), {"model_dump": lambda self: {
        "user_id": "u1", "authentication_method": "jwt",
        "authenticated_at": "2026-08-27T00:00:00Z",
    }})()
    value = asyncio.run(route.get_config(request, {"gid": "u1", "org_role": "member"}, principal, gateway))
    assert value == {"success": True}
    assert [envelope.capability_id for envelope in gateway.envelopes] == [PUBLIC_CONFIG_CAPABILITY_ID]
    source = (ROOT / "backend/routers/file_store.py").read_text(encoding="utf-8")
    assert "public_file_store_config" not in source


def test_bop_list_compatibility_branches_have_no_router_sql() -> None:
    source = (ROOT / "plugins/craft/craft_backend/routers/lists.py").read_text(encoding="utf-8")
    assert "get_conn" not in source
    assert "workmanship_bop_bop_versions" not in source
    assert "SELECT " not in source
    assert "UPDATE " not in source


def test_bop_rest_branches_delegate_to_exact_gateway_outcomes() -> None:
    import plugins.craft.craft_backend.routers.lists as route

    class Error:
        code = "confirmation_required"

        def model_dump(self, **_kwargs):
            return {"code": self.code}

    class Gateway:
        catalog_release = "rel_test"

        def __init__(self):
            self.envelopes = []
            self.approvals = []

        async def invoke(self, envelope):
            self.envelopes.append(envelope)
            if envelope.capability_id == "craft.bop.version.archive" and envelope.approval_reference is None:
                return type("Result", (), {"ok": False, "data": None, "error": Error()})()
            data = ({"items": [{"version_gid": "b1", "version_tag": "V1", "revision": 3}], "next_cursor": None}
                    if envelope.capability_id == "craft.bop.version.list"
                    else {"version_gid": "b1", "status": "archived", "revision": 4})
            return type("Result", (), {"ok": True, "data": {"data": data}, "error": None})()

        async def request_approval(self, envelope):
            self.approvals.append(envelope)
            return type("Approval", (), {"token": "approved"})()

    principal = type("Principal", (), {"model_dump": lambda self: {
        "user_id": "u1", "authentication_method": "jwt",
        "authenticated_at": datetime(2026, 8, 27, tzinfo=UTC),
    }})()
    user = {"gid": "u1", "team_id": "t1", "org_role": "member"}
    request = Request({"type": "http", "method": "GET", "path": "/api/lists", "headers": []})
    gateway = Gateway()

    listed = asyncio.run(route.list_cloud_lists(
        item_type="bop_version", request=request, current_user=user,
        principal=principal, gateway=gateway,
    ))
    deleted = asyncio.run(route.delete_cloud_list(
        "b1", request, item_type="bop_version", expected_revision=3,
        current_user=user, principal=principal, gateway=gateway,
    ))

    assert listed["data"][0] == {
        "gid": "b1", "name": "V1", "maturity": None, "takt_time": None,
        "status": None, "created_at": None, "storage_scope": "cloud",
        "owner_type": "user", "owner_gid": "", "item_type": "bop_version",
        "revision": 3, "color": "#5b8dee",
    }
    assert deleted == {"success": True}
    assert [item.capability_id for item in gateway.envelopes] == [
        "craft.bop.version.list", "craft.bop.version.archive", "craft.bop.version.archive",
    ]
    assert gateway.envelopes[1].idempotency_key is None
    assert gateway.envelopes[2].idempotency_key == gateway.envelopes[1].request_id
    assert gateway.envelopes[2].approval_reference == "approved"
    assert len(gateway.approvals) == 1


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
        {"capability_id": "project.project.read.atomic.projects_search", "major_version": 1, "omittable_error_codes": []},
        {"capability_id": "project.follow.read.atomic.follows_list", "major_version": 1, "omittable_error_codes": []},
    ]
    assert entries["/api/workbench/panel1"]["constituents"] == [
        {"capability_id": "project.task.read.atomic.tasks_search", "major_version": 1, "omittable_error_codes": []},
        {"capability_id": "project.issue.read.atomic.issues_search", "major_version": 1, "omittable_error_codes": []},
    ]
    for entry in entries.values():
        source = ROOT / entry["source"]
        assert entry["source_sha256"] == "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
        assert entry["executor"] == "backend.routers.workbench_home:execute_constituents"
        assert entry["partial_failure_policy"] == "fail_closed_except_declared_business_absence"

from pathlib import Path

from backend.capability_v2.catalog import load_catalog_release
from backend.capabilities.models_next import CapabilityRisk, CapabilitySpec
from plugins.project_management.project_management_backend.capabilities.provider import descriptor_for
from plugins.project_management.project_management_backend.capabilities.reviewed import register_reviewed_capabilities
from backend.capabilities.registry_next import CapabilityRegistry
from plugins.craft.craft_backend.capabilities.contracts import INPUT_SCHEMAS, OUTPUT_SCHEMAS
from plugins.project_management.project_management_backend.capabilities import reviewed as project_reviewed


def test_execution_structure_is_available_to_governed_plugins():
    root = Path(__file__).resolve().parents[2]
    release = load_catalog_release(
        (root / "docs/governance/capability-catalog-release.json").read_text(encoding="utf-8")
    )
    descriptor = next(
        item for item in release.descriptors
        if item.id == "craft.bop.execution_structure.get" and item.major_version == 1
    )
    assert descriptor.exposure.plugin is True


def test_reference_plugin_renders_problem_recommendations_and_invalidates_stale_checks():
    root = Path(__file__).resolve().parents[2]
    plugin = root / "packages/plugin-sdk/examples/project-readiness"
    html = (plugin / "index.html").read_text(encoding="utf-8")
    app = (plugin / "app.js").read_text(encoding="utf-8")
    assert 'id="recommendations"' in html
    assert "requestGeneration+=1" in app.replace(" ", "")


def test_project_management_writes_use_external_domain_transactions():
    descriptor = descriptor_for(CapabilitySpec(
        owner="project_management", id="project.test.write", version=1,
        description="test", risk=CapabilityRisk.WRITE,
        input_schema={"type": "object"}, output_schema={"type": "object"},
    ))
    assert descriptor.consistency_policy == "external"


def test_project_management_permissions_match_live_role_model():
    registry = CapabilityRegistry()
    register_reviewed_capabilities(registry)
    assert registry.get("project.project.change.apply").spec.permissions == ("project.manage_any",)
    assert registry.get("project.project.read").spec.permissions == ("project.view",)
    arguments = registry.get("project.project.change.apply").spec.input_schema["properties"]["arguments"]
    assert arguments["additionalProperties"] is False
    assert "projects.create" in registry.get("project.project.change.apply").spec.input_schema["properties"]["operation"]["enum"]
    result = registry.get("project.project.change.apply").spec.output_schema["properties"]["data"]
    assert "description" in result
    assert "type" not in result


def test_project_search_scope_is_derived_for_direct_capability_consumers(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        project_reviewed,
        "build_access_scope",
        lambda user: {"user_gid": user["gid"], "team_gids": ["team-1"], "project_gids": ["project-1"], "is_admin": False},
    )
    monkeypatch.setattr(
        project_reviewed.project_outcome_port,
        "invoke",
        lambda capability_id, payload, context: captured.update({"capability_id": capability_id, "payload": payload}) or {"success": True, "data": []},
    )

    handler = project_reviewed._handler("project.project.read")
    result = handler({"operation": "projects.search", "arguments": {}}, type("Context", (), {"user_gid": "u1", "team_gid": "team-1", "active_roles": ()})())

    assert result["data"]["data"] == []
    assert captured["payload"]["arguments"]["scope"] == {
        "user_gid": "u1", "team_gids": ["team-1"], "project_gids": ["project-1"], "is_admin": False,
    }


def test_craft_unconstrained_transport_leaves_do_not_become_empty_objects():
    version_gid = OUTPUT_SCHEMAS["craft.bop.version.create"]["properties"]["version_gid"]
    assert "Provider-validated" in version_gid["description"]
    assert "type" not in version_gid


def test_craft_provider_validated_array_items_remain_open_transport_values():
    command = INPUT_SCHEMAS["craft.bop.draft.change.preview"]["properties"]["commands"]["items"]
    assert "Provider-validated" in command["description"]
    assert "type" not in command


def test_craft_execution_structure_contract_declares_published_timestamp():
    for capability_id in (
        "craft.bop.execution_structure.get",
        "craft.bop.execution_structure.preview",
    ):
        schema = OUTPUT_SCHEMAS[capability_id]
        assert "published_at" in schema["properties"]
        assert "published_at" in schema["required"]

from __future__ import annotations

from backend.capabilities.registry_next import CapabilityRegistry
from backend.capabilities.validation_next import validate_payload


def test_structural_base_capabilities_are_registered_with_closed_contracts():
    from backend.base.web_atomic import register_atomic_web_capabilities

    registry = CapabilityRegistry()
    register_atomic_web_capabilities(registry)
    expected = {
        "base.organization.team.directory.list": ({}, {"teams": []}),
        "base.team.directory.list": ({}, {"success": True, "data": []}),
        "base.self_annotation.batch.get": ({"item_gids": ["item_1"]}, {"items": []}),
        "base.identity.admin_user.list": ({}, {"success": True, "data": []}),
        "base.identity.role.assign.atomic": (
            {"user_gid": "user_1", "new_role": "member", "external_subtype": None},
            {"success": True, "data": {"gid": "user_1", "name": "", "email": "", "avatar_url": "", "system_role": "member", "org_role": "member", "external_subtype": None, "team_id": None, "is_active": True, "created_at": ""}},
        ),
    }
    for capability_id, (payload, result) in expected.items():
        item = registry.get(capability_id)
        assert item.spec.owner == "base"
        validate_payload(dict(item.spec.input_schema), payload)
        validate_payload(dict(item.spec.output_schema), result)
        try:
            validate_payload(dict(item.spec.input_schema), {**payload, "unexpected": True})
        except ValueError:
            pass
        else:
            raise AssertionError(f"{capability_id} input accepted an unknown field")
    role = registry.get("base.identity.role.assign.atomic")
    assert role.descriptor.consistency_policy == "strong"
    assert role.descriptor.transaction_policy["mode"] == "single_transaction"
    assert getattr(role.handler, "__capability_transactional__", False) is True


def test_plugins_remain_explicitly_unresolved_without_marketplace_lifecycle_proof():
    from backend.capability_v2.atomic_web_contracts import ROUTE_CAPABILITIES, UNSAFE_REASONS

    for key in (("POST", "/api/plugin/install"), ("DELETE", "/api/plugin/uninstall/{dynamic}")):
        assert key not in ROUTE_CAPABILITIES
        assert "signed" in UNSAFE_REASONS[key] or "lifecycle" in UNSAFE_REASONS[key]

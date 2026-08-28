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


def test_plugins_register_signed_lifecycle_contracts_without_a_url_fallback():
    from backend.capability_v2.atomic_web_contracts import ROUTE_CAPABILITIES, UNSAFE_REASONS

    assert ("POST", "/api/plugin/install") in ROUTE_CAPABILITIES
    assert ("DELETE", "/api/plugin/uninstall/{dynamic}") in ROUTE_CAPABILITIES
    assert ("POST", "/api/plugin/install") not in UNSAFE_REASONS
    assert ("DELETE", "/api/plugin/uninstall/{dynamic}") not in UNSAFE_REASONS


def test_saved_view_capabilities_register_closed_contracts_and_strong_writes():
    from backend.base.web_atomic import register_atomic_web_capabilities

    registry = CapabilityRegistry()
    register_atomic_web_capabilities(registry)
    expected = {
        "base.saved_view.search": {"module": "", "list_gid": None},
        "base.saved_view.create": {
            "name": "Open", "module": "", "list_gid": None, "config": {
                "columns": [{"key": "field_1", "visible": True, "order": 0, "width": 120}],
                "filters": [{"id": "filter_1", "field": "field_1", "op": "eq", "value": "open"}],
                "filterMode": "and", "sorts": [{"field": "field_1", "dir": "asc"}],
                "groupBy": None, "viewType": "grid", "treeParentField": None,
            }, "share_scope": "private", "idempotency_key": "idem-1",
        },
        "base.saved_view.update": {
            "view_gid": "view_1", "expected_revision": 1, "name": "Open", "config": {
                "columns": [{"key": "field_1", "visible": True, "order": 0, "width": 120}],
                "filters": [{"id": "filter_1", "field": "field_1", "op": "eq", "value": "open"}],
                "filterMode": "and", "sorts": [{"field": "field_1", "dir": "asc"}],
                "groupBy": None, "viewType": "grid", "treeParentField": None,
            }, "idempotency_key": "idem-2",
        },
        "base.saved_view.copy": {"view_gid": "view_1", "name": "Copy", "idempotency_key": "idem-3"},
        "base.saved_view.delete": {"view_gid": "view_1", "expected_revision": 2, "idempotency_key": "idem-4"},
    }
    for capability_id, payload in expected.items():
        item = registry.get(capability_id)
        assert item.spec.owner == "base"
        validate_payload(dict(item.spec.input_schema), payload)
        with __import__("pytest").raises(ValueError, match="unknown field"):
            validate_payload(dict(item.spec.input_schema), {**payload, "unexpected": True})
    for capability_id in set(expected) - {"base.saved_view.search"}:
        item = registry.get(capability_id)
        assert item.descriptor.consistency_policy == "strong"
        assert item.descriptor.transaction_policy["mode"] == "single_transaction"
        assert getattr(item.handler, "__capability_transactional__", False) is True


def test_saved_view_gateway_actor_preserves_team_identity():
    from backend.base.web_atomic import _actor

    context = type("Context", (), {"user_gid": "user_1", "team_gid": "team_1", "active_roles": ("member",)})()

    assert _actor(context)["team_gids"] == ["team_1"]


def test_annotation_and_identity_capabilities_use_closed_contracts_and_strong_confirmed_write():
    from backend.base.web_atomic import register_atomic_web_capabilities

    registry = CapabilityRegistry()
    register_atomic_web_capabilities(registry)
    change = registry.get("base.self_annotation.change.apply")
    assert change.descriptor.consistency_policy == "strong"
    assert change.descriptor.confirmation_policy == "user"
    assert getattr(change.handler, "__capability_transactional__", False) is True
    for capability_id, payload in {
        "base.self_annotation.record.get": {"item_gid": "item_1"},
        "base.self_annotation.search": {"limit": 200, "status": None},
        "base.identity.session.profile.get": {},
    }.items():
        item = registry.get(capability_id)
        validate_payload(dict(item.spec.input_schema), payload)
        with __import__("pytest").raises(ValueError, match="unknown field"):
            validate_payload(dict(item.spec.input_schema), {**payload, "unexpected": True})

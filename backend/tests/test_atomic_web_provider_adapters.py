from __future__ import annotations

from backend.capabilities.models_next import CapabilityContext


CTX = CapabilityContext(
    user_gid="usr_1",
    team_gid="team_1",
    active_roles=("super_admin",),
    permissions=("base.read", "base.write", "integration.read", "integration.write", "craft.write"),
)


def test_base_adapter_invokes_the_exact_bound_handler(monkeypatch):
    from backend.base import web_atomic

    seen = {}

    def fake(*, user_gid, module, list_gid):
        seen.update(user_gid=user_gid, module=module, list_gid=list_gid)
        return {"success": True, "data": []}

    monkeypatch.setitem(web_atomic.HANDLERS, "base.saved_view.list", fake)
    result = web_atomic.invoke_atomic("base.saved_view.list", {"module": "task", "list_gid": "list_1"}, CTX)
    assert seen == {"user_gid": "usr_1", "module": "task", "list_gid": "list_1"}
    assert result == {"success": True, "data": []}


def test_integration_adapter_propagates_provider_errors(monkeypatch):
    from plugins.integration.integration_backend.capabilities import web_atomic

    def fail(**_kwargs):
        raise RuntimeError("connector failed")

    monkeypatch.setitem(web_atomic.HANDLERS, "integration.datasource.connection.test", fail)
    try:
        web_atomic.invoke_atomic("integration.datasource.connection.test", {"datasource_gid": "ds_1"}, CTX)
    except RuntimeError as exc:
        assert str(exc) == "connector failed"
    else:
        raise AssertionError("provider error was swallowed")


def test_craft_write_delegates_once_without_rest_fallback(monkeypatch):
    from plugins.craft.craft_backend.capabilities import web_atomic
    from backend.capability_v2.provider_contracts import CapabilityOutput

    calls = []

    def update(payload, context):
        calls.append((payload, context.user_gid))
        return CapabilityOutput(data={"success": True})

    monkeypatch.setattr(web_atomic, "change_rule_library", update)
    result = web_atomic.invoke_atomic("craft.rule.definition.update", {"gid": "rule_1", "changes_json": '{"name":"R"}'}, CTX)
    assert calls == [({"operation": "update", "gid": "rule_1", "record": {"name": "R"}}, "usr_1")]
    assert result == {"success": True}

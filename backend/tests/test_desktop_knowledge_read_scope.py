from types import SimpleNamespace

from plugins.knowledge.knowledge_backend.application.outcomes import KnowledgeOutcomes


def test_knowledge_list_and_detail_use_authenticated_context_not_payload_identity():
    calls = []

    class Repository:
        def item_list(self, arguments, user_gid, tenant_gid, *, permissions, active_roles):
            calls.append(("list", arguments, user_gid, tenant_gid, permissions, active_roles))
            return [{"gid": "k1", "title": "Visible"}]

        def item_get(self, gid, user_gid, tenant_gid, *, permissions, active_roles):
            calls.append(("get", gid, user_gid, tenant_gid, permissions, active_roles))
            return {"gid": gid, "title": "Visible"}

    context = SimpleNamespace(
        user_gid="u1", team_gid="t1", permissions=("knowledge.read",), active_roles=("member",),
    )
    outcomes = KnowledgeOutcomes(repository=Repository())
    listed = outcomes.invoke("knowledge.hub.read", {
        "operation": "items.list", "arguments": {"limit": 100, "show_hidden": False},
    }, context)
    detail = outcomes.invoke("knowledge.hub.read", {
        "operation": "items.get", "arguments": {"gid": "k1"},
    }, context)

    assert listed == {"items": [{"gid": "k1", "title": "Visible"}]}
    assert detail == {"gid": "k1", "title": "Visible"}
    assert calls == [
        ("list", {"limit": 100, "show_hidden": False}, "u1", "t1", ("knowledge.read",), ("member",)),
        ("get", "k1", "u1", "t1", ("knowledge.read",), ("member",)),
    ]

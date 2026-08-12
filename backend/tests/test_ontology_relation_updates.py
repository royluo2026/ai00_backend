import asyncio
from unittest.mock import AsyncMock

from plugins.craft.craft_backend.routers import ontology


def test_update_relation_creates_a_governed_proposal(monkeypatch):
    propose = AsyncMock(return_value={"proposal_gid": "proposal-1"})
    monkeypatch.setattr(ontology, "_propose", propose)
    principal = object()

    result = asyncio.run(
        ontology.update_relation(
            "relation-1",
            {"label_zh": "人员"},
            {"gid": "user-1"},
            principal,
        )
    )

    assert result == {"proposal_gid": "proposal-1"}
    propose.assert_awaited_once_with(
        {
            "change_type": "relation.update",
            "stable_gid": "relation-1",
            "after": {"label_zh": "人员"},
        },
        {"gid": "user-1"},
        principal,
    )


def test_legacy_seed_route_is_retained_but_no_seed_rows_are_embedded():
    paths = {route.path for route in ontology.router.routes}
    assert "/api/ontology/seed" in paths
    assert not hasattr(ontology, "_SEED_RELATIONS")


def test_compatibility_router_has_no_database_connection():
    assert not hasattr(ontology, "get_conn")

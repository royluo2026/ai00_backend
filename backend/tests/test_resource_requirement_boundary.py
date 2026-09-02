from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timezone
from types import SimpleNamespace

from pydantic_core import PydanticUndefined


def test_resource_requirement_compatibility_invokes_the_atomic_capability(monkeypatch):
    from plugins.craft.craft_backend.routers import resource_requirements

    captured = {}

    async def invoke(_gateway, envelope):
        captured["envelope"] = envelope
        return SimpleNamespace(ok=True, data={"items": [], "next_cursor": None}, error=None)

    monkeypatch.setattr(resource_requirements, "invoke_compatibility", invoke)
    request = SimpleNamespace(headers={"X-Request-ID": "request-1"})
    principal = SimpleNamespace(model_dump=lambda: {
        "user_id": "user-1", "authentication_method": "test",
        "authenticated_at": datetime.now(timezone.utc),
    })
    gateway = SimpleNamespace(catalog_release="release-1")

    result = asyncio.run(
        resource_requirements._invoke_resource(
            request, {"gid": "user-1", "system_role": "super_admin"}, principal, gateway,
            "craft.resource_requirement.search", {"resource_type": "socket", "page_size": 50},
        )
    )

    assert result == {"items": [], "next_cursor": None}
    assert captured["envelope"].capability_id == "craft.resource_requirement.search"
    assert captured["envelope"].payload == {"resource_type": "socket", "page_size": 50}


def test_resource_requirement_router_has_no_database_connection():
    from plugins.craft.craft_backend.routers import resource_requirements

    assert not hasattr(resource_requirements, "get_conn")


def test_resource_staging_route_requires_a_bop_version_selector():
    from plugins.craft.craft_backend.routers import resource_requirements

    parameter = inspect.signature(resource_requirements.list_resource_staging).parameters["version_gid"]
    assert parameter.default.default is PydanticUndefined


def test_bop_entry_link_provider_validates_standard_resource_links(monkeypatch):
    from plugins.craft.craft_backend.capabilities import bop_entry_link_change

    calls = []

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, _params): calls.append(" ".join(sql.split()))
        def fetchone(self):
            if "bop_entries" in calls[-1]:
                return {"version_gid": "version-1"}
            if "bop_versions" in calls[-1]:
                return {"status": "active"}
            return None

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()
        def commit(self): return None

    validated = []
    monkeypatch.setattr(bop_entry_link_change, "get_craft_conn", lambda: Connection())
    monkeypatch.setattr(bop_entry_link_change, "_check_line_editable", lambda *_args: None)
    monkeypatch.setattr(bop_entry_link_change, "_log_entry_op", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bop_entry_link_change, "next_gid", lambda: "link-1")
    monkeypatch.setattr(
        bop_entry_link_change,
        "validate_resource_link",
        lambda link_type, entity_gid, _cur: validated.append((link_type, entity_gid)),
        raising=False,
    )

    result = bop_entry_link_change.apply_bop_entry_link_change(
        {"operation": "attach", "entry_gid": "entry-1", "link_type": "resource_tool", "entity_gid": "resource-1"},
        type("Context", (), {"user_gid": "user-1", "active_roles": ("super_admin",)})(),
    )

    assert result == {"data": {"gid": "link-1"}}
    assert validated == [("resource_tool", "resource-1")]

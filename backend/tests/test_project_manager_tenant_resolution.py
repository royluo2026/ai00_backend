from __future__ import annotations

import asyncio
from types import SimpleNamespace

from backend.base.org_management_capabilities import _validated_project_tenant


class _DomainClient:
    def __init__(self, result):
        self.result = result

    async def invoke(self, *_args, **_kwargs):
        return self.result


def test_manager_state_uses_the_validated_projects_owning_tenant() -> None:
    context = SimpleNamespace(team_gid="admin-team")
    validation = SimpleNamespace(ok=True, data={"data": {"team_id": "project-team"}}, error=None)

    assert asyncio.run(
        _validated_project_tenant(context, "project-1", validation=validation)
    ) == "project-team"

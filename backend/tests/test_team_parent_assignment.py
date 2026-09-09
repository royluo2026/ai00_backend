from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.base import desktop_actions
from backend.routers import teams


class ParentCursor:
    def __init__(self, parents: dict[str, str | None]):
        self.parents = parents
        self.current = None

    def execute(self, _sql, params):
        self.current = str(params[0])

    def fetchone(self):
        if self.current not in self.parents:
            return None
        return {"parent_team_gid": self.parents[self.current]}


def test_parent_validation_accepts_ancestor_and_rejects_descendant() -> None:
    cursor = ParentCursor({"root": None, "child": "root", "grandchild": "child"})
    teams._validate_parent_team_gid(cursor, "child", "root")

    with pytest.raises(HTTPException) as exc:
        teams._validate_parent_team_gid(cursor, "child", "grandchild")
    assert exc.value.status_code == 400
    assert "下级" in exc.value.detail


def test_team_update_capability_accepts_nullable_parent() -> None:
    definition = next(item for item in desktop_actions.DEFINITIONS if item[0] == "base.team.update")
    schema = definition[2]["properties"]["changes"]["properties"]["parent_team_gid"]
    assert schema["type"] == ["string", "null"]
    assert teams.UpdateTeamBody(parent_team_gid=None).model_fields_set == {"parent_team_gid"}

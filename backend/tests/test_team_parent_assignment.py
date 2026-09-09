from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.base import desktop_actions
from backend.base import structural_web
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


class RecordingCursor:
    def __init__(self):
        self.statements: list[tuple[str, tuple | list | None]] = []
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.statements.append((sql, params))

    def fetchall(self):
        return []

    def fetchone(self):
        return None


class RecordingConnection:
    def __init__(self, cursor: RecordingCursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self._cursor

    def commit(self):
        return None


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


def test_directory_capabilities_read_only_active_bounded_rows(monkeypatch) -> None:
    cursor = RecordingCursor()
    connection = RecordingConnection(cursor)
    monkeypatch.setattr(structural_web, "get_conn", lambda: connection)

    structural_web.list_organization_teams(actor={})
    structural_web.list_admin_users(actor={"system_role": "super_admin"})

    sql = "\n".join(statement for statement, _params in cursor.statements)
    assert sql.count("is_active=TRUE") == 2
    assert sql.count("LIMIT 1000") == 2


def test_team_soft_delete_and_reactivation_use_existing_is_active_column(monkeypatch) -> None:
    cursor = RecordingCursor()
    connection = RecordingConnection(cursor)
    monkeypatch.setattr(teams, "get_conn", lambda: connection)

    teams.delete_team("team-1", _={})
    teams.add_team_member("team-1", teams.AddMemberBody(user_gid="user-1"), current_user={})

    sql = "\n".join(statement for statement, _params in cursor.statements)
    assert "deleted_at" not in sql
    assert "SET is_active = FALSE" in sql
    assert "SET team_id = %s, is_active = TRUE" in sql

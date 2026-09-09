from __future__ import annotations

from backend.base.bop_edit_authorization import check_bop_edit, get_bop_edit_scope


class Cursor:
    def __init__(self, rows): self.rows, self.index = rows, 0
    def execute(self, *_args): pass
    def fetchone(self):
        value = self.rows[self.index] if self.index < len(self.rows) else None
        self.index += 1
        return value
    def fetchall(self):
        value = self.rows[self.index] if self.index < len(self.rows) else []
        self.index += 1
        return value or []
    def __enter__(self): return self
    def __exit__(self, *_args): pass


class Connection:
    def __init__(self, rows): self.rows = rows
    def cursor(self): return Cursor(self.rows)


class Context:
    def __init__(self, rows): self.connection = Connection(rows)
    def __enter__(self): return self.connection
    def __exit__(self, *_args): pass


def test_super_is_global_without_storage(monkeypatch) -> None:
    monkeypatch.setattr("backend.base.bop_edit_authorization.get_conn", lambda: (_ for _ in ()).throw(AssertionError()))
    assert check_bop_edit(tenant_gid="t", user_gid="u", active_roles=("super_admin",), project_gid="p", line_gid=None)["scope"] == "global"


def test_member_and_team_admin_are_not_project_editors(monkeypatch) -> None:
    monkeypatch.setattr("backend.base.bop_edit_authorization.get_conn", lambda: Context([None, None, None]))
    for roles in (("member",), ("team_admin",)):
        assert not check_bop_edit(tenant_gid="t", user_gid="u", active_roles=roles,
                                  project_gid="p", line_gid="l")["allowed"]


def test_managed_project_manager_and_line_leader_are_scoped(monkeypatch) -> None:
    monkeypatch.setattr("backend.base.bop_edit_authorization.get_conn", lambda: Context([{"managed": 1}, {"1": 1}]))
    assert check_bop_edit(tenant_gid="t", user_gid="u", active_roles=("member",), project_gid="p", line_gid=None)["scope"] == "project"
    monkeypatch.setattr("backend.base.bop_edit_authorization.get_conn", lambda: Context([{"managed": 1}, None, [{"bop_line_gid": "l"}]]))
    assert check_bop_edit(tenant_gid="t", user_gid="u", active_roles=("member",), project_gid="p", line_gid="l")["scope"] == "line"


def test_edit_scope_returns_only_assigned_lines_for_ordinary_member(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.base.bop_edit_authorization.get_conn",
        lambda: Context([{"managed": 1}, None, [{"bop_line_gid": "line-own"}]]),
    )
    result = get_bop_edit_scope(
        tenant_gid="t", user_gid="u", active_roles=("member",),
        project_gid="p", line_gids=("line-own", "line-other"),
    )
    assert result == {
        "project_wide": False,
        "editable_line_gids": ("line-own",),
        "reason": "line_leader",
    }


def test_edit_scope_is_project_wide_for_project_manager(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.base.bop_edit_authorization.get_conn",
        lambda: Context([{"managed": 1}, {"1": 1}]),
    )
    result = get_bop_edit_scope(
        tenant_gid="t", user_gid="u", active_roles=("member",),
        project_gid="p", line_gids=("line-a", "line-b"),
    )
    assert result["project_wide"] is True
    assert result["reason"] == "project_manager"


from contextlib import contextmanager

from plugins.simulation.simulation_backend.data import workspace_repository as module


class Cursor:
    def __init__(self, responses):
        self.responses = list(responses)
        self.executed = []
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=()):
        self.executed.append((" ".join(sql.split()), tuple(params)))

    def fetchone(self):
        return self.responses.pop(0) if self.responses else None

    def fetchall(self):
        return self.responses.pop(0) if self.responses else []


def connection(cursor):
    @contextmanager
    def connect():
        class Connection:
            def cursor(self):
                return cursor

        yield Connection()

    return connect


def test_search_visibility_is_owner_or_shared_not_current_tenant(monkeypatch):
    cursor = Cursor([[{
        "workspace_gid": 10, "version_gid": 11, "owner_gid": 30,
        "name": "shared", "visibility": "shared", "row_version": 1,
    }], []])
    monkeypatch.setattr(module, "get_simulation_conn", connection(cursor))

    result = module.WorkspaceRepository().search(
        tenant_gid="200", owner_gid="30", offset=0, page_size=50,
    )

    sql, params = cursor.executed[0]
    assert "w.tenant_gid=%s" not in sql
    assert "(w.owner_gid=%s OR w.visibility='shared')" in sql
    assert params == ("30", 51, 0)
    assert result["items"][0]["workspace_gid"] == "10"


def test_get_uses_workspace_source_tenant_for_owned_children(monkeypatch):
    cursor = Cursor([{
        "workspace_gid": 10, "version_gid": 11, "workspace_tenant_gid": 100,
        "owner_gid": 30, "name": "mine", "visibility": "private", "row_version": 1,
    }, [], [], []])
    monkeypatch.setattr(module, "get_simulation_conn", connection(cursor))

    result = module.WorkspaceRepository().get("10", tenant_gid="200", owner_gid="30")

    assert result["workspace_gid"] == "10"
    assert "workspace_tenant_gid" not in result
    assert "w.tenant_gid=%s" not in cursor.executed[0][0]
    assert cursor.executed[2][1] == ("10", "100")
    assert cursor.executed[3][1] == ("10", "100")


def test_owner_update_uses_workspace_source_tenant_after_org_change(monkeypatch):
    cursor = Cursor([{"row_version": 1, "status": "active", "tenant_gid": 100}, None])
    monkeypatch.setattr(module, "get_simulation_conn", connection(cursor))

    result = module.WorkspaceRepository().mutate(
        workspace_gid="10", tenant_gid="200", owner_gid="30", expected_row_version=1,
        idempotency_key="update-1", operation="update_workspace",
        values={"name": "mine", "review_type": "other", "version_label": "V1",
                "status": "active", "visibility": "private", "primary_project_gid": None,
                "project_gids": []},
    )

    owner_sql, owner_params = cursor.executed[0]
    assert "tenant_gid=%s" not in owner_sql
    assert owner_params == ("10", "30")
    assert result["row_version"] == 2

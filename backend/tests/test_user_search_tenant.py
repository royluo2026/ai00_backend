"""A collaborator picker only exposes active members of the caller's team."""
from unittest.mock import patch

from backend.services.user_service import search_users


class Cursor:
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def execute(self, sql, params):
        self.sql, self.params = sql, params
    def fetchall(self): return []


class Connection:
    def __init__(self, cursor): self.cursor_value = cursor
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def cursor(self): return self.cursor_value


def test_collaborator_search_is_limited_to_the_active_tenant():
    cursor = Cursor()
    with patch("backend.services.user_service.get_conn", return_value=Connection(cursor)):
        assert search_users("王", 10, team_gid="team_1") == []
    assert "team_id = %s" in cursor.sql
    assert cursor.params == ("team_1", "%王%", "%王%", 10)

from __future__ import annotations

import json
from datetime import datetime

from backend.platform_sdk import project_access


class _Cursor:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _sql, _params=None):
        return None

    def fetchall(self):
        return [{
            "gid": "membership-1",
            "project_gid": "project-1",
            "user_gid": "user-1",
            "name": "User",
            "email": "user@example.com",
            "avatar_url": "",
            "role": "member",
            "scope_gid": None,
            "scope_type": "project",
            "created_at": datetime(2026, 9, 9, 10, 0, 0),
        }]


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return _Cursor()


def test_all_project_memberships_are_json_serializable(monkeypatch) -> None:
    """A DB datetime must not make project.member.read fail in the Gateway."""
    monkeypatch.setattr(project_access, "get_conn", lambda: _Connection())

    rows = project_access.list_all_project_memberships()

    assert rows[0]["created_at"] == "2026-09-09T10:00:00"
    json.dumps(rows)

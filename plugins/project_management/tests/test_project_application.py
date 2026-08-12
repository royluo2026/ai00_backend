from __future__ import annotations

import pytest

from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError,
    CapabilityContext,
)
from plugins.project_management.project_management_backend.application.service import (
    ProjectManagementApplication,
)


CONTEXT = CapabilityContext(user_gid="user-1", team_gid="team-1")


class InMemoryItemEntryRepository:
    def __init__(self):
        self.entries = {
            ("task", "task-1"): [
                {
                    "gid": "entry-gid-1",
                    "id": "entry-1",
                    "item_type": "task",
                    "item_gid": "task-1",
                    "parent_id": None,
                    "section": "detail",
                    "author": "human",
                    "author_name": "Ada",
                    "author_gid": "user-1",
                    "content": "Initial",
                    "resolved": 0,
                    "sort_order": 1,
                    "read_by_human": 1,
                    "ai_status": "unread",
                    "created_at": "2026-08-12T00:00:00",
                }
            ]
        }
        self.list_owners = {"list-1": "user-1", "list-2": "user-2"}
        self.change_logs = [
            {
                "gid": "change-1",
                "item_type": "task",
                "item_gid": "task-1",
                "list_gid": "list-1",
                "changed_by": "user-2",
                "changed_at": "2026-08-12T01:00:00",
                "field_name": "title",
                "old_value": "Old",
                "new_value": "New",
            },
            {
                "gid": "change-2",
                "item_type": "task",
                "item_gid": "task-1",
                "list_gid": "list-1",
                "changed_by": "user-1",
                "changed_at": "2026-08-12T00:00:00",
                "field_name": "status",
                "old_value": "todo",
                "new_value": "done",
            },
        ]

    def list_item_entries(self, item_type, item_gid):
        return list(self.entries.get((item_type, item_gid), []))

    def replace_item_entries(self, item_type, item_gid, entries):
        self.entries[(item_type, item_gid)] = list(entries)

    def delete_item_entries(self, item_type, item_gid):
        self.entries.pop((item_type, item_gid), None)

    def get_list_owner(self, list_gid):
        return self.list_owners.get(list_gid)

    def get_item_list_owner(self, item_type, item_gid):
        matching = next(
            (
                row
                for row in self.change_logs
                if row["item_type"] == item_type and row["item_gid"] == item_gid
            ),
            None,
        )
        return self.list_owners.get(matching["list_gid"]) if matching else None

    def list_change_logs_by_list(self, list_gid, limit, offset):
        rows = [row for row in self.change_logs if row["list_gid"] == list_gid]
        return rows[offset : offset + limit]

    def list_change_logs_by_item(self, item_type, item_gid, changed_by, limit, offset):
        rows = [
            row
            for row in self.change_logs
            if row["item_type"] == item_type
            and row["item_gid"] == item_gid
            and (changed_by is None or row["changed_by"] == changed_by)
        ]
        return rows[offset : offset + limit]


def _application():
    generated = iter(("entry-gid-2", "entry-gid-3"))
    return ProjectManagementApplication(
        repository=InMemoryItemEntryRepository(),
        next_id=lambda: next(generated),
    )


def test_item_entry_read_returns_the_legacy_stable_shape():
    result = _application().invoke(
        "project.list.read",
        {
            "operation": "item_entries.get",
            "arguments": {"item_type": "task", "item_gid": "task-1"},
        },
        CONTEXT,
    )

    assert result == {
        "entries": [
            {
                "id": "entry-1",
                "gid": "entry-gid-1",
                "parent_id": None,
                "section": "detail",
                "author": "human",
                "author_name": "Ada",
                "author_gid": "user-1",
                "content": "Initial",
                "resolved": False,
                "sort_order": 1.0,
                "read_by_human": True,
                "ai_status": "unread",
                "created_at": "2026-08-12T00:00:00",
            }
        ]
    }


def test_item_entry_replace_and_delete_are_owned_by_project_application():
    application = _application()
    replaced = application.invoke(
        "project.list.change.apply",
        {
            "operation": "item_entries.replace",
            "arguments": {
                "item_type": "task",
                "item_gid": "task-1",
                "entries": [{"id": "entry-2", "content": "Updated"}],
            },
        },
        CONTEXT,
    )

    assert replaced == {
        "success": True,
        "count": 1,
        "entries": [{"id": "entry-2", "content": "Updated", "gid": "entry-gid-2"}],
    }
    assert application.invoke(
        "project.list.change.apply",
        {
            "operation": "item_entries.delete",
            "arguments": {"item_type": "task", "item_gid": "task-1"},
        },
        CONTEXT,
    ) == {"success": True}
    assert application.invoke(
        "project.list.read",
        {
            "operation": "item_entries.get",
            "arguments": {"item_type": "task", "item_gid": "task-1"},
        },
        CONTEXT,
    ) == {"entries": []}


def test_project_application_rejects_an_unknown_or_cross_capability_operation():
    with pytest.raises(CapabilityBusinessError, match="not supported") as error:
        _application().invoke(
            "project.list.read",
            {"operation": "item_entries.delete", "arguments": {}},
            CONTEXT,
        )

    assert error.value.code == "operation_not_supported"


def test_change_log_read_preserves_owner_and_member_visibility():
    application = _application()

    assert len(
        application.invoke(
            "project.change_log.read",
            {
                "operation": "change_logs.search",
                "arguments": {"list_gid": "list-1", "limit": 100, "offset": 0},
            },
            CONTEXT,
        )
    ) == 2
    member_context = CapabilityContext(user_gid="user-2", team_gid="team-1")
    assert application.invoke(
        "project.change_log.read",
        {
            "operation": "change_logs.search",
            "arguments": {
                "item_type": "task",
                "item_gid": "task-1",
                "limit": 100,
                "offset": 0,
            },
        },
        member_context,
    ) == [
        {
            "gid": "change-1",
            "item_type": "task",
            "item_gid": "task-1",
            "list_gid": "list-1",
            "changed_by": "user-2",
            "changed_at": "2026-08-12T01:00:00",
            "field_name": "title",
            "old_value": "Old",
            "new_value": "New",
        }
    ]


def test_change_log_list_read_rejects_non_owner_but_trusted_super_admin_can_read():
    application = _application()
    with pytest.raises(CapabilityBusinessError, match="owner") as error:
        application.invoke(
            "project.change_log.read",
            {
                "operation": "change_logs.search",
                "arguments": {"list_gid": "list-1", "limit": 100, "offset": 0},
            },
            CapabilityContext(user_gid="user-2", team_gid="team-1"),
        )
    assert error.value.code == "forbidden"

    result = application.invoke(
        "project.change_log.read",
        {
            "operation": "change_logs.search",
            "arguments": {"list_gid": "list-1", "limit": 100, "offset": 0},
        },
        CapabilityContext(
            user_gid="admin-1", team_gid="team-1", active_roles=("super_admin",)
        ),
    )
    assert len(result) == 2

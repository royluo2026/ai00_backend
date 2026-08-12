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

    def list_item_entries(self, item_type, item_gid):
        return list(self.entries.get((item_type, item_gid), []))

    def replace_item_entries(self, item_type, item_gid, entries):
        self.entries[(item_type, item_gid)] = list(entries)

    def delete_item_entries(self, item_type, item_gid):
        self.entries.pop((item_type, item_gid), None)


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

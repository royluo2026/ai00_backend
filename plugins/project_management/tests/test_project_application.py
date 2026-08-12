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
        self.sessions = {
            "session-1": {
                "gid": "session-1",
                "section_gid": "section-1",
                "owner_gid": "user-1",
                "status": "active",
                "participants": ["user-1"],
                "meta": {"cursor": 3},
                "created_at": "2026-08-12T02:00:00",
                "ended_at": None,
            }
        }
        self.share_links = {}
        self.list_access = {("list-1", "user-1", "team-1"): "write"}
        self.permission_requests = {}
        self.list_shares = {}
        self.item_shares = {}

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

    def list_collaboration_sessions(self, section_gid):
        return [
            row
            for row in self.sessions.values()
            if (row["section_gid"] == section_gid if section_gid else row["status"] == "active")
        ]

    def get_collaboration_session(self, gid):
        return self.sessions.get(gid)

    def create_collaboration_session(self, gid, section_gid, owner_gid):
        self.sessions[gid] = {
            "gid": gid,
            "section_gid": section_gid,
            "owner_gid": owner_gid,
            "status": "active",
            "participants": [owner_gid],
            "meta": {},
            "created_at": "2026-08-12T03:00:00",
            "ended_at": None,
        }

    def join_collaboration_session(self, gid, participant_gid):
        session = self.sessions.get(gid)
        if session and session["status"] == "active" and participant_gid not in session["participants"]:
            session["participants"].append(participant_gid)

    def end_collaboration_session(self, gid, owner_gid):
        session = self.sessions.get(gid)
        if not session or session["owner_gid"] != owner_gid:
            return False
        session["status"] = "ended"
        session["ended_at"] = "2026-08-12T04:00:00"
        return True

    def create_share_link(self, token, values):
        self.share_links[token] = {"token": token, **values}
        return self.share_links[token]

    def resolve_share_link(self, token):
        return self.share_links.get(token)

    def get_list_access(self, list_gid, user_gid, team_gid):
        return self.list_access.get((list_gid, user_gid, team_gid), "none")

    def delete_share_link(self, token, user_gid, is_super):
        link = self.share_links.get(token)
        if not link:
            return "not_found"
        if link["created_by"] != user_gid and not is_super:
            return "forbidden"
        del self.share_links[token]
        return "deleted"

    def create_permission_request(self, gid, values):
        row = {"gid": gid, **values, "status": "pending"}
        self.permission_requests[gid] = row
        return row

    def list_permission_requests(self, target_gid, status_filter):
        return [row for row in self.permission_requests.values() if (not target_gid or row["target_gid"] == target_gid) and (not status_filter or row["status"] == status_filter)]

    def decide_permission_request(self, gid, responder_gid, decision):
        row = self.permission_requests.get(gid)
        if not row:
            return "not_found", None
        if row["status"] != "pending":
            return "already_decided", row
        row["status"] = decision
        row["responded_by"] = responder_gid
        return "updated", row

    def is_list_owner(self, list_gid, user_gid):
        return self.list_owners.get(list_gid) == user_gid

    def list_list_shares(self, list_gid):
        return [row for row in self.list_shares.values() if row["list_gid"] == list_gid]

    def upsert_list_share(self, gid, values):
        row = {"gid": gid, **values}; self.list_shares[gid] = row; return row

    def delete_list_share(self, list_gid, gid):
        if gid in self.list_shares and self.list_shares[gid]["list_gid"] == list_gid: del self.list_shares[gid]

    def upsert_item_share(self, gid, values):
        row = {"gid": gid, **values}; self.item_shares[gid] = row; return row

    def delete_item_share(self, gid, user_gid):
        row = self.item_shares.get(gid)
        if not row: return "not_found"
        if row["shared_by"] != user_gid: return "forbidden"
        del self.item_shares[gid]; return "deleted"


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


def test_collaboration_read_returns_legacy_list_and_detail_shapes():
    application = _application()
    listed = application.invoke(
        "project.collaboration.read",
        {"operation": "collaboration.sessions.list", "arguments": {"section_gid": None}},
        CONTEXT,
    )
    detailed = application.invoke(
        "project.collaboration.read",
        {"operation": "collaboration.sessions.get", "arguments": {"gid": "session-1"}},
        CONTEXT,
    )

    assert listed == {
        "success": True,
        "data": [{
            "gid": "session-1",
            "section_gid": "section-1",
            "owner_gid": "user-1",
            "status": "active",
            "participants": ["user-1"],
            "created_at": "2026-08-12T02:00:00",
            "ended_at": None,
        }],
    }
    assert detailed["data"]["meta"] == {"cursor": 3}


def test_collaboration_create_join_and_end_preserve_members_and_owner_rule():
    application = ProjectManagementApplication(
        repository=InMemoryItemEntryRepository(), next_id=lambda: "session-2"
    )
    assert application.invoke(
        "project.collaboration.change.apply",
        {
            "operation": "collaboration.sessions.create",
            "arguments": {"section_gid": "section-2"},
        },
        CONTEXT,
    ) == {"success": True, "data": {"gid": "session-2"}}
    member = CapabilityContext(user_gid="user-2", team_gid="team-1")
    application.invoke(
        "project.collaboration.change.apply",
        {"operation": "collaboration.sessions.join", "arguments": {"gid": "session-2"}},
        member,
    )
    application.invoke(
        "project.collaboration.change.apply",
        {"operation": "collaboration.sessions.join", "arguments": {"gid": "session-2"}},
        member,
    )
    assert application.invoke(
        "project.collaboration.read",
        {"operation": "collaboration.sessions.get", "arguments": {"gid": "session-2"}},
        CONTEXT,
    )["data"]["participants"] == ["user-1", "user-2"]

    with pytest.raises(CapabilityBusinessError, match="owner") as error:
        application.invoke(
            "project.collaboration.change.apply",
            {"operation": "collaboration.sessions.end", "arguments": {"gid": "session-2"}},
            member,
        )
    assert error.value.code == "forbidden"


def test_share_link_create_resolve_and_delete_preserve_access_shape():
    application = ProjectManagementApplication(
        repository=InMemoryItemEntryRepository(), next_token=lambda: "token-1"
    )
    created = application.invoke(
        "project.sharing.change.apply",
        {
            "operation": "share_links.create",
            "arguments": {"target_type": "list", "target_gid": "list-1", "display_name": "Plan"},
        },
        CONTEXT,
    )
    assert created["token"] == "token-1"
    assert application.invoke(
        "project.sharing.read",
        {"operation": "share_links.resolve", "arguments": {"token": "token-1"}},
        CONTEXT,
    ) == {
        "target_type": "list", "target_gid": "list-1", "item_type": None,
        "display_name": "Plan", "current_permission": "write", "can_request": False,
    }
    assert application.invoke(
        "project.sharing.change.apply",
        {"operation": "share_links.delete", "arguments": {"token": "token-1"}},
        CONTEXT,
    ) == {"ok": True}


def test_share_link_delete_enforces_creator_or_trusted_super_admin():
    repository = InMemoryItemEntryRepository()
    repository.create_share_link("token-1", {"created_by": "user-1"})
    application = ProjectManagementApplication(repository=repository)
    with pytest.raises(CapabilityBusinessError, match="creator") as error:
        application.invoke(
            "project.sharing.change.apply",
            {"operation": "share_links.delete", "arguments": {"token": "token-1"}},
            CapabilityContext(user_gid="user-2", team_gid="team-1"),
        )
    assert error.value.code == "forbidden"


def test_permission_request_create_list_and_decide_return_notification_intent():
    application = ProjectManagementApplication(repository=InMemoryItemEntryRepository(), next_id=lambda: "request-1")
    created = application.invoke(
        "project.permission_request.change.apply",
        {"operation": "permission_requests.create", "arguments": {"target_type": "list", "target_gid": "list-1", "want_permission": "read", "message": "Need access"}},
        CONTEXT,
    )
    assert created["request"]["requester_gid"] == "user-1"
    assert application.invoke(
        "project.permission_request.read",
        {"operation": "permission_requests.list", "arguments": {"target_gid": "list-1", "status": "pending"}}, CONTEXT,
    )["requests"] == [created["request"]]
    decided = application.invoke(
        "project.permission_request.change.apply",
        {"operation": "permission_requests.approve", "arguments": {"gid": "request-1"}}, CONTEXT,
    )
    assert decided == {"ok": True, "notification": {"recipient_gid": "user-1", "event": "permission_approved", "target_type": "list", "target_gid": "list-1"}}
    with pytest.raises(CapabilityBusinessError) as error:
        application.invoke("project.permission_request.change.apply", {"operation": "permission_requests.reject", "arguments": {"gid": "request-1"}}, CONTEXT)
    assert error.value.code == "already_decided"


def test_direct_shares_enforce_list_owner_and_item_share_creator():
    application = ProjectManagementApplication(repository=InMemoryItemEntryRepository(), next_id=lambda: "share-1")
    created = application.invoke("project.sharing.change.apply", {"operation": "shares.list.create", "arguments": {"list_gid": "list-1", "shared_to": "user-2", "permission": "read"}}, CONTEXT)
    assert application.invoke("project.sharing.read", {"operation": "shares.list.list", "arguments": {"list_gid": "list-1"}}, CONTEXT) == {"shares": [created["share"]]}
    with pytest.raises(CapabilityBusinessError) as error:
        application.invoke("project.sharing.read", {"operation": "shares.list.list", "arguments": {"list_gid": "list-1"}}, CapabilityContext(user_gid="user-2", team_gid="team-1"))
    assert error.value.code == "forbidden"

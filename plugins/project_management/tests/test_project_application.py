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
        self.lists = {}
        self.projects = {}
        self.vehicle_models = {}
        self.task_templates = {}
        self.template_items = {}
        self.created_tasks = []
        self.approval_orders = {}
        self.workbenches = {}
        self.workbench_overrides = {}

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

    def search_lists(self, filters, scope):
        return list(self.lists.values())

    def create_list(self, gid, values):
        self.lists[gid] = {"gid": gid, "created_at": "2026-08-12", "deleted_at": None, **values}

    def get_list(self, gid):
        return self.lists.get(gid)

    def update_list(self, gid, updates):
        if gid not in self.lists: return False
        self.lists[gid].update(updates); return True

    def archive_list(self, gid):
        if gid not in self.lists: return False
        self.lists[gid]["deleted_at"] = "2026-08-12"; return True

    def retarget_list_items(self, gid, new_list_gid, item_type):
        return gid in self.lists

    def search_projects(self, filters, scope):
        return list(self.projects.values())

    def create_project(self, gid, values):
        self.projects[gid] = {"gid": gid, "created_at": "2026-08-12", "updated_at": "2026-08-12", "deleted_at": None, "archived_at": None, "is_deleted": False, "is_archived": False, "share_scope": "team", **values}

    def get_project(self, gid):
        return self.projects.get(gid)

    def update_project(self, gid, updates):
        if gid not in self.projects: return False
        self.projects[gid].update(updates); return True

    def delete_project(self, gid):
        if gid not in self.projects: return False
        self.projects[gid]["is_deleted"] = True; return True

    def list_vehicle_models(self): return list(self.vehicle_models.values())
    def create_vehicle_model(self, gid, values): self.vehicle_models[gid] = {"gid": gid, "created_at": "2026-08-12", **values}
    def update_vehicle_model(self, gid, values):
        if gid not in self.vehicle_models: return False
        self.vehicle_models[gid].update(values); return True
    def delete_vehicle_model(self, gid): return self.vehicle_models.pop(gid, None) is not None
    def list_task_templates(self): return list(self.task_templates.values())
    def create_task_template(self, gid, values): self.task_templates[gid] = {"gid": gid, "version": 1, "is_active": True, "created_at": "2026-08-12", "updated_at": "2026-08-12", **values}
    def get_task_template(self, gid):
        row = self.task_templates.get(gid)
        return ({**row, "items": [item for item in self.template_items.values() if item["template_gid"] == gid]} if row else None)
    def update_task_template(self, gid, updates):
        if gid not in self.task_templates: return False
        self.task_templates[gid].update(updates); self.task_templates[gid]["version"] += 1; return True
    def delete_task_template(self, gid): return self.task_templates.pop(gid, None) is not None
    def create_task_template_item(self, gid, values): self.template_items[gid] = {"gid": gid, **values}
    def update_task_template_item(self, gid, updates):
        if gid not in self.template_items: return False
        self.template_items[gid].update(updates); return True
    def delete_task_template_item(self, gid): return self.template_items.pop(gid, None) is not None
    def create_tasks_from_template(self, tasks): self.created_tasks.extend(tasks)
    def search_approval_orders(self, filters, scope): return list(self.approval_orders.values())
    def create_approval_order(self, gid, values): self.approval_orders[gid] = {"gid": gid, "status": "pending", "opinions": [], "created_at": "2026-08-12", "updated_at": "2026-08-12", **values}
    def get_approval_order(self, gid): return self.approval_orders.get(gid)
    def transition_approval_order(self, gid, action, actor_gid, comment):
        row = self.approval_orders.get(gid)
        expected = {"start": "pending", "approve": "in_review", "reject": "in_review", "withdraw": ("pending", "in_review")}[action]
        if not row or row["status"] not in ((expected,) if isinstance(expected, str) else expected): return None
        if action in {"start", "withdraw"} and row["applicant_gid"] != actor_gid: return None
        row["status"] = {"start": "in_review", "approve": "approved", "reject": "rejected", "withdraw": "withdrawn"}[action]
        row["opinions"].append({"actor_gid": actor_gid, "action": action, "comment": comment}); return row
    def apply_scope_upgrade(self, item_type, item_gid, target_scope): return True
    def list_workbenches(self, user_gid, team_gid):
        return ([row for row in self.workbenches.values() if row["owner_type"] == "user" and row["owner_gid"] == user_gid], [row for row in self.workbenches.values() if row["owner_type"] == "team" and row["owner_gid"] == team_gid], dict(self.workbench_overrides))
    def count_workbenches(self, owner_type, owner_gid): return sum(row["owner_type"] == owner_type and row["owner_gid"] == owner_gid for row in self.workbenches.values())
    def create_workbench(self, gid, values): self.workbenches[gid] = {"gid": gid, "created_at": "2026-08-12", "updated_at": "2026-08-12", **values}
    def get_workbench(self, gid): return self.workbenches.get(gid)
    def update_workbench(self, gid, updates):
        if gid not in self.workbenches: return False
        self.workbenches[gid].update(updates); return True
    def delete_workbench(self, gid): return self.workbenches.pop(gid, None) is not None
    def get_workbench_override(self, gid, user_gid): return self.workbench_overrides.get((gid, user_gid))
    def upsert_workbench_override(self, gid, user_gid, widgets): self.workbench_overrides[(gid, user_gid)] = {"widgets": widgets, "updated_at": "2026-08-12"}
    def delete_workbench_override(self, gid, user_gid): self.workbench_overrides.pop((gid, user_gid), None)


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


def test_project_lists_create_read_update_and_archive_under_owner_policy():
    application = ProjectManagementApplication(repository=InMemoryItemEntryRepository(), next_id=lambda: "list-1")
    created = application.invoke("project.list.change.apply", {"operation": "lists.create", "arguments": {"name": "My tasks", "visibility": "private"}}, CONTEXT)
    assert created == {"success": True, "data": {"gid": "list-1"}}
    listed = application.invoke("project.list.read", {"operation": "lists.search", "arguments": {"item_type": "task", "scope": {"user_gid": "user-1"}}}, CONTEXT)
    assert listed["data"][0]["read_scope"] == "personal"
    assert application.invoke("project.list.change.apply", {"operation": "lists.update", "arguments": {"gid": "list-1", "updates": {"name": "Renamed"}}}, CONTEXT) == {"success": True}
    with pytest.raises(CapabilityBusinessError) as error:
        application.invoke("project.list.change.apply", {"operation": "lists.delete", "arguments": {"gid": "list-1"}}, CapabilityContext(user_gid="user-2", team_gid="team-1"))
    assert error.value.code == "forbidden"
    assert application.invoke("project.list.change.apply", {"operation": "lists.delete", "arguments": {"gid": "list-1"}}, CONTEXT) == {"success": True}


def test_projects_create_read_update_delete_and_vehicle_models():
    application = ProjectManagementApplication(repository=InMemoryItemEntryRepository(), next_id=lambda: "generated-1")
    created = application.invoke("project.project.change.apply", {"operation": "projects.create", "arguments": {"project_code": "EV", "model_year": 2028, "suffix": "SOP"}}, CONTEXT)
    assert created == {"success": True, "data": {"gid": "generated-1", "name": "EV-2028-SOP"}}
    listed = application.invoke("project.project.read", {"operation": "projects.search", "arguments": {"scope": {"user_gid": "user-1"}}}, CONTEXT)
    assert listed["data"][0]["owner_gid"] == "user-1"
    assert application.invoke("project.project.change.apply", {"operation": "projects.update", "arguments": {"gid": "generated-1", "updates": {"suffix": "PRE"}}}, CONTEXT) == {"success": True}
    assert application.invoke("project.project.read", {"operation": "projects.get", "arguments": {"gid": "generated-1"}}, CONTEXT)["data"]["name"] == "EV-2028-PRE"
    assert application.invoke("project.project.change.apply", {"operation": "projects.delete", "arguments": {"gid": "generated-1"}}, CONTEXT) == {"success": True}
    model = application.invoke("project.project.change.apply", {"operation": "vehicle_models.create", "arguments": {"name": "Sedan", "brand": "AI00"}}, CONTEXT)
    assert model["data"]["name"] == "Sedan"
    assert application.invoke("project.project.read", {"operation": "vehicle_models.list", "arguments": {}}, CONTEXT)["data"][0]["brand"] == "AI00"


def test_task_template_lifecycle_and_instantiation_are_project_owned():
    ids = iter(["template-1", "item-1", "task-1"])
    application = ProjectManagementApplication(repository=InMemoryItemEntryRepository(), next_id=lambda: next(ids))
    assert application.invoke("project.task_template.change.apply", {"operation": "task_templates.create", "arguments": {"name": "Launch"}}, CONTEXT)["data"]["gid"] == "template-1"
    application.invoke("project.task_template.change.apply", {"operation": "task_templates.items.create", "arguments": {"template_gid": "template-1", "title_pattern": "Prepare {{project_name}}", "due_offset_days": 2}}, CONTEXT)
    detail = application.invoke("project.task_template.read", {"operation": "task_templates.get", "arguments": {"gid": "template-1"}}, CONTEXT)
    assert detail["data"]["items"][0]["title_pattern"] == "Prepare {{project_name}}"
    created = application.invoke("project.task_template.change.apply", {"operation": "task_templates.instantiate", "arguments": {"gid": "template-1", "project_gid": "project-1", "start_date": "2026-08-12", "title_vars": {"project_name": "P1"}}}, CONTEXT)
    assert created == {"success": True, "data": [{"gid": "task-1", "title": "Prepare P1", "due_date": "2026-08-14", "assignee_gid": None, "template_item_gid": "item-1"}], "count": 1}


def test_approval_lifecycle_is_project_owned_and_emits_notification_intent():
    application = ProjectManagementApplication(repository=InMemoryItemEntryRepository(), next_id=lambda: "approval-1")
    created = application.invoke("project.approval.change.apply", {"operation": "approval.orders.create", "arguments": {"title": "Release", "reviewer_gid": "user-2"}}, CONTEXT)
    assert created["data"]["gid"] == "approval-1"
    assert application.invoke("project.approval.change.apply", {"operation": "approval.orders.start", "arguments": {"gid": "approval-1"}}, CONTEXT) == {"success": True}
    approved = application.invoke("project.approval.change.apply", {"operation": "approval.orders.approve", "arguments": {"gid": "approval-1", "comment": "ok"}}, CapabilityContext(user_gid="user-2", team_gid="team-1", active_roles=("project_admin",)))
    assert approved["notification"]["recipient_gid"] == "user-1"


def test_workbench_lifecycle_and_member_override_are_project_owned():
    ids = iter(["workbench-1"])
    application = ProjectManagementApplication(repository=InMemoryItemEntryRepository(), next_id=lambda: next(ids))
    application.invoke("project.workbench.change.apply", {"operation": "workbenches.create", "arguments": {"name": "Mine", "widgets": [{"type": "tasks"}]}}, CONTEXT)
    listed = application.invoke("project.workbench.read", {"operation": "workbenches.list", "arguments": {}}, CONTEXT)
    assert listed["data"]["personal"][0]["name"] == "Mine"
    with pytest.raises(CapabilityBusinessError) as error:
        application.invoke("project.workbench.change.apply", {"operation": "workbenches.overrides.upsert", "arguments": {"gid": "workbench-1", "widgets": []}}, CONTEXT)
    assert error.value.code == "invalid_input"

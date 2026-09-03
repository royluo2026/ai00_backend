from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from backend.capability_v2.provider_contracts import CapabilityContext
from backend.capabilities.validation_next import validate_payload
from backend.capability_v2.descriptor_adapter import (
    descriptor_from_provider_spec as adapt_v1_spec,
)
from backend.capability_v2.business_definition import substantive_business_definition_errors
from plugins.project_management.project_management_backend.capabilities import (
    register_capabilities,
)
from plugins.project_management.project_management_backend.capabilities.provider import (
    DEPRECATED_CAPABILITY_IDS,
    descriptor_for,
)
from plugins.project_management.project_management_backend.capabilities.reviewed import (
    _ATOMIC_OUTPUT_SCHEMAS,
    EXACT_CAPABILITY_IDS,
)
from plugins.project_management.project_management_backend.capabilities.projects import (
    register_project_capabilities,
    search_projects,
)
from plugins.project_management.project_management_backend.data.connection import _params


CONTEXT = CapabilityContext(user_gid="user-1", team_gid="team-1")
ROOT = Path(__file__).resolve().parents[3]


class Registry:
    def register(self, spec, handler, *, descriptor=None):
        self.spec = spec
        self.handler = handler
        self.descriptor = descriptor


class SnapshotRegistry:
    def __init__(self):
        self.items = []

    def register(self, spec, handler, *, descriptor=None):
        self.items.append((spec, handler, descriptor))


def _frozen_project_capability_ids() -> set[str]:
    review = json.loads(
        (ROOT / "docs/governance/capability-coverage-review/project-management.json")
        .read_text(encoding="utf-8")
    )
    return set(review["capabilities"])


def test_project_provider_is_complete_against_frozen_review():
    registry = SnapshotRegistry()
    register_capabilities(registry)
    actual = {
        descriptor.id for _, _, descriptor in registry.items
        if ".atomic." not in descriptor.id
    }

    assert actual == _frozen_project_capability_ids()


def test_all_project_capabilities_have_native_stable_contracts():
    registry = SnapshotRegistry()
    register_capabilities(registry)

    for spec, _, descriptor in registry.items:
        assert descriptor is not None, spec.id
        assert descriptor.owner_domain == "project_management"
        if spec.id in DEPRECATED_CAPABILITY_IDS:
            assert descriptor.lifecycle_status == "deprecated"
            assert descriptor.input_schema["properties"]["operation"]["enum"] == []
            continue
        assert descriptor.lifecycle_status == "stable"
        assert descriptor.exposure.agent is True
        assert descriptor.exposure.plugin is True
        assert descriptor.domain_errors_complete is True
        assert descriptor.domain_errors
        assert substantive_business_definition_errors(descriptor) == (), spec.id


def test_project_capability_version_gid_changes_with_contract_schema():
    registry = SnapshotRegistry()
    register_capabilities(registry)
    spec = next(
        spec for spec, _, descriptor in registry.items
        if descriptor.id == "project.task.read.atomic.tasks_search"
    )
    changed = spec.model_copy(update={
        "input_schema": {
            **spec.input_schema,
            "properties": {
                **spec.input_schema["properties"],
                "contract_probe": {"type": "string"},
            },
        }
    })

    assert descriptor_for(spec).capability_version_gid != descriptor_for(
        changed
    ).capability_version_gid


def test_workbench_atomic_capabilities_publish_closed_runtime_contracts():
    registry = SnapshotRegistry()
    register_capabilities(registry)
    descriptors = {descriptor.id: descriptor for _, _, descriptor in registry.items}

    cases = {
        "project.project.read.atomic.projects_search": (
            {
                "arguments": {
                    "include_deleted": False,
                    "include_archived": False,
                    "scope": {"user_gid": "user-1"},
                }
            },
            {"data": {"success": True, "data": []}},
        ),
        "project.task.read.atomic.tasks_search": (
            {
                "arguments": {
                    "project_gid": None,
                    "status": None,
                    "list_gid": None,
                    "scheduled_date_from": "2026-08-01",
                    "q": None,
                    "page_size": 300,
                    "scope": {"user_gid": "user-1"},
                }
            },
            {"data": {"success": True, "data": [{
                "gid": "task-1",
                "title": "Governed task",
                "source_ref": {},
                "attachments": [],
                "progress_logs": [],
                "feishu_groups": [],
                "feishu_docs": [],
                "canvas_row_gid": "row-1",
                "canvas_col_gid": "col-1",
                "is_deleted": False,
            }]}},
        ),
        "project.issue.read.atomic.issues_search": (
            {"arguments": {"page_size": 200, "scope": {"user_gid": "user-1"}}},
            {"data": {"success": True, "data": [{
                "gid": "issue-1",
                "title": "Governed issue",
                "source_ref": {},
                "attachments": [],
                "tracking_refs": [],
                "feishu_groups": [],
                "feishu_docs": [],
            }]}},
        ),
        "project.follow.read.atomic.follows_list": (
            {"arguments": {"item_type": None}},
            {"data": {"success": True, "data": []}},
        ),
        "project.notification.read.atomic.notifications_unread_count": (
            {"arguments": {}},
            {"data": {"success": True, "data": {"count": 0}}},
        ),
        "project.list.read.atomic.lists_search": (
            {"arguments": {"item_type": None, "q": None, "scope": {"user_gid": "user-1"}}},
            {"data": {"success": True, "data": [{
                "gid": "list-1", "name": "Tasks", "color": "#5b8dee",
                "storage_scope": "cloud", "owner_type": "user", "owner_gid": "user-1",
                "creator_gid": "user-1", "visibility": "private", "read_scope": "personal",
                "write_scope": "personal", "deleted_at": None, "item_type": "task",
                "sort_order": 0, "created_at": "2026-09-01T00:00:00", "project_gid": None,
            }]}},
        ),
    }

    for capability_id, (payload, output) in cases.items():
        descriptor = descriptors[capability_id]
        validate_payload(descriptor.input_schema, payload)
        validate_payload(descriptor.output_schema, output, label="output")

    task_arguments = descriptors[
        "project.task.read.atomic.tasks_search"
    ].input_schema["properties"]["arguments"]
    assert task_arguments["additionalProperties"] is False
    assert task_arguments["properties"]["page_size"] == {
        "type": "integer", "minimum": 1, "maximum": 500,
    }
    assert task_arguments["properties"]["scheduled_date_from"] == {
        "type": ["string", "null"],
    }


def test_consolidated_project_capabilities_accept_a_bounded_operation_envelope():
    registry = SnapshotRegistry()
    register_capabilities(registry)

    generic = {
        spec.id: descriptor.input_schema
        for spec, _, descriptor in registry.items
        if spec.id.startswith("project.") and ".atomic." not in spec.id
        and spec.id not in EXACT_CAPABILITY_IDS
    }

    assert generic
    for capability_id, schema in generic.items():
        assert schema["required"] == ["operation", "arguments"], capability_id
        assert set(schema["properties"]) == {"operation", "arguments"}, capability_id
        assert schema["properties"]["operation"]["type"] == "string", capability_id
        assert schema["additionalProperties"] is False, capability_id


def test_project_database_never_falls_back_to_base_credentials(monkeypatch):
    monkeypatch.delenv("AI00_PROJECT_MANAGEMENT_DB_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "mysql://base:secret@db/base")

    with pytest.raises(RuntimeError, match="AI00_PROJECT_MANAGEMENT_DB_URL"):
        _params()


def test_project_search_returns_only_stable_refs():
    fake_repository = Mock()
    fake_repository.search.return_value = [
        {"gid": "p1", "name": "Alpha", "project_code": "A-1", "status": "active"}
    ]
    with patch(
        "plugins.project_management.project_management_backend.capabilities.projects.repository",
        fake_repository,
    ):
        result = search_projects({"query": "Alpha", "limit": 10}, CONTEXT)

    assert result.data == {
        "items": [{
            "object_ref": "project:p1",
            "title": "Alpha",
            "summary": "active",
            "match_reason": "name_or_code",
            "owner": "project_management",
        }],
        "total": 1,
        "query": "Alpha",
    }
    fake_repository.search.assert_called_once_with("Alpha", 10, CONTEXT)


def test_project_search_descriptor_is_project_owned_and_automation_ready():
    registry = Registry()
    register_project_capabilities(registry)
    descriptor = registry.descriptor or adapt_v1_spec(registry.spec)

    assert descriptor.owner_domain == "project_management"
    assert descriptor.exposure.plugin is True
    assert descriptor.exposure.agent is True
    assert descriptor.output_schema["properties"]


def test_vehicle_model_list_has_a_real_closed_atomic_output_contract():
    schema = _ATOMIC_OUTPUT_SCHEMAS["vehicle_models.list"]
    item = schema["properties"]["data"]["items"]
    assert item["additionalProperties"] is False
    assert set(item["properties"]) == {
        "gid", "name", "brand", "platform", "vehicle_type", "created_at",
    }

from __future__ import annotations

from backend.tests.capability_completion_support import registered_descriptor_ids
from plugins.project_management.project_management_backend.api.compatibility import _atomic_web_target


def test_project_compatibility_pins_operation_to_atomic_capability() -> None:
    capability_id, payload = _atomic_web_target(
        "project.task.change.apply",
        {"operation": "tasks.create", "arguments": {"title": "one"}},
    )

    assert capability_id == "project.task.change.apply.atomic.tasks_create"
    assert payload == {"title": "one"}


def test_knowledge_and_project_register_fixed_operation_capabilities() -> None:
    knowledge = registered_descriptor_ids("plugins.knowledge.knowledge_backend.capabilities")
    project = registered_descriptor_ids("plugins.project_management.project_management_backend.capabilities")

    assert "knowledge.entry.change.apply.atomic.entries_create" in knowledge
    assert "knowledge.hub.read.atomic.items_get" in knowledge
    assert "project.task.change.apply.atomic.tasks_create" in project
    assert "project.approval.read.atomic.approval_orders_search" in project

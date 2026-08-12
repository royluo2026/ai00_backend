from __future__ import annotations

from backend.base.collaboration import (
    COLLABORATION_CAPABILITY_IDS,
    BaseCollaborationService,
    collaboration_service_port,
    register_collaboration_capabilities,
)
from backend.capabilities.models_next import CapabilityContext
from backend.capabilities.registry_next import CapabilityRegistry


def test_notification_search_and_read_state_are_tenant_and_recipient_scoped():
    service = BaseCollaborationService()
    notification = service.notify(
        tenant_gid="tenant-1",
        recipient_gid="user-1",
        subject_ref="approval-1",
        payload={"message": "Approval requested"},
    )
    service.notify(
        tenant_gid="tenant-1",
        recipient_gid="user-2",
        subject_ref="approval-2",
        payload={"message": "Hidden from user-1"},
    )

    found = service.search_notifications(
        tenant_gid="tenant-1", recipient_gid="user-1"
    )
    updated = service.set_notification_read_state(
        tenant_gid="tenant-1",
        recipient_gid="user-1",
        notification_id=notification.notification_id,
        read=True,
    )

    assert [item.notification_id for item in found] == [notification.notification_id]
    assert updated.read_at is not None


def test_notification_preferences_use_optimistic_versioning():
    service = BaseCollaborationService()

    initial = service.get_preferences(tenant_gid="tenant-1", user_gid="user-1")
    updated = service.update_preferences(
        tenant_gid="tenant-1",
        user_gid="user-1",
        expected_version=initial.version,
        preferences={"approval": {"in_app": True, "email": False}},
    )

    assert updated.version == 1
    assert updated.preferences["approval"]["in_app"] is True


def test_workspace_publish_creates_immutable_versions():
    service = BaseCollaborationService()

    first = service.publish_workspace_template(
        tenant_gid="tenant-1",
        template_id="team-home",
        publisher_gid="user-1",
        expected_version=0,
        template={"widgets": ["approvals"]},
    )
    second = service.publish_workspace_template(
        tenant_gid="tenant-1",
        template_id="team-home",
        publisher_gid="user-1",
        expected_version=1,
        template={"widgets": ["approvals", "activity"]},
    )

    assert first.version == 1
    assert second.version == 2
    assert service.read_workspace_template(
        tenant_gid="tenant-1", template_id="team-home", version=1
    ).template == {"widgets": ["approvals"]}


def test_collaboration_capabilities_expose_the_six_reviewed_base_operations():
    registry = CapabilityRegistry()
    service = BaseCollaborationService()
    notification = service.notify(
        tenant_gid="tenant-1",
        recipient_gid="user-1",
        subject_ref="approval-1",
        payload={"message": "Approval requested"},
    )
    collaboration_service_port.bind(service)
    register_collaboration_capabilities(registry)
    context = CapabilityContext(user_gid="user-1", team_gid="tenant-1")
    try:
        found = registry.get("base.notification.search", 1).handler({}, context)
        read = registry.get("base.notification.read_state.set", 1).handler(
            {"notification_id": notification.notification_id, "read": True}, context
        )
        preferences = registry.get("base.notification.preference.get", 1).handler(
            {}, context
        )
        updated = registry.get("base.notification.preference.update", 1).handler(
            {"expected_version": 0, "preferences": {"in_app": True}}, context
        )
        published = registry.get("base.workspace.template.publish", 1).handler(
            {
                "template_id": "team-home",
                "expected_version": 0,
                "template": {"widgets": ["approvals"]},
            },
            context,
        )
        loaded = registry.get("base.workspace.template.read", 1).handler(
            {"template_id": "team-home", "version": 1}, context
        )
    finally:
        collaboration_service_port.clear()

    assert {item.spec.id for item in registry.snapshot()} == COLLABORATION_CAPABILITY_IDS
    assert found["items"][0]["notification_id"] == notification.notification_id
    assert read["read_at"] is not None
    assert preferences == {"version": 0, "preferences": {}}
    assert updated == {"version": 1, "preferences": {"in_app": True}}
    assert published["version"] == 1
    assert loaded["template"] == {"widgets": ["approvals"]}

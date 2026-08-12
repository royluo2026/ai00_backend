from __future__ import annotations

from backend.base.collaboration import BaseCollaborationService


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

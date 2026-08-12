"""Base Notification and Workspace domain services."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from uuid import uuid4

from backend.capabilities.models_next import CapabilityBusinessError


@dataclass(frozen=True)
class Notification:
    tenant_gid: str
    notification_id: str
    recipient_gid: str
    subject_ref: str
    payload: dict
    read_at: datetime | None
    created_at: datetime


@dataclass(frozen=True)
class NotificationPreferences:
    tenant_gid: str
    user_gid: str
    version: int
    preferences: dict


@dataclass(frozen=True)
class WorkspaceTemplate:
    tenant_gid: str
    template_id: str
    version: int
    template: dict
    publisher_gid: str
    published_at: datetime


class BaseCollaborationService:
    def __init__(self) -> None:
        self._notifications: dict[tuple[str, str], Notification] = {}
        self._preferences: dict[tuple[str, str], NotificationPreferences] = {}
        self._templates: dict[tuple[str, str, int], WorkspaceTemplate] = {}
        self._latest_template: dict[tuple[str, str], int] = {}
        self._lock = RLock()

    @staticmethod
    def _required(value: str, code: str) -> str:
        value = value.strip()
        if not value:
            raise CapabilityBusinessError(code, f"{code} is required.")
        return value

    def notify(
        self,
        *,
        tenant_gid: str,
        recipient_gid: str,
        subject_ref: str,
        payload: dict,
    ) -> Notification:
        item = Notification(
            tenant_gid=self._required(tenant_gid, "tenant_required"),
            notification_id="not_" + uuid4().hex,
            recipient_gid=self._required(recipient_gid, "recipient_required"),
            subject_ref=self._required(subject_ref, "subject_ref_required"),
            payload=deepcopy(payload),
            read_at=None,
            created_at=datetime.now(UTC),
        )
        with self._lock:
            self._notifications[(item.tenant_gid, item.notification_id)] = item
        return item

    def search_notifications(
        self, *, tenant_gid: str, recipient_gid: str
    ) -> tuple[Notification, ...]:
        with self._lock:
            values = [
                item for item in self._notifications.values()
                if item.tenant_gid == tenant_gid
                and item.recipient_gid == recipient_gid
            ]
        return tuple(sorted(values, key=lambda item: (item.created_at, item.notification_id)))

    def set_notification_read_state(
        self,
        *,
        tenant_gid: str,
        recipient_gid: str,
        notification_id: str,
        read: bool,
    ) -> Notification:
        with self._lock:
            key = (tenant_gid, notification_id)
            current = self._notifications.get(key)
            if current is None or current.recipient_gid != recipient_gid:
                raise CapabilityBusinessError(
                    "resource_not_found", "Notification was not found."
                )
            updated = Notification(
                **{
                    **current.__dict__,
                    "read_at": datetime.now(UTC) if read else None,
                }
            )
            self._notifications[key] = updated
            return updated

    def get_preferences(
        self, *, tenant_gid: str, user_gid: str
    ) -> NotificationPreferences:
        key = (self._required(tenant_gid, "tenant_required"), user_gid)
        with self._lock:
            return self._preferences.get(key) or NotificationPreferences(
                tenant_gid=key[0], user_gid=user_gid, version=0, preferences={}
            )

    def update_preferences(
        self,
        *,
        tenant_gid: str,
        user_gid: str,
        expected_version: int,
        preferences: dict,
    ) -> NotificationPreferences:
        with self._lock:
            current = self.get_preferences(tenant_gid=tenant_gid, user_gid=user_gid)
            if current.version != expected_version:
                raise CapabilityBusinessError(
                    "version_conflict", "Notification preference version changed."
                )
            updated = NotificationPreferences(
                tenant_gid=tenant_gid,
                user_gid=user_gid,
                version=current.version + 1,
                preferences=deepcopy(preferences),
            )
            self._preferences[(tenant_gid, user_gid)] = updated
            return updated

    def publish_workspace_template(
        self,
        *,
        tenant_gid: str,
        template_id: str,
        publisher_gid: str,
        expected_version: int,
        template: dict,
    ) -> WorkspaceTemplate:
        key = (self._required(tenant_gid, "tenant_required"), template_id)
        with self._lock:
            current = self._latest_template.get(key, 0)
            if current != expected_version:
                raise CapabilityBusinessError(
                    "version_conflict", "Workspace template version changed."
                )
            version = current + 1
            item = WorkspaceTemplate(
                tenant_gid=key[0],
                template_id=template_id,
                version=version,
                template=deepcopy(template),
                publisher_gid=publisher_gid,
                published_at=datetime.now(UTC),
            )
            self._templates[(key[0], template_id, version)] = item
            self._latest_template[key] = version
            return item

    def read_workspace_template(
        self,
        *,
        tenant_gid: str,
        template_id: str,
        version: int | None = None,
    ) -> WorkspaceTemplate:
        key = (tenant_gid, template_id)
        with self._lock:
            selected = version or self._latest_template.get(key)
            item = self._templates.get((tenant_gid, template_id, selected or 0))
            if item is None:
                raise CapabilityBusinessError(
                    "resource_not_found", "Workspace template was not found."
                )
            return item


__all__ = [
    "BaseCollaborationService",
    "Notification",
    "NotificationPreferences",
    "WorkspaceTemplate",
]

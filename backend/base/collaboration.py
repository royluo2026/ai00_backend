"""Base Notification and Workspace domain services."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from threading import RLock
from uuid import uuid4

from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError,
    CapabilityRisk,
    CapabilitySpec,
)

from .provider import register_capability


COLLABORATION_CAPABILITY_IDS = {
    "base.notification.search",
    "base.notification.read_state.set",
    "base.notification.preference.get",
    "base.notification.preference.update",
    "base.workspace.template.read",
    "base.workspace.template.publish",
}


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


class SqlBaseCollaborationService:
    """Production collaboration service using only the Base runtime credential."""

    def __init__(self, connection_factory=None) -> None:
        if connection_factory is None:
            from .approval import _base_runtime_connection
            connection_factory = _base_runtime_connection
        self._connection_factory = connection_factory

    @staticmethod
    def _json(value):
        return json.loads(value) if isinstance(value, str) else value

    @classmethod
    def _notification(cls, row) -> Notification:
        return Notification(
            tenant_gid=row[0], notification_id=row[1], recipient_gid=row[2],
            subject_ref=row[3], payload=cls._json(row[4]), read_at=row[5],
            created_at=row[6],
        )

    def notify(self, *, tenant_gid: str, recipient_gid: str, subject_ref: str, payload: dict) -> Notification:
        item = Notification(tenant_gid, "not_" + uuid4().hex, recipient_gid,
                            subject_ref, deepcopy(payload), None, datetime.now(UTC))
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO workmanship_base_notifications "
                    "(tenant_gid,notification_id,recipient_gid,subject_ref,payload_json,read_at,created_at) "
                    "VALUES (%s,%s,%s,%s,%s,NULL,%s)",
                    (tenant_gid, item.notification_id, recipient_gid, subject_ref,
                     json.dumps(payload, ensure_ascii=False, sort_keys=True), item.created_at),
                )
            connection.commit()
        return item

    def search_notifications(self, *, tenant_gid: str, recipient_gid: str) -> tuple[Notification, ...]:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT tenant_gid,notification_id,recipient_gid,subject_ref,payload_json,read_at,created_at "
                    "FROM workmanship_base_notifications WHERE tenant_gid=%s AND recipient_gid=%s "
                    "ORDER BY created_at,notification_id", (tenant_gid, recipient_gid),
                )
                rows = cursor.fetchall()
        return tuple(self._notification(row) for row in rows)

    def set_notification_read_state(self, *, tenant_gid: str, recipient_gid: str,
                                    notification_id: str, read: bool) -> Notification:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT tenant_gid,notification_id,recipient_gid,subject_ref,payload_json,read_at,created_at "
                    "FROM workmanship_base_notifications WHERE tenant_gid=%s AND notification_id=%s "
                    "AND recipient_gid=%s FOR UPDATE", (tenant_gid, notification_id, recipient_gid),
                )
                row = cursor.fetchone()
                if row is None:
                    raise CapabilityBusinessError("resource_not_found", "Notification was not found.")
                read_at = datetime.now(UTC) if read else None
                cursor.execute(
                    "UPDATE workmanship_base_notifications SET read_at=%s "
                    "WHERE tenant_gid=%s AND notification_id=%s AND recipient_gid=%s",
                    (read_at, tenant_gid, notification_id, recipient_gid),
                )
            connection.commit()
        return Notification(**{**self._notification(row).__dict__, "read_at": read_at})

    def get_preferences(self, *, tenant_gid: str, user_gid: str) -> NotificationPreferences:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT version,preferences_json FROM workmanship_base_notification_preferences "
                    "WHERE tenant_gid=%s AND user_gid=%s", (tenant_gid, user_gid),
                )
                row = cursor.fetchone()
        return NotificationPreferences(tenant_gid, user_gid, row[0], self._json(row[1])) if row else NotificationPreferences(tenant_gid, user_gid, 0, {})

    def update_preferences(self, *, tenant_gid: str, user_gid: str,
                           expected_version: int, preferences: dict) -> NotificationPreferences:
        document = json.dumps(preferences, ensure_ascii=False, sort_keys=True)
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT version FROM workmanship_base_notification_preferences "
                    "WHERE tenant_gid=%s AND user_gid=%s FOR UPDATE", (tenant_gid, user_gid),
                )
                row = cursor.fetchone()
                current = row[0] if row else 0
                if current != expected_version:
                    raise CapabilityBusinessError("version_conflict", "Notification preference version changed.")
                version = current + 1
                if row:
                    cursor.execute(
                        "UPDATE workmanship_base_notification_preferences SET version=%s,preferences_json=%s,updated_at=%s "
                        "WHERE tenant_gid=%s AND user_gid=%s AND version=%s",
                        (version, document, datetime.now(UTC), tenant_gid, user_gid, current),
                    )
                else:
                    cursor.execute(
                        "INSERT INTO workmanship_base_notification_preferences "
                        "(tenant_gid,user_gid,version,preferences_json) VALUES (%s,%s,%s,%s)",
                        (tenant_gid, user_gid, version, document),
                    )
            connection.commit()
        return NotificationPreferences(tenant_gid, user_gid, version, deepcopy(preferences))

    def publish_workspace_template(self, *, tenant_gid: str, template_id: str,
                                   publisher_gid: str, expected_version: int,
                                   template: dict) -> WorkspaceTemplate:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT MAX(version) FROM workmanship_base_workspace_templates "
                    "WHERE tenant_gid=%s AND template_id=%s FOR UPDATE", (tenant_gid, template_id),
                )
                current = cursor.fetchone()[0] or 0
                if current != expected_version:
                    raise CapabilityBusinessError("version_conflict", "Workspace template version changed.")
                version, published_at = current + 1, datetime.now(UTC)
                cursor.execute(
                    "INSERT INTO workmanship_base_workspace_templates "
                    "(tenant_gid,template_id,version,template_json,published_by,published_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s)",
                    (tenant_gid, template_id, version,
                     json.dumps(template, ensure_ascii=False, sort_keys=True), publisher_gid, published_at),
                )
            connection.commit()
        return WorkspaceTemplate(tenant_gid, template_id, version, deepcopy(template), publisher_gid, published_at)

    def read_workspace_template(self, *, tenant_gid: str, template_id: str,
                                version: int | None = None) -> WorkspaceTemplate:
        clause = "version=%s" if version is not None else "version=(SELECT MAX(t.version) FROM workmanship_base_workspace_templates t WHERE t.tenant_gid=%s AND t.template_id=%s)"
        params = (tenant_gid, template_id, version) if version is not None else (tenant_gid, template_id, tenant_gid, template_id)
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT tenant_gid,template_id,version,template_json,published_by,published_at "
                    "FROM workmanship_base_workspace_templates WHERE tenant_gid=%s AND template_id=%s AND " + clause,
                    params,
                )
                row = cursor.fetchone()
        if row is None:
            raise CapabilityBusinessError("resource_not_found", "Workspace template was not found.")
        return WorkspaceTemplate(row[0], row[1], row[2], self._json(row[3]), row[4], row[5])


@dataclass
class CollaborationServicePort:
    service: BaseCollaborationService | SqlBaseCollaborationService | None = None

    def bind(self, service) -> None:
        self.service = service

    def clear(self) -> None:
        self.service = None

    def require(self):
        return self.service or SqlBaseCollaborationService()


collaboration_service_port = CollaborationServicePort()


def _tenant(context: object) -> str:
    value = str(getattr(context, "team_gid", "") or "").strip()
    if not value:
        raise CapabilityBusinessError("tenant_required", "An authenticated tenant is required.")
    return value


def _notification_dict(item: Notification) -> dict:
    return {"notification_id": item.notification_id, "subject_ref": item.subject_ref,
            "payload": item.payload, "read_at": item.read_at.isoformat() if item.read_at else None,
            "created_at": item.created_at.isoformat()}


def _template_dict(item: WorkspaceTemplate) -> dict:
    return {"template_id": item.template_id, "version": item.version,
            "template": item.template, "publisher_gid": item.publisher_gid,
            "published_at": item.published_at.isoformat()}


def register_collaboration_capabilities(registry) -> None:
    def search(payload, context):
        items = collaboration_service_port.require().search_notifications(
            tenant_gid=_tenant(context), recipient_gid=str(getattr(context, "user_gid", "")))
        return {"items": [_notification_dict(item) for item in items]}

    handlers = {
        "base.notification.search": search,
        "base.notification.read_state.set": lambda p, c: _notification_dict(collaboration_service_port.require().set_notification_read_state(tenant_gid=_tenant(c), recipient_gid=str(getattr(c, "user_gid", "")), notification_id=p["notification_id"], read=p["read"])),
        "base.notification.preference.get": lambda p, c: (lambda x: {"version": x.version, "preferences": x.preferences})(collaboration_service_port.require().get_preferences(tenant_gid=_tenant(c), user_gid=str(getattr(c, "user_gid", "")))),
        "base.notification.preference.update": lambda p, c: (lambda x: {"version": x.version, "preferences": x.preferences})(collaboration_service_port.require().update_preferences(tenant_gid=_tenant(c), user_gid=str(getattr(c, "user_gid", "")), expected_version=p["expected_version"], preferences=p["preferences"])),
        "base.workspace.template.publish": lambda p, c: _template_dict(collaboration_service_port.require().publish_workspace_template(tenant_gid=_tenant(c), template_id=p["template_id"], publisher_gid=str(getattr(c, "user_gid", "")), expected_version=p["expected_version"], template=p["template"])),
        "base.workspace.template.read": lambda p, c: _template_dict(collaboration_service_port.require().read_workspace_template(tenant_gid=_tenant(c), template_id=p["template_id"], version=p.get("version"))),
    }
    for capability_id in sorted(COLLABORATION_CAPABILITY_IDS):
        is_read = capability_id.endswith((".search", ".get", ".read"))
        register_capability(registry, CapabilitySpec(
            owner="base", id=capability_id, version=1,
            description=f"Execute {capability_id} in the Base collaboration service.",
            risk=CapabilityRisk.READ if is_read else CapabilityRisk.WRITE,
            confirmation="none", idempotent=True,
            permissions=("base.collaboration.read",) if is_read else ("base.collaboration.write",),
            input_schema={"type": "object"}, output_schema={"type": "object"},
            tags=("base", "collaboration", "read" if is_read else "write"),
        ), handlers[capability_id])

__all__ = [
    "BaseCollaborationService",
    "COLLABORATION_CAPABILITY_IDS",
    "CollaborationServicePort",
    "Notification",
    "NotificationPreferences",
    "WorkspaceTemplate",
    "SqlBaseCollaborationService",
    "collaboration_service_port",
    "register_collaboration_capabilities",
]

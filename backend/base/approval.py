"""Base-owned business Approval aggregate and application service."""
from __future__ import annotations

import re
import json
import os
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from threading import RLock
from typing import Protocol
from uuid import uuid4
from pathlib import Path

from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError,
    CapabilityRisk,
    CapabilitySpec,
)

from .provider import register_capability
from backend.capability_v2.domain_database import (
    connect_domain_database,
    load_domain_database_url,
)
from backend.capability_v2.domain_manifest import load_domain_manifests


APPROVAL_CAPABILITY_IDS = {
    "base.approval.request.create",
    "base.approval.request.get",
    "base.approval.request.search",
    "base.approval.request.decide",
    "base.approval.request.cancel",
}


_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_FINAL_STATES = {"approved", "rejected", "cancelled"}


@dataclass(frozen=True)
class ApprovalRequest:
    tenant_gid: str
    approval_id: str
    subject_ref: str
    requester_gid: str
    resource_ref: str
    revision: str
    content_hash: str
    reason: str
    approver_ids: tuple[str, ...]
    status: str
    decision_reason: str | None
    decided_by: str | None
    created_at: datetime
    updated_at: datetime


class ApprovalRepository(Protocol):
    def add(self, request: ApprovalRequest) -> None: ...

    def get(self, tenant_gid: str, approval_id: str) -> ApprovalRequest | None: ...

    def search(
        self, tenant_gid: str, subject_ref: str | None, status: str | None
    ) -> tuple[ApprovalRequest, ...]: ...

    def transition(
        self,
        tenant_gid: str,
        approval_id: str,
        expected_state: str,
        target_state: str,
        *,
        actor_gid: str,
        reason: str | None,
        idempotent_target: bool,
    ) -> ApprovalRequest: ...


class InMemoryApprovalRepository:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], ApprovalRequest] = {}
        self._lock = RLock()

    def add(self, request: ApprovalRequest) -> None:
        with self._lock:
            key = (request.tenant_gid, request.approval_id)
            if key in self._items:
                raise CapabilityBusinessError(
                    "idempotency_conflict", "Approval ID already exists."
                )
            self._items[key] = request

    def get(self, tenant_gid: str, approval_id: str) -> ApprovalRequest | None:
        with self._lock:
            return self._items.get((tenant_gid, approval_id))

    def search(
        self, tenant_gid: str, subject_ref: str | None, status: str | None
    ) -> tuple[ApprovalRequest, ...]:
        with self._lock:
            values = [
                item
                for item in self._items.values()
                if item.tenant_gid == tenant_gid
                and (subject_ref is None or item.subject_ref == subject_ref)
                and (status is None or item.status == status)
            ]
            return tuple(sorted(values, key=lambda item: (item.created_at, item.approval_id)))

    def transition(
        self,
        tenant_gid: str,
        approval_id: str,
        expected_state: str,
        target_state: str,
        *,
        actor_gid: str,
        reason: str | None,
        idempotent_target: bool,
    ) -> ApprovalRequest:
        with self._lock:
            key = (tenant_gid, approval_id)
            current = self._items.get(key)
            if current is None:
                raise CapabilityBusinessError(
                    "resource_not_found", "Approval request was not found."
                )
            if idempotent_target and current.status == target_state:
                return current
            if current.status != expected_state:
                raise CapabilityBusinessError(
                    "state_conflict",
                    f"Approval is {current.status}, expected {expected_state}.",
                )
            now = datetime.now(UTC)
            updated = replace(
                current,
                status=target_state,
                decision_reason=reason,
                decided_by=actor_gid,
                updated_at=now,
            )
            self._items[key] = updated
            return updated


class SqlApprovalRepository:
    """Runtime repository that opens only the Base domain credential."""

    _COLUMNS = (
        "tenant_gid", "approval_id", "subject_ref", "requester_gid", "status",
        "request_json", "decision_json", "created_at", "updated_at",
    )

    def __init__(self, connection_factory=None) -> None:
        self._connection_factory = connection_factory or _base_runtime_connection

    @classmethod
    def _request(cls, row) -> ApprovalRequest:
        values = row if isinstance(row, dict) else dict(zip(cls._COLUMNS, row))
        request = values["request_json"]
        decision = values.get("decision_json")
        if isinstance(request, str):
            request = json.loads(request)
        if isinstance(decision, str):
            decision = json.loads(decision)
        decision = decision or {}
        return ApprovalRequest(
            tenant_gid=values["tenant_gid"],
            approval_id=values["approval_id"],
            subject_ref=values["subject_ref"],
            requester_gid=values["requester_gid"],
            resource_ref=request["resource_ref"],
            revision=request["revision"],
            content_hash=request["content_hash"],
            reason=request["reason"],
            approver_ids=tuple(request["approver_ids"]),
            status=values["status"],
            decision_reason=decision.get("reason"),
            decided_by=decision.get("actor_gid"),
            created_at=values["created_at"],
            updated_at=values["updated_at"],
        )

    def add(self, request: ApprovalRequest) -> None:
        document = json.dumps({
            "resource_ref": request.resource_ref,
            "revision": request.revision,
            "content_hash": request.content_hash,
            "reason": request.reason,
            "approver_ids": list(request.approver_ids),
        }, ensure_ascii=False, sort_keys=True)
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO workmanship_base_approvals "
                    "(tenant_gid,approval_id,subject_ref,requester_gid,status,"
                    "expected_state,request_json,decision_json,created_at,updated_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,NULL,%s,%s)",
                    (
                        request.tenant_gid, request.approval_id,
                        request.subject_ref, request.requester_gid, request.status,
                        "pending", document, request.created_at, request.updated_at,
                    ),
                )
            connection.commit()

    def get(self, tenant_gid: str, approval_id: str) -> ApprovalRequest | None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT tenant_gid,approval_id,subject_ref,requester_gid,status,"
                    "request_json,decision_json,created_at,updated_at "
                    "FROM workmanship_base_approvals "
                    "WHERE tenant_gid=%s AND approval_id=%s",
                    (tenant_gid, approval_id),
                )
                row = cursor.fetchone()
        return self._request(row) if row else None

    def search(
        self, tenant_gid: str, subject_ref: str | None, status: str | None
    ) -> tuple[ApprovalRequest, ...]:
        clauses = ["tenant_gid=%s"]
        parameters: list[str] = [tenant_gid]
        if subject_ref is not None:
            clauses.append("subject_ref=%s")
            parameters.append(subject_ref)
        if status is not None:
            clauses.append("status=%s")
            parameters.append(status)
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT tenant_gid,approval_id,subject_ref,requester_gid,status,"
                    "request_json,decision_json,created_at,updated_at "
                    "FROM workmanship_base_approvals WHERE "
                    + " AND ".join(clauses)
                    + " ORDER BY created_at,approval_id",
                    tuple(parameters),
                )
                rows = cursor.fetchall()
        return tuple(self._request(row) for row in rows)

    def transition(
        self,
        tenant_gid: str,
        approval_id: str,
        expected_state: str,
        target_state: str,
        *,
        actor_gid: str,
        reason: str | None,
        idempotent_target: bool,
    ) -> ApprovalRequest:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT tenant_gid,approval_id,subject_ref,requester_gid,status,"
                    "request_json,decision_json,created_at,updated_at "
                    "FROM workmanship_base_approvals "
                    "WHERE tenant_gid=%s AND approval_id=%s FOR UPDATE",
                    (tenant_gid, approval_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise CapabilityBusinessError(
                        "resource_not_found", "Approval request was not found."
                    )
                current = self._request(row)
                if idempotent_target and current.status == target_state:
                    connection.rollback()
                    return current
                if current.status != expected_state:
                    connection.rollback()
                    raise CapabilityBusinessError(
                        "state_conflict",
                        f"Approval is {current.status}, expected {expected_state}.",
                    )
                now = datetime.now(UTC)
                decision = json.dumps(
                    {"actor_gid": actor_gid, "reason": reason},
                    ensure_ascii=False,
                    sort_keys=True,
                )
                cursor.execute(
                    "UPDATE workmanship_base_approvals "
                    "SET status=%s,decision_json=%s,updated_at=%s "
                    "WHERE tenant_gid=%s AND approval_id=%s AND status=%s",
                    (
                        target_state, decision, now, tenant_gid, approval_id,
                        expected_state,
                    ),
                )
                if cursor.rowcount != 1:
                    connection.rollback()
                    raise CapabilityBusinessError(
                        "state_conflict", "Approval state changed concurrently."
                    )
            connection.commit()
        return replace(
            current,
            status=target_state,
            decision_reason=reason,
            decided_by=actor_gid,
            updated_at=now,
        )


def _base_runtime_connection():
    root = Path(__file__).resolve().parents[2]
    manifests = load_domain_manifests(
        root / "backend/capability_v2/official_domains.json"
    )
    manifest = manifests.require("base")
    url = load_domain_database_url(manifest, os.environ, role="runtime")
    return connect_domain_database(url)


class ApprovalService:
    def __init__(self, repository: ApprovalRepository) -> None:
        self._repository = repository

    @staticmethod
    def _tenant(tenant_gid: str) -> str:
        value = tenant_gid.strip()
        if not value:
            raise CapabilityBusinessError(
                "tenant_required", "An authenticated tenant is required."
            )
        return value

    def create(
        self, *, tenant_gid: str, requester_gid: str, payload: dict
    ) -> ApprovalRequest:
        tenant_gid = self._tenant(tenant_gid)
        required = (
            "subject_ref",
            "resource_ref",
            "revision",
            "content_hash",
            "reason",
            "approver_ids",
        )
        if any(not payload.get(field) for field in required):
            raise CapabilityBusinessError(
                "validation_failed", "Approval request fields are incomplete."
            )
        if not _DIGEST_RE.fullmatch(str(payload["content_hash"])):
            raise CapabilityBusinessError(
                "validation_failed", "Approval content_hash must be an exact SHA-256 digest."
            )
        approvers = tuple(dict.fromkeys(str(item) for item in payload["approver_ids"] if item))
        if not approvers:
            raise CapabilityBusinessError(
                "validation_failed", "At least one approver is required."
            )
        now = datetime.now(UTC)
        request = ApprovalRequest(
            tenant_gid=tenant_gid,
            approval_id="apr_" + uuid4().hex,
            subject_ref=str(payload["subject_ref"]),
            requester_gid=requester_gid,
            resource_ref=str(payload["resource_ref"]),
            revision=str(payload["revision"]),
            content_hash=str(payload["content_hash"]),
            reason=str(payload["reason"]),
            approver_ids=approvers,
            status="pending",
            decision_reason=None,
            decided_by=None,
            created_at=now,
            updated_at=now,
        )
        self._repository.add(request)
        return request

    def get(self, *, tenant_gid: str, approval_id: str) -> ApprovalRequest:
        request = self._repository.get(self._tenant(tenant_gid), approval_id)
        if request is None:
            raise CapabilityBusinessError(
                "resource_not_found", "Approval request was not found."
            )
        return request

    def search(
        self,
        *,
        tenant_gid: str,
        subject_ref: str | None = None,
        status: str | None = None,
    ) -> tuple[ApprovalRequest, ...]:
        if status is not None and status not in {"pending", *_FINAL_STATES}:
            raise CapabilityBusinessError(
                "validation_failed", "Approval status filter is invalid."
            )
        return self._repository.search(
            self._tenant(tenant_gid), subject_ref, status
        )

    def decide(
        self,
        *,
        tenant_gid: str,
        approval_id: str,
        expected_state: str,
        actor_gid: str,
        decision: str,
        reason: str,
    ) -> ApprovalRequest:
        current = self.get(tenant_gid=tenant_gid, approval_id=approval_id)
        if actor_gid not in current.approver_ids:
            raise CapabilityBusinessError(
                "permission_denied", "Actor is not an approval participant."
            )
        if decision not in {"approved", "rejected"}:
            raise CapabilityBusinessError(
                "validation_failed", "Decision must be approved or rejected."
            )
        return self._repository.transition(
            self._tenant(tenant_gid),
            approval_id,
            expected_state,
            decision,
            actor_gid=actor_gid,
            reason=reason,
            idempotent_target=False,
        )

    def cancel(
        self,
        *,
        tenant_gid: str,
        approval_id: str,
        expected_state: str,
        actor_gid: str,
    ) -> ApprovalRequest:
        return self._repository.transition(
            self._tenant(tenant_gid),
            approval_id,
            expected_state,
            "cancelled",
            actor_gid=actor_gid,
            reason="Cancelled by the owning workflow.",
            idempotent_target=True,
        )


@dataclass
class ApprovalServicePort:
    service: ApprovalService | None = None

    def bind(self, service: ApprovalService) -> None:
        self.service = service

    def clear(self) -> None:
        self.service = None

    def require(self) -> ApprovalService:
        if self.service is None:
            return ApprovalService(SqlApprovalRepository())
        return self.service


approval_service_port = ApprovalServicePort()


def _tenant(context: object) -> str:
    tenant_gid = str(getattr(context, "team_gid", "") or "").strip()
    if not tenant_gid:
        raise CapabilityBusinessError(
            "tenant_required", "An authenticated tenant is required."
        )
    return tenant_gid


def _serialized(item: ApprovalRequest) -> dict:
    return {
        "approval_id": item.approval_id,
        "subject_ref": item.subject_ref,
        "requester_gid": item.requester_gid,
        "resource_ref": item.resource_ref,
        "revision": item.revision,
        "content_hash": item.content_hash,
        "reason": item.reason,
        "approver_ids": list(item.approver_ids),
        "status": item.status,
        "decision_reason": item.decision_reason,
        "decided_by": item.decided_by,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def _create(payload: dict, context: object) -> dict:
    return _serialized(approval_service_port.require().create(
        tenant_gid=_tenant(context),
        requester_gid=str(getattr(context, "user_gid", "")),
        payload=payload,
    ))


def _get(payload: dict, context: object) -> dict:
    return _serialized(approval_service_port.require().get(
        tenant_gid=_tenant(context), approval_id=payload["approval_id"]
    ))


def _search(payload: dict, context: object) -> dict:
    items = approval_service_port.require().search(
        tenant_gid=_tenant(context),
        subject_ref=payload.get("subject_ref"),
        status=payload.get("status"),
    )
    return {"items": [_serialized(item) for item in items]}


def _decide(payload: dict, context: object) -> dict:
    return _serialized(approval_service_port.require().decide(
        tenant_gid=_tenant(context),
        approval_id=payload["approval_id"],
        expected_state=payload["expected_state"],
        actor_gid=str(getattr(context, "user_gid", "")),
        decision=payload["decision"],
        reason=payload["reason"],
    ))


def _cancel(payload: dict, context: object) -> dict:
    return _serialized(approval_service_port.require().cancel(
        tenant_gid=_tenant(context),
        approval_id=payload["approval_id"],
        expected_state=payload["expected_state"],
        actor_gid=str(getattr(context, "user_gid", "")),
    ))


def register_approval_capabilities(registry) -> None:
    handlers = {
        "base.approval.request.create": _create,
        "base.approval.request.get": _get,
        "base.approval.request.search": _search,
        "base.approval.request.decide": _decide,
        "base.approval.request.cancel": _cancel,
    }
    for capability_id in sorted(APPROVAL_CAPABILITY_IDS):
        is_read = capability_id.endswith((".get", ".search"))
        register_capability(
            registry,
            CapabilitySpec(
                owner="base",
                id=capability_id,
                version=1,
                description=f"Execute {capability_id} in the Base Approval service.",
                risk=CapabilityRisk.READ if is_read else CapabilityRisk.WRITE,
                confirmation="none",
                idempotent=True,
                permissions=("base.approval.read",) if is_read else ("base.approval.write",),
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                tags=("base", "approval", "read" if is_read else "write"),
            ),
            handlers[capability_id],
        )


__all__ = [
    "ApprovalRepository",
    "ApprovalRequest",
    "ApprovalService",
    "ApprovalServicePort",
    "APPROVAL_CAPABILITY_IDS",
    "InMemoryApprovalRepository",
    "SqlApprovalRepository",
    "approval_service_port",
    "register_approval_capabilities",
]

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy

import pytest

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext
from plugins.project_management.project_management_backend.application.service import (
    ProjectManagementApplication,
    RejectOrder,
)
from plugins.project_management.project_management_backend.capabilities.reviewed import (
    register_reviewed_capabilities,
)


class InMemoryApprovalRejectRepository:
    def __init__(self, *, fail_outbox: bool = False) -> None:
        self.fail_outbox = fail_outbox
        self.orders = {
            "order-1": {
                "gid": "order-1",
                "team_gid": "team-1",
                "reviewer_gid": "reviewer-1",
                "applicant_gid": "applicant-1",
                "status": "in_review",
                "revision": 7,
                "opinions": [],
            }
        }
        self.operations: dict[tuple[str, str, str, str], dict] = {}
        self.audits: list[dict] = []
        self.notifications: list[dict] = []

    @contextmanager
    def transaction(self):
        snapshot = deepcopy((self.orders, self.operations, self.audits, self.notifications))
        try:
            yield self
        except Exception:
            self.orders, self.operations, self.audits, self.notifications = snapshot
            raise

    def claim_approval_rejection(self, *, actor_gid, team_gid, idempotency_key, payload_hash):
        key = (actor_gid, team_gid, "project.approval.order.reject@1", idempotency_key)
        existing = self.operations.get(key)
        if existing is None:
            self.operations[key] = {"payload_hash": payload_hash, "result": None}
            return None
        if existing["payload_hash"] != payload_hash:
            raise CapabilityBusinessError("idempotency_conflict", "idempotency key payload differs")
        return existing["result"]

    def require_rejectable_approval_order(self, *, order_gid, actor_gid, team_gid):
        order = self.orders.get(order_gid)
        if (
            order is None
            or order["team_gid"] != team_gid
            or order["reviewer_gid"] != actor_gid
        ):
            raise CapabilityBusinessError("not_found", "approval order not found")
        return order

    def reject_approval_order(self, *, order, comment, expected_revision):
        if order["revision"] != expected_revision:
            raise CapabilityBusinessError("version_conflict", "approval order revision changed")
        if order["status"] != "in_review":
            raise CapabilityBusinessError("invalid_state", "approval order cannot be rejected")
        order["status"] = "rejected"
        order["revision"] += 1
        order["opinions"].append({"action": "reject", "comment": comment})
        return order

    def enqueue_approval_rejection_notification(self, *, event_gid, order, team_gid):
        if self.fail_outbox:
            raise RuntimeError("outbox unavailable")
        self.notifications.append(
            {"gid": event_gid, "order_gid": order["gid"], "recipient_gid": order["applicant_gid"], "team_gid": team_gid}
        )

    def complete_approval_rejection(self, *, actor_gid, team_gid, idempotency_key, result):
        self.operations[(actor_gid, team_gid, "project.approval.order.reject@1", idempotency_key)]["result"] = deepcopy(result)

    def audit_approval_rejection(self, **event):
        self.audits.append(event)

    def count_notifications(self, event_gid):
        return sum(event["gid"] == event_gid for event in self.notifications)


class Registry:
    def __init__(self) -> None:
        self.items = []

    def register(self, spec, handler, *, descriptor=None):
        self.items.append((spec, handler, descriptor))


@pytest.fixture
def repository():
    return InMemoryApprovalRejectRepository()


@pytest.fixture
def application(repository):
    return ProjectManagementApplication(repository=repository, next_id=iter(("notification-1", "audit-1")).__next__)


@pytest.fixture
def context():
    return CapabilityContext(
        user_gid="reviewer-1",
        team_gid="team-1",
        confirmation_token="confirmed-1",
        idempotency_key="reject-1",
    )


@pytest.fixture
def command():
    return RejectOrder(order_gid="order-1", comment="Not ready", expected_revision=7)


def test_reject_commits_order_operation_audit_and_outbox_once(application, repository, command, context):
    first = application.reject_order(command, context)
    second = application.reject_order(command, context)

    assert first == second == {
        "order_gid": "order-1",
        "status": "rejected",
        "revision": 8,
        "notification_event_gid": "notification-1",
    }
    assert repository.orders["order-1"]["status"] == "rejected"
    assert len(repository.audits) == 1
    assert repository.count_notifications(first["notification_event_gid"]) == 1


def test_reject_revision_conflict_writes_nothing(application, repository, context):
    with pytest.raises(CapabilityBusinessError) as error:
        application.reject_order(
            RejectOrder(order_gid="order-1", comment="Not ready", expected_revision=6), context
        )

    assert error.value.code == "version_conflict"
    assert repository.orders["order-1"]["status"] == "in_review"
    assert repository.operations == {}
    assert repository.audits == []
    assert repository.notifications == []


def test_reject_same_idempotency_key_with_changed_payload_conflicts(application, repository, command, context):
    application.reject_order(command, context)

    with pytest.raises(CapabilityBusinessError) as error:
        application.reject_order(
            RejectOrder(order_gid="order-1", comment="Different reason", expected_revision=7), context
        )

    assert error.value.code == "idempotency_conflict"
    assert len(repository.notifications) == 1


def test_reject_cross_team_is_not_found(application, repository, command, context):
    with pytest.raises(CapabilityBusinessError) as error:
        application.reject_order(
            command,
            context.model_copy(update={"team_gid": "team-2", "idempotency_key": "reject-2"}),
        )

    assert error.value.code == "not_found"
    assert repository.orders["order-1"]["status"] == "in_review"


def test_reject_rolls_back_when_outbox_insert_fails(command, context):
    repository = InMemoryApprovalRejectRepository(fail_outbox=True)
    application = ProjectManagementApplication(repository=repository, next_id=lambda: "notification-1")

    with pytest.raises(RuntimeError, match="outbox unavailable"):
        application.reject_order(command, context)

    assert repository.orders["order-1"]["status"] == "in_review"
    assert repository.operations == {}
    assert repository.audits == []
    assert repository.notifications == []


def test_exact_reject_capability_has_closed_write_contract():
    registry = Registry()
    register_reviewed_capabilities(registry)
    spec, _, descriptor = next(
        item for item in registry.items if item[0].id == "project.approval.order.reject"
    )

    assert spec.version == 1
    assert spec.confirmation == "user"
    assert spec.input_schema == {
        "type": "object",
        "required": ["order_gid", "comment", "expected_revision"],
        "properties": {
            "order_gid": {"type": "string", "minLength": 1, "maxLength": 128},
            "comment": {"type": "string", "minLength": 1, "maxLength": 2000},
            "expected_revision": {"type": "integer", "minimum": 1},
        },
        "additionalProperties": False,
    }
    assert descriptor.idempotency_policy == "required"
    assert descriptor.consistency_policy == "external"
    assert descriptor.output_schema["required"] == [
        "order_gid", "status", "revision", "notification_event_gid"
    ]

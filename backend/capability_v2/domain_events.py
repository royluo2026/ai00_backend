"""Versioned domain-event contracts for independently owned databases."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Protocol

from pydantic import Field, model_validator

from .contracts import FrozenModel, IDENTITY_PATTERN
from .domain_manifest import DOMAIN_ID_PATTERN, EventSubscriptionManifest


EVENT_TYPE_PATTERN = (
    r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$"
)
AGGREGATE_TYPE_PATTERN = r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$"
RESERVED_PAYLOAD_FIELDS = frozenset(
    {
        "tenant_id",
        "tenant_gid",
        "producer_domain",
        "aggregate_id",
        "aggregate_version",
    }
)


class UnsupportedEventVersion(ValueError):
    """Raised before inbox processing when an event is not declared or supported."""


class DomainEventEnvelope(FrozenModel):
    event_id: str = Field(pattern=IDENTITY_PATTERN)
    event_type: str = Field(pattern=EVENT_TYPE_PATTERN)
    event_version: int = Field(ge=1)
    producer_domain: str = Field(pattern=DOMAIN_ID_PATTERN)
    tenant_id: str = Field(pattern=IDENTITY_PATTERN)
    aggregate_type: str = Field(pattern=AGGREGATE_TYPE_PATTERN)
    aggregate_id: str = Field(pattern=IDENTITY_PATTERN)
    aggregate_version: int = Field(ge=1)
    occurred_at: datetime
    payload: Mapping[str, Any]
    request_id: str = Field(pattern=IDENTITY_PATTERN)
    trace_id: str = Field(pattern=IDENTITY_PATTERN)
    causation_id: str = Field(pattern=IDENTITY_PATTERN)

    @model_validator(mode="after")
    def validate_closed_event_contract(self) -> "DomainEventEnvelope":
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        reserved = RESERVED_PAYLOAD_FIELDS.intersection(self.payload)
        if reserved:
            raise ValueError(
                f"reserved event payload field: {sorted(reserved)[0]}"
            )
        return self


class OutboxWriter(Protocol):
    def append(self, event: DomainEventEnvelope, *, transaction: object) -> None: ...


class InboxDeduplicator(Protocol):
    def begin(self, event_id: str, *, tenant_id: str) -> bool: ...

    def complete(self, event_id: str, *, tenant_id: str) -> None: ...

    def fail(self, event_id: str, *, tenant_id: str, error_code: str) -> None: ...


def supports_event_version(
    subscription: EventSubscriptionManifest,
    event: DomainEventEnvelope,
) -> bool:
    return (
        subscription.producer_domain == event.producer_domain
        and subscription.event_type == event.event_type
        and subscription.min_version <= event.event_version <= subscription.max_version
    )


def require_event_subscription(
    manifest: object,
    event: DomainEventEnvelope,
) -> EventSubscriptionManifest:
    subscriptions = getattr(manifest, "event_subscriptions", ())
    matching = tuple(
        subscription
        for subscription in subscriptions
        if subscription.producer_domain == event.producer_domain
        and subscription.event_type == event.event_type
    )
    if not matching:
        raise UnsupportedEventVersion("event_subscription_not_declared")
    for subscription in matching:
        if supports_event_version(subscription, event):
            return subscription
    raise UnsupportedEventVersion("event_version_unsupported")


__all__ = [
    "DomainEventEnvelope",
    "InboxDeduplicator",
    "OutboxWriter",
    "UnsupportedEventVersion",
    "require_event_subscription",
    "supports_event_version",
]

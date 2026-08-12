"""Durable cross-domain event delivery through declared subscriptions."""
from __future__ import annotations

from typing import Callable, Mapping, Protocol

from .domain_events import DomainEventEnvelope, UnsupportedEventVersion, supports_event_version


EventHandler = Callable[[DomainEventEnvelope], bool]


class DurableEventTransport:
    """Routes immutable envelopes only to manifest-declared Inbox handlers."""

    def __init__(self, consumer_manifests: Mapping[str, object], handlers: Mapping[str, EventHandler]):
        self._consumer_manifests = dict(consumer_manifests)
        self._handlers = dict(handlers)

    def deliver(self, event: DomainEventEnvelope) -> int:
        declared = []
        supported = []
        for manifest in self._consumer_manifests.values():
            for subscription in getattr(manifest, "event_subscriptions", ()):
                if subscription.producer_domain == event.producer_domain and subscription.event_type == event.event_type:
                    declared.append(subscription)
                    if supports_event_version(subscription, event):
                        supported.append(subscription)
        if not declared:
            raise UnsupportedEventVersion("event_subscription_not_declared")
        if not supported:
            raise UnsupportedEventVersion("event_version_unsupported")
        delivered = 0
        for subscription in supported:
            try:
                handler = self._handlers[subscription.subscription_id]
            except KeyError as exc:
                raise RuntimeError(f"event_handler_not_registered:{subscription.subscription_id}") from exc
            delivered += int(handler(event))
        return delivered


class OutboxPoller(Protocol):
    def poll(self, *, limit: int = 100) -> tuple[DomainEventEnvelope, ...]: ...
    def mark_delivered(self, event_id: str) -> None: ...
    def mark_failed(self, event_id: str, error: Exception) -> None: ...


def deliver_pending(poller: OutboxPoller, transport: DurableEventTransport, *, limit: int = 100) -> int:
    delivered = 0
    for event in poller.poll(limit=limit):
        try:
            transport.deliver(event)
        except Exception as exc:
            poller.mark_failed(event.event_id, exc)
            continue
        poller.mark_delivered(event.event_id)
        delivered += 1
    return delivered


__all__ = ["DurableEventTransport", "OutboxPoller", "deliver_pending"]

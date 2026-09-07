"""Best-effort wake signals for Connector plan workers.

Signals carry no plan data and are deliberately backed by normal lease polling:
missing a signal can delay work, but can never authorize or lose work.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from threading import Lock


class ConnectorWakeSubscription:
    def __init__(self, broker: "ConnectorWakeBroker", connector_id: str) -> None:
        self._broker = broker
        self.connector_id = connector_id
        self._loop: asyncio.AbstractEventLoop | None = None
        self._event: asyncio.Event | None = None

    async def __aenter__(self):
        self._loop = asyncio.get_running_loop()
        self._event = asyncio.Event()
        self._broker._add(self)
        return self

    async def __aexit__(self, *_args):
        self._broker._remove(self)

    def signal(self) -> None:
        if self._loop is not None and self._event is not None:
            self._loop.call_soon_threadsafe(self._event.set)

    async def wait(self, timeout_seconds: float) -> bool:
        if self._event is None:
            raise RuntimeError("connector_wake_subscription_not_started")
        try:
            await asyncio.wait_for(self._event.wait(), timeout_seconds)
        except TimeoutError:
            return False
        self._event.clear()
        return True


class ConnectorWakeBroker:
    def __init__(self) -> None:
        self._lock = Lock()
        self._subscriptions: dict[str, set[ConnectorWakeSubscription]] = defaultdict(set)

    def subscribe(self, connector_id: str) -> ConnectorWakeSubscription:
        return ConnectorWakeSubscription(self, connector_id)

    def notify(self, connector_id: str) -> None:
        with self._lock:
            subscriptions = tuple(self._subscriptions.get(connector_id, ()))
        for subscription in subscriptions:
            subscription.signal()

    def _add(self, subscription: ConnectorWakeSubscription) -> None:
        with self._lock:
            self._subscriptions[subscription.connector_id].add(subscription)

    def _remove(self, subscription: ConnectorWakeSubscription) -> None:
        with self._lock:
            subscriptions = self._subscriptions.get(subscription.connector_id)
            if subscriptions is None:
                return
            subscriptions.discard(subscription)
            if not subscriptions:
                self._subscriptions.pop(subscription.connector_id, None)


connector_wake_broker = ConnectorWakeBroker()

__all__ = ["ConnectorWakeBroker", "connector_wake_broker"]

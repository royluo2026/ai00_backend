from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.capability_v2.domain_events import (
    DomainEventEnvelope,
    UnsupportedEventVersion,
    require_event_subscription,
    supports_event_version,
)
from backend.capability_v2.domain_manifest import EventSubscriptionManifest


def valid_event(**overrides):
    values = {
        "event_id": "evt_1",
        "event_type": "factory.asset.scrapped",
        "event_version": 1,
        "producer_domain": "factory",
        "tenant_id": "tenant_1",
        "aggregate_type": "factory.asset",
        "aggregate_id": "asset_1",
        "aggregate_version": 7,
        "occurred_at": datetime.now(UTC),
        "payload": {"asset_ref": "factory-asset:asset_1"},
        "request_id": "req_1",
        "trace_id": "trace_1",
        "causation_id": "req_1",
    }
    values.update(overrides)
    return DomainEventEnvelope(**values)


def subscription(**overrides):
    values = {
        "subscription_id": "base.factory_assets",
        "producer_domain": "factory",
        "event_type": "factory.asset.scrapped",
        "min_version": 1,
        "max_version": 2,
    }
    values.update(overrides)
    return EventSubscriptionManifest(**values)


def test_event_requires_explicit_tenant_aggregate_version_and_correlation():
    event = valid_event()

    assert event.tenant_id == "tenant_1"
    assert event.aggregate_version == 7
    assert event.request_id == "req_1"
    assert event.trace_id == "trace_1"
    assert event.causation_id == "req_1"


@pytest.mark.parametrize(
    "reserved",
    ["tenant_id", "tenant_gid", "producer_domain", "aggregate_id", "aggregate_version"],
)
def test_event_rejects_reserved_identity_fields_in_payload(reserved):
    with pytest.raises(ValueError, match="reserved event payload field"):
        valid_event(payload={reserved: "forged"})


def test_event_requires_timezone_aware_occurrence():
    with pytest.raises(ValueError, match="occurred_at must be timezone-aware"):
        valid_event(occurred_at=datetime(2026, 8, 12, 12, 0))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("event_type", "factory.scrapped"),
        ("event_version", 0),
        ("aggregate_version", 0),
        ("request_id", ""),
        ("trace_id", ""),
        ("causation_id", ""),
    ],
)
def test_event_rejects_invalid_version_name_or_correlation(field, value):
    with pytest.raises(ValueError):
        valid_event(**{field: value})


def test_event_is_immutable():
    event = valid_event()

    with pytest.raises(ValueError):
        event.aggregate_version = 8


def test_subscription_accepts_only_declared_type_producer_and_version():
    declared = subscription()

    assert supports_event_version(declared, valid_event(event_version=2)) is True
    assert supports_event_version(declared, valid_event(event_version=3)) is False
    assert supports_event_version(
        declared,
        valid_event(producer_domain="knowledge"),
    ) is False
    assert supports_event_version(
        declared,
        valid_event(event_type="factory.asset.repaired"),
    ) is False


def test_require_event_subscription_returns_matching_declaration():
    declared = subscription()
    manifest = SimpleNamespace(event_subscriptions=(declared,))

    assert require_event_subscription(manifest, valid_event(event_version=2)) is declared


def test_undeclared_event_fails_with_stable_reason():
    manifest = SimpleNamespace(event_subscriptions=())

    with pytest.raises(UnsupportedEventVersion, match="event_subscription_not_declared"):
        require_event_subscription(manifest, valid_event())


def test_declared_event_with_unsupported_version_fails_with_stable_reason():
    manifest = SimpleNamespace(event_subscriptions=(subscription(),))

    with pytest.raises(UnsupportedEventVersion, match="event_version_unsupported"):
        require_event_subscription(manifest, valid_event(event_version=3))

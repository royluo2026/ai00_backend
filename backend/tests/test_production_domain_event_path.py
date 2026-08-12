from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.base.inbox import MemoryBaseProjectionStore
from backend.capability_v2.domain_events import DomainEventEnvelope, UnsupportedEventVersion
from backend.capability_v2.event_transport import DurableEventTransport
from backend.capability_v2.domain_manifest import EventSubscriptionManifest


def _event(*, version: int = 1) -> DomainEventEnvelope:
    return DomainEventEnvelope(
        event_id="evt_knowledge_1", event_type="knowledge.document.published",
        event_version=version, producer_domain="knowledge", tenant_id="tenant_1",
        aggregate_type="knowledge.document", aggregate_id="doc_1", aggregate_version=1,
        occurred_at=datetime.now(UTC), payload={"document_ref": "knowledge-document:doc_1", "revision_ref": "knowledge-revision:rev_1"},
        request_id="req_1", trace_id="trace_1", causation_id="req_1",
    )


def _base_manifest():
    return SimpleNamespace(event_subscriptions=(EventSubscriptionManifest(
        subscription_id="base.knowledge_documents", producer_domain="knowledge",
        event_type="knowledge.document.published", min_version=1, max_version=1,
    ),))


def test_knowledge_publication_reaches_base_once():
    base = MemoryBaseProjectionStore()
    transport = DurableEventTransport({"base": _base_manifest()}, {"base.knowledge_documents": base.handle})

    transport.deliver(_event())
    transport.deliver(_event())

    assert base.inbox_count("evt_knowledge_1") == 1
    assert base.projection_count(subject_ref="knowledge-document:doc_1") == 1


def test_unsupported_event_version_is_explicit_and_not_projected():
    base = MemoryBaseProjectionStore()
    transport = DurableEventTransport({"base": _base_manifest()}, {"base.knowledge_documents": base.handle})

    with pytest.raises(UnsupportedEventVersion, match="event_version_unsupported"):
        transport.deliver(_event(version=2))
    assert base.inbox_count("evt_knowledge_1") == 0


def test_transient_failure_can_be_replayed_without_duplicate_projection():
    base = MemoryBaseProjectionStore(failures_before_success=1)
    transport = DurableEventTransport({"base": _base_manifest()}, {"base.knowledge_documents": base.handle})

    with pytest.raises(RuntimeError, match="transient"):
        transport.deliver(_event())
    transport.deliver(_event())
    transport.deliver(_event())

    assert base.inbox_count("evt_knowledge_1") == 1
    assert base.projection_count(subject_ref="knowledge-document:doc_1") == 1

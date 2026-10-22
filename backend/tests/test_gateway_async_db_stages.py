"""Gateway DB waits must not hold the server event loop or abandon owned writes."""
from __future__ import annotations

import asyncio
import threading

import pytest

from backend.capability_v2.authorization import AuthorizationDecision
from backend.capability_v2.contracts import SideEffectLevel
from backend.capability_v2.outcomes import InMemoryOutcomeStore
from backend.capability_v2.reliability import (
    InMemoryRateLimiter, ReliabilityCoordinator, TransactionalCapabilityOutput,
    transactional_provider,
)
from backend.tests.test_capability_gateway_pipeline import _descriptor, _envelope, _gateway


class _BlockedStage:
    def __init__(self, stage):
        self.stage = stage
        self.started = threading.Event()
        self.release = threading.Event()
        self.finished = threading.Event()
        self.threads = []
        self.fail = None

    def visit(self, stage):
        self.threads.append((stage, threading.get_ident()))
        if stage == self.stage:
            self.started.set()
            self.release.wait(1.0)  # Bound a broken event-loop implementation's wait.
            self.finished.set()
        if stage == self.fail:
            raise RuntimeError("database unit failed")


def _blocked_gateway(stage):
    blocked = _BlockedStage(stage)
    store = InMemoryOutcomeStore()

    class Policy:
        def authorize(self, *_args):
            blocked.visit("authorize")
            return AuthorizationDecision(allowed=True, code="allowed", policy_version="test")
        def approve(self, *_args): blocked.visit("approve")
        def project(self, _descriptor, _identity, data): return data

    class Reliability(ReliabilityCoordinator):
        def replay(self, *args, **kwargs):
            blocked.visit("replay")
            return super().replay(*args, **kwargs)
        def begin(self, *args, **kwargs):
            blocked.visit("begin")
            return super().begin(*args, **kwargs)
        def complete(self, *args, **kwargs):
            blocked.visit("complete")
            return super().complete(*args, **kwargs)
        def mark_unknown(self, *args, **kwargs):
            blocked.visit("unknown")
            return super().mark_unknown(*args, **kwargs)

    class Transaction:
        def commit(self): blocked.visit("commit")
        def rollback(self): blocked.visit("rollback")
        def close(self): blocked.visit("close")

    @transactional_provider
    def provider(*_args):
        blocked.visit("provider")
        return TransactionalCapabilityOutput({"routing_id": "routing_1"}, Transaction())

    descriptor = _descriptor().model_copy(update={
        "side_effect_level": SideEffectLevel.WRITE, "idempotency_policy": "required",
    })
    gateway, release = _gateway(descriptor, provider, Policy(), Reliability(store, InMemoryRateLimiter(limit=100)))
    return gateway, _envelope(release).model_copy(update={"idempotency_key": "blocked"}), blocked, store


async def _wait_started(blocked):
    async with asyncio.timeout(2):
        while not blocked.started.is_set():
            await asyncio.sleep(0)


@pytest.mark.parametrize("stage", ["authorize", "replay", "approve", "begin", "complete", "commit"])
def test_database_stage_allows_unrelated_gateway_read(stage):
    async def scenario():
        gateway, envelope, blocked, _store = _blocked_gateway(stage)
        pending = asyncio.create_task(gateway.invoke(envelope))
        try:
            await _wait_started(blocked)
            class ReadPolicy:
                def authorize(self, *_args): return None
                def approve(self, *_args): pass
                def project(self, _descriptor, _identity, data): return data
            async def read(*_args): return {"routing_id": "unrelated"}
            reader, release = _gateway(_descriptor(), read, ReadPolicy())
            result = await reader.invoke(_envelope(release))
            assert result.ok
            assert not blocked.finished.is_set(), f"{stage} blocked the unrelated read"
        finally:
            blocked.release.set()
            await pending
    asyncio.run(scenario())


@pytest.mark.parametrize("stage", ["complete", "commit"])
def test_cancelled_request_drains_finalization_and_returns_actual_commit(stage, monkeypatch):
    async def scenario():
        gateway, envelope, blocked, store = _blocked_gateway(stage)
        releases = []
        original_release = gateway._admission._release
        async def release(*args):
            releases.append(args)
            await original_release(*args)
        monkeypatch.setattr(gateway._admission, "_release", release)
        pending = asyncio.create_task(gateway.invoke(envelope))
        try:
            await _wait_started(blocked)
            assert not blocked.finished.is_set()
            assert gateway._admission.in_flight("craft.routing.get@1") == 1
            pending.cancel()
            await asyncio.sleep(0.01)
            pending.cancel()
            await asyncio.sleep(0.01)
            assert not pending.done()
        finally:
            blocked.release.set()
        result = await pending
        assert result.ok and result.status.value == "completed"
        assert store.snapshot()[0].status == "completed"
        assert gateway._admission.in_flight("craft.routing.get@1") == 0
        assert len(releases) == 1
        finalizer_threads = [thread for name, thread in blocked.threads if name in {"complete", "commit", "close"}]
        assert len(finalizer_threads) == 3 and len(set(finalizer_threads)) == 1
        assert finalizer_threads[0] != threading.get_ident()
    asyncio.run(scenario())


@pytest.mark.parametrize("stage", ["complete", "commit"])
def test_cancelled_finalization_failure_rolls_back_marks_unknown_and_closes(stage):
    async def scenario():
        gateway, envelope, blocked, store = _blocked_gateway(stage)
        blocked.fail = stage
        pending = asyncio.create_task(gateway.invoke(envelope))
        try:
            await _wait_started(blocked)
            assert not blocked.finished.is_set()
            pending.cancel()
            await asyncio.sleep(0.01)
            assert not pending.done()
        finally:
            blocked.release.set()
        result = await pending
        assert not result.ok and result.status.value == "outcome_unknown"
        assert result.error.code == "outcome_persistence_failed"
        assert store.snapshot()[0].status == "outcome_unknown"
        names = [name for name, _thread in blocked.threads]
        assert names[-3:] == ["rollback", "unknown", "close"]
        owned_threads = [thread for name, thread in blocked.threads if name in {"complete", "commit", "rollback", "unknown", "close"}]
        assert len(set(owned_threads)) == 1
        assert owned_threads[0] != threading.get_ident()
    asyncio.run(scenario())


def test_cancellation_during_approval_never_dispatches_provider():
    async def scenario():
        gateway, envelope, blocked, store = _blocked_gateway("approve")
        pending = asyncio.create_task(gateway.invoke(envelope))
        try:
            await _wait_started(blocked)
            assert not blocked.finished.is_set()
            pending.cancel()
            await asyncio.sleep(0.01)
            assert not pending.done()
        finally:
            blocked.release.set()
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert store.snapshot() == ()
        assert not any(name == "provider" for name, _thread in blocked.threads)
    asyncio.run(scenario())


def test_cancellation_during_begin_terminalizes_lease_without_dispatch():
    async def scenario():
        gateway, envelope, blocked, store = _blocked_gateway("begin")
        pending = asyncio.create_task(gateway.invoke(envelope))
        try:
            await _wait_started(blocked)
            assert not blocked.finished.is_set()
            pending.cancel()
            await asyncio.sleep(0.01)
            assert not pending.done()
        finally:
            blocked.release.set()
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert not any(name == "provider" for name, _thread in blocked.threads)
        assert store.snapshot()[0].status == "failed"
        assert store.snapshot()[0].result.error.code == "cancelled_before_dispatch"
    asyncio.run(scenario())

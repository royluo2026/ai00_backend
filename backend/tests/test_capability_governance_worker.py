from datetime import UTC, datetime, timedelta

from backend.capability_governance_test.worker import InMemoryRunLeaseStore, LeasedGovernanceWorker


def test_only_one_worker_executes_a_live_run_and_completion_is_idempotent():
    leases = InMemoryRunLeaseStore()
    leases.queue("analysis", "100")
    first = LeasedGovernanceWorker(leases, worker_id="worker-a")
    second = LeasedGovernanceWorker(leases, worker_id="worker-b")
    completed = []

    assert first.run_once("analysis", "100", lambda: completed.append("a")) is True
    assert second.run_once("analysis", "100", lambda: completed.append("b")) is False
    assert first.complete("analysis", "100") is False
    assert completed == ["a"]


def test_worker_renews_lease_and_requeues_an_expired_run():
    now = datetime(2026, 8, 18, tzinfo=UTC)
    leases = InMemoryRunLeaseStore(clock=lambda: now)
    leases.queue("test", "200")
    worker = LeasedGovernanceWorker(leases, worker_id="worker-a", lease_seconds=10)

    assert worker.acquire("test", "200") is True
    assert worker.renew("test", "200") is True
    leases.expire("test", "200", now + timedelta(seconds=11))

    assert leases.status("test", "200") == "queued"

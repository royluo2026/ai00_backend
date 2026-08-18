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


def test_long_running_work_renews_before_another_worker_can_claim_with_fake_clock():
    now = [datetime(2026, 8, 18, tzinfo=UTC)]
    leases = InMemoryRunLeaseStore(clock=lambda: now[0])
    leases.queue("analysis", "300")
    first = LeasedGovernanceWorker(leases, worker_id="worker-a", lease_seconds=10)
    second = LeasedGovernanceWorker(leases, worker_id="worker-b", lease_seconds=10)

    def execute(heartbeat):
        now[0] += timedelta(seconds=9)
        assert heartbeat() is True
        now[0] += timedelta(seconds=9)
        assert heartbeat() is True
        assert second.acquire("analysis", "300") is False

    assert first.run_once("analysis", "300", execute) is True


def test_sql_completion_requeues_an_expired_lease_without_completing_it():
    from backend.capability_governance_test.worker import SqlRunLeaseStore

    statements = []

    class Cursor:
        rowcount = 0
        def execute(self, statement, values):
            statements.append((statement, values))
        def close(self):
            return None

    class Connection:
        def cursor(self): return Cursor()
        def commit(self): return None
        def rollback(self): return None

    store = SqlRunLeaseStore(lambda: Connection(), clock=lambda: datetime(2026, 8, 18, tzinfo=UTC))

    assert store.complete("analysis", "300", "worker-a") is False
    assert "lease_expires_at > %s" in statements[0][0]
    assert statements[1][1][0] == "queued"


def test_sql_acquire_creates_queue_row_denies_live_competitor_and_reclaims_expiry():
    from backend.capability_governance_test.worker import SqlRunLeaseStore

    now = [datetime(2026, 8, 18, tzinfo=UTC)]
    rows = {}

    class Cursor:
        rowcount = 0
        def execute(self, statement, values):
            if statement.startswith("INSERT INTO"):
                _, kind, run_gid, status, _, _, _, _ = values
                rows.setdefault((kind, run_gid), {"status": status, "worker_id": None, "expires": None})
                self.rowcount = 1
            elif "SET status=%s, worker_id=%s, lease_expires_at=%s" in statement:
                _, worker_id, expiry, _, kind, run_gid, observed = values
                row = rows[(kind, run_gid)]
                eligible = row["status"] == "queued" or (
                    row["status"] == "running" and row["expires"] <= observed
                )
                if eligible:
                    row.update(status="running", worker_id=worker_id, expires=expiry)
                    self.rowcount = 1
                else:
                    self.rowcount = 0
        def close(self): return None

    class Connection:
        def cursor(self): return Cursor()
        def commit(self): return None
        def rollback(self): return None

    store = SqlRunLeaseStore(lambda: Connection(), clock=lambda: now[0], next_ids=lambda: 9001)

    assert store.acquire("analysis", "300", "worker-a", lease_seconds=10) is True
    assert store.acquire("analysis", "300", "worker-b", lease_seconds=10) is False
    now[0] += timedelta(seconds=11)
    assert store.acquire("analysis", "300", "worker-b", lease_seconds=10) is True

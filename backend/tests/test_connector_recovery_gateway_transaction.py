"""Real Gateway + Simulation SQL + SQL reliability enlistment (isolated SQLite)."""
import asyncio
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import json
import sqlite3
import threading

import pytest

from backend.tests.test_simulation_connector_runtime_v2_sql import (
    database, recovery_case, read, SQLiteConnection, SQLiteCursor, NOW,
)
from backend.capabilities.registry_next import CapabilityRegistry
from backend.capability_v2.authorization import AuthorizationGrants
from backend.capability_v2.catalog import CatalogResolver, build_release
from backend.capability_v2.catalog_store import InMemoryCatalogStore
from backend.capability_v2.contracts import (
    ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType, InvocationEnvelope, TenantIdentity,
)
from backend.capability_v2.gateway import CapabilityGatewayService
from backend.capability_v2.identity import DESKTOP_CONSUMER_ID
from backend.capability_v2.outcomes import SqlOutcomeStore
from backend.capability_v2.policies import LegacyServerGatewayPolicy
from backend.capability_v2.reliability import ApprovalService, InMemoryApprovalStore, InMemoryRateLimiter, ReliabilityCoordinator
from plugins.simulation.simulation_backend.capabilities.connector_runtime import ConnectorControlPlane, register_connector_runtime_capabilities
from plugins.simulation.simulation_backend.data import connection as simulation_connection
from plugins.simulation.simulation_backend.data.connector_repository import SimulationConnectorRepository


class GatewayCursor(SQLiteCursor):
    def fetchone(self):
        row = super().fetchone()
        if row:
            for name in ('started_at', 'completed_at'):
                if isinstance(row.get(name), str):
                    row[name] = datetime.fromisoformat(row[name])
        return row


class GatewayConnection(SQLiteConnection):
    def cursor(self):
        return GatewayCursor(self.connection)

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        self.connection.close()


@pytest.fixture
def recovery_gateway(database, monkeypatch):
    with database[0]() as connection:
        if not isinstance(connection, SQLiteConnection):
            pytest.skip('Gateway transaction boundary fixture is isolated SQLite')
        path = connection.connection.execute('PRAGMA database_list').fetchone()[2]
    args = recovery_case(database)

    def open_transaction():
        raw = sqlite3.connect(path, check_same_thread=False, timeout=5)
        raw.row_factory = sqlite3.Row
        raw.execute('BEGIN IMMEDIATE')
        return GatewayConnection(raw)

    @contextmanager
    def connections():
        connection = open_transaction()
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    monkeypatch.setattr(simulation_connection, 'open_simulation_transaction', open_transaction, raising=False)
    with connections() as connection, connection.cursor() as cur:
        cur.execute('CREATE TABLE workmanship_base_capability_outcomes ('
            'operation_id TEXT PRIMARY KEY,request_id TEXT,idempotency_scope TEXT UNIQUE,payload_hash TEXT,'
            'capability_id TEXT,major_version INTEGER,tenant_id TEXT,consumer_scope TEXT,actor_id TEXT,'
            'consumer_type TEXT,consumer_id TEXT,consumer_instance_id TEXT,policy_version TEXT,status TEXT,'
            'result_json TEXT,started_at TEXT,completed_at TEXT)')
        cur.execute('CREATE TABLE workmanship_base_capability_audit_outbox ('
            'event_id TEXT PRIMARY KEY,operation_id TEXT UNIQUE,event_type TEXT,payload_json TEXT,'
            'created_at TEXT,delivered_at TEXT,attempt_count INTEGER DEFAULT 0,last_error_code TEXT)')
    registry = CapabilityRegistry()
    register_connector_runtime_capabilities(registry, ConnectorControlPlane(SimulationConnectorRepository(), clock=lambda: NOW))
    descriptor = registry.get('simulation.connector.recovery.resolve', 1).descriptor
    release = build_release([descriptor])
    catalogs = InMemoryCatalogStore()
    catalogs.publish(release)
    approvals = ApprovalService(InMemoryApprovalStore())
    grants = AuthorizationGrants(permissions=('simulation.use',), resource_scopes=('*',),
        data_scopes=('confidential',), policy_version='recovery-test-1', tenant_id='tenant-001')
    policy = LegacyServerGatewayPolicy(lambda user: {'gid': user, 'is_active': True}, lambda *_: grants, approvals)
    gateway = CapabilityGatewayService(CatalogResolver(catalogs, registry), policy,
        reliability=ReliabilityCoordinator(SqlOutcomeStore(connections), InMemoryRateLimiter(limit=100))).bind_release(release.release_id)
    identity = ConsumerIdentity(
        actor=ActorIdentity(user_id='user-001', authentication_method='jwt', authenticated_at=datetime.now(UTC)),
        tenant=TenantIdentity(tenant_id='tenant-001', membership='member', active_roles=('member',)),
        consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id=DESKTOP_CONSUMER_ID))
    envelope = InvocationEnvelope(capability_id=descriptor.id, major_version=1, catalog_release=release.release_id,
        payload={k:v for k,v in args.items() if k not in {'actor_id','tenant_id','now'}}, identity=identity,
        request_id='recovery-transaction-test', trace_id='recovery-transaction-test', idempotency_key='recovery-transaction-test')
    return gateway, envelope, connections, policy


def confirmed_invoke(gateway, envelope):
    async def run():
        approval = await gateway.request_approval(envelope)
        confirmed = envelope.model_copy(update={'approval_reference': approval.token})
        return await gateway.invoke(confirmed), confirmed
    return asyncio.run(run())


@pytest.mark.parametrize('identity_kind', ['expected_plan_hash', 'expected_recovery_fingerprint'])
def test_recovery_gateway_plan_hash_only_abandonment_binds_confirmation(database, recovery_gateway, identity_kind):
    gateway, envelope, connections, _ = recovery_gateway
    before = read(database, 'runtime_plans')
    with connections() as conn, conn.cursor() as cur:
        cur.execute('UPDATE workmanship_sim_connector_runtime_plans SET outcome_hash=NULL WHERE plan_id=%s', (before['plan_id'],))
        if identity_kind == 'expected_recovery_fingerprint':
            cur.execute('UPDATE workmanship_sim_connector_runtime_plans SET plan_hash=%s,plan_json=%s WHERE plan_id=%s',
                        ('', '{invalid json', before['plan_id']))
    payload = dict(envelope.payload, decision='abandoned', expected_plan_hash='sha256:' + before['plan_hash'])
    payload.pop('expected_outcome_hash')
    if identity_kind == 'expected_recovery_fingerprint':
        payload.pop('expected_plan_hash')
        payload[identity_kind] = SimulationConnectorRepository().search_manual_recovery(
            actor_id='user-001', tenant_id='tenant-001')['items'][0]['recovery_fingerprint']
    from plugins.simulation.simulation_backend.capabilities.connector_contracts import INPUT_SCHEMAS
    import jsonschema
    for name in ('expected_outcome_hash', 'expected_plan_hash', 'expected_recovery_fingerprint'):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(dict(payload, **{name: None}), INPUT_SCHEMAS['simulation.connector.recovery.resolve'])
    envelope = envelope.model_copy(update={'payload': payload})
    approval = asyncio.run(gateway.request_approval(envelope))
    changed = envelope.model_copy(update={'approval_reference': approval.token,
        'payload': dict(payload, **{identity_kind: 'sha256:' + '0'*64})})
    denied = asyncio.run(gateway.invoke(changed))
    assert not denied.ok and denied.error.code == 'confirmation_rejected'
    assert read(database, 'runtime_plans')['status'] == 'outcome_unknown'
    result, confirmed = confirmed_invoke(gateway, envelope)
    assert result.ok, result.error
    assert result.data['decision'] == 'abandoned' and result.data['retry_started'] is False
    assert asyncio.run(gateway.invoke(confirmed)).data == result.data
    after = read(database, 'runtime_plans')
    assert after['status'] == 'cancelled' and after['outcome_hash'] is None
    assert after['outcome_json'] == before['outcome_json']


@pytest.mark.parametrize('decision', ['not_executed', 'abandoned'])
def test_recovery_gateway_confirmation_commits_outcome_audit_and_replays(database, recovery_gateway, decision):
    gateway, envelope, connections, _ = recovery_gateway
    envelope = envelope.model_copy(update={'payload': dict(envelope.payload, decision=decision)})
    before = read(database, 'runtime_plans')
    result, confirmed = confirmed_invoke(gateway, envelope)
    assert result.ok, result.error
    assert result.data['retry_started'] is False
    replay = asyncio.run(gateway.invoke(confirmed))
    assert replay.ok and replay.data == result.data and replay.operation_ref == result.operation_ref
    after = read(database, 'runtime_plans')
    assert after['status'] == 'cancelled'
    assert (after['outcome_json'], after['outcome_hash']) == (before['outcome_json'], before['outcome_hash'])
    with connections() as connection, connection.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS count FROM workmanship_sim_connector_runtime_audit WHERE event_type='human_recovery_disposition'")
        assert cur.fetchone()['count'] == 1
        cur.execute('SELECT * FROM workmanship_base_capability_outcomes')
        outcome = cur.fetchone()
        assert outcome['status'] == 'completed'
        assert json.loads(outcome['result_json'])['data']['audit_ref'] == result.data['audit_ref']
        cur.execute('SELECT * FROM workmanship_base_capability_audit_outbox')
        assert cur.fetchone()['operation_id'] == outcome['operation_id']


@pytest.mark.parametrize('failure', ['outbox', 'projection'])
@pytest.mark.parametrize('decision', ['not_executed', 'abandoned'])
def test_recovery_gateway_failure_rolls_back_plan_and_human_audit(database, recovery_gateway, failure, decision):
    gateway, envelope, connections, policy = recovery_gateway
    envelope = envelope.model_copy(update={'payload': dict(envelope.payload, decision=decision)})
    before = read(database, 'runtime_plans')
    if failure == 'outbox':
        with connections() as connection, connection.cursor() as cur:
            cur.execute("CREATE TRIGGER fail_recovery_outbox BEFORE INSERT ON workmanship_base_capability_audit_outbox "
                        "BEGIN SELECT RAISE(ABORT,'injected outbox failure'); END")
    else:
        def reject_projection(*args):
            raise ValueError('injected projection failure')
        policy.project = reject_projection
    result, _ = confirmed_invoke(gateway, envelope)
    assert not result.ok
    assert result.error.code == ('outcome_persistence_failed' if failure == 'outbox' else 'provider_failed')
    assert read(database, 'runtime_plans') == before
    with connections() as connection, connection.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS count FROM workmanship_sim_connector_runtime_audit WHERE event_type='human_recovery_disposition'")
        assert cur.fetchone()['count'] == 0
        cur.execute("SELECT COUNT(*) AS count FROM workmanship_base_capability_outcomes WHERE status='completed'")
        assert cur.fetchone()['count'] == 0


@pytest.mark.parametrize('decision', ['executed', 'abandoned'])
def test_recovery_gateway_refuses_unconfirmed_and_changed_confirmation(database, recovery_gateway, decision):
    gateway, envelope, _, _ = recovery_gateway
    before = read(database, 'runtime_plans')
    denied = asyncio.run(gateway.invoke(envelope))
    assert not denied.ok and denied.error.code == 'confirmation_required'
    approval = asyncio.run(gateway.request_approval(envelope))
    changed = envelope.model_copy(update={'approval_reference':approval.token,
        'payload':dict(envelope.payload, decision=decision)})
    denied = asyncio.run(gateway.invoke(changed))
    assert not denied.ok and denied.error.code == 'confirmation_rejected'
    assert read(database, 'runtime_plans') == before


@pytest.mark.parametrize('abandonment', ['timeout', 'cancel'])
def test_recovery_gateway_cleans_late_transaction_without_commit(database, recovery_gateway, abandonment):
    from backend.capability_v2.reliability import transactional_provider
    original_gateway, envelope, connections, policy = recovery_gateway
    descriptor, provider = original_gateway._resolve_envelope(envelope)
    entered, release, returned, closed = (threading.Event() for _ in range(4))
    calls, cleanup = [], []

    @transactional_provider
    def delayed_handler(payload, context):
        entered.set()
        if not release.wait(5):
            raise RuntimeError('test did not release provider')
        output = provider.handler(payload, context)
        transaction = output.transaction
        commit, rollback, close = transaction.commit, transaction.rollback, transaction.close
        cleanup.append(lambda: (rollback(), close()))
        def tracked_commit():
            calls.append('commit')
            commit()
        def tracked_rollback():
            calls.append('rollback')
            rollback()
        def tracked_close():
            calls.append('close')
            close()
            closed.set()
        transaction.commit, transaction.rollback, transaction.close = tracked_commit, tracked_rollback, tracked_close
        returned.set()
        return output

    registry = CapabilityRegistry()
    registry.register(provider.spec, delayed_handler, descriptor=descriptor)
    catalogs = InMemoryCatalogStore()
    catalogs.publish(original_gateway.catalog())
    gateway = CapabilityGatewayService(CatalogResolver(catalogs, registry), policy,
        reliability=ReliabilityCoordinator(SqlOutcomeStore(connections), InMemoryRateLimiter(limit=100))).bind_release(envelope.catalog_release)
    before = read(database, 'runtime_plans')

    async def run():
        approval = await gateway.request_approval(envelope)
        confirmed = envelope.model_copy(update={'approval_reference': approval.token,
            'deadline': datetime.now(UTC) + timedelta(seconds=0.3 if abandonment == 'timeout' else 5)})
        invocation = asyncio.create_task(gateway.invoke(confirmed))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            # The event loop must remain responsive while the synchronous worker waits.
            await asyncio.sleep(0)
            assert not release.is_set() and not invocation.done()
            if abandonment == 'cancel':
                invocation.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await invocation
            else:
                result = await asyncio.wait_for(invocation, timeout=1)
                assert not result.ok and result.error.code == 'runtime_timeout'
            assert not release.is_set()
            release.set()
            assert await asyncio.to_thread(returned.wait, 2)
            assert await asyncio.to_thread(closed.wait, 2), 'late transaction was orphaned'
            assert calls == ['rollback', 'close']
        finally:
            release.set()
            await asyncio.to_thread(returned.wait, 2)
            if not closed.is_set():
                for clean in cleanup:
                    clean()
    asyncio.run(run())
    assert read(database, 'runtime_plans') == before
    with connections() as connection, connection.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS count FROM workmanship_sim_connector_runtime_audit WHERE event_type='human_recovery_disposition'")
        assert cur.fetchone()['count'] == 0
        cur.execute("SELECT COUNT(*) AS count FROM workmanship_base_capability_outcomes WHERE status='completed'")
        assert cur.fetchone()['count'] == 0

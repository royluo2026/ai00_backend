"""A bounded v2 lease can cover a 600 second operation without relaxing fences."""
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.routers import simulation_connector as transport
from plugins.simulation.simulation_backend.application.connector_runtime_sessions import RuntimeSessionService
from plugins.simulation.simulation_backend.data import connector_repository as persistence

NOW = datetime(2026, 10, 15, tzinfo=UTC)


def test_v2_http_accepts_600_seconds_but_remains_bounded():
    body_type = transport.runtime_lease.__annotations__['body']
    if isinstance(body_type, str):
        body_type = getattr(transport, body_type)
    assert body_type(lease_seconds=600).lease_seconds == 600
    with pytest.raises(ValidationError):
        body_type(lease_seconds=601)
    with pytest.raises(ValidationError):
        transport.ConnectorLeaseBody(lease_seconds=600)


@pytest.mark.parametrize('requested,session_seconds,plan_seconds,expected', [
    (600, 660, 900, 600), (999999, 660, 900, 600),
    (600, 450, 900, 450), (600, 660, 400, 400),
])
def test_repository_lease_honors_both_session_and_signed_plan_expiry(monkeypatch, requested, session_seconds, plan_seconds, expected):
    class Cursor:
        rowcount = 0
        def execute(self, sql, params):
            self.rowcount = 1 if "status='leased',lease_id" in sql else 0
        def fetchone(self):
            return {'plan_id': 'plan', 'plan_json': '{}', 'expires_at': NOW + timedelta(seconds=plan_seconds)}
        def __enter__(self): return self
        def __exit__(self, *_): return False
    cursor = Cursor()
    monkeypatch.setattr(persistence, 'get_simulation_conn', lambda: nullcontext(SimpleNamespace(cursor=lambda: cursor)))
    repository = persistence.SimulationConnectorRepository()
    monkeypatch.setattr(repository, '_authenticated_runtime', lambda *_: {'session_token_hash': 'hash', 'session_expires_at': NOW + timedelta(seconds=session_seconds)})
    monkeypatch.setattr(repository, '_has_unresolved_plans', lambda *_: False)
    monkeypatch.setattr(repository, '_runtime_audit', lambda *_args, **_kwargs: None)
    leased = repository.lease_v2_plan('device', 1, 'runtime', 'token', NOW, requested)
    assert leased['lease_until'] == NOW + timedelta(seconds=expected)


def test_normal_runtime_session_renewal_has_bounded_execution_and_delivery_margin():
    expiries = []
    def record(*args):
        expiries.append(args[-1])
        return {'expires_at': args[-1]}
    repository = SimpleNamespace(register_runtime_session=record, renew_runtime=record, restart_runtime_session=record)
    service = RuntimeSessionService(repository, clock=lambda: NOW)
    service._prove = lambda *_args, **_kwargs: None
    service.register('device', 1, 'runtime', device_credential='credential', runtime_type='electron', challenge='challenge', signature='signature')
    pins = dict(device_id='device', generation=1, runtime_instance_id='runtime')
    service.renew('token', **pins)
    service.restart('next-runtime', 'token', **pins)
    assert expiries == [NOW + timedelta(seconds=660)] * 3


def test_local_tc_open_signed_plan_already_covers_the_maximum_lease():
    from plugins.simulation.simulation_backend.capabilities.connector_runtime import _direct_vismockup_plan_v2
    context = SimpleNamespace(team_gid='tenant', user_gid='user', capability_version_gid='cv2_test',
        business_definition_hash='sha256:'+'a'*64, catalog_release='rel_test', request_id='request',
        idempotency_key='key', normalized_input_hash='sha256:'+'b'*64)
    plan = _direct_vismockup_plan_v2(action='cache_tc_open', connector_id='device', payload={}, context=context, now=NOW)
    assert plan['steps'][0]['timeout_seconds'] == 600
    assert datetime.fromisoformat(plan['expires_at'].replace('Z', '+00:00')) == NOW + timedelta(seconds=900)


def test_recovery_sessions_keep_their_shorter_bound():
    expiries = []
    def record(*args, **kwargs):
        expiries.append(args[-1])
        return {}
    service = RuntimeSessionService(SimpleNamespace(register_reconciliation_session=record), clock=lambda: NOW)
    service._prove = lambda *_args, **_kwargs: None
    service.register_reconciliation('device', 1, 'runtime', device_credential='credential', runtime_type='electron',
        challenge='challenge', signature='signature', plan_id='plan')
    assert expiries == [NOW + timedelta(seconds=300)]


@pytest.mark.parametrize('operation', ['register', 'renew', 'restart', 'takeover'])
@pytest.mark.parametrize('seconds', [-1, 0, 660, 661])
def test_real_session_persistence_accepts_660_and_rejects_661(monkeypatch, operation, seconds):
    class Cursor:
        rowcount = 1
        def execute(self, sql, params): pass
        def fetchall(self): return []
        def __enter__(self): return self
        def __exit__(self, *_): return False
    cursor = Cursor()
    monkeypatch.setattr(persistence, 'get_simulation_conn', lambda: nullcontext(SimpleNamespace(cursor=lambda: cursor)))
    repository = persistence.SimulationConnectorRepository()
    row = dict(device_id='device', runtime_generation=1, current_runtime_instance_id='prior',
        session_token_hash='hash', session_expires_at=NOW-timedelta(seconds=1))
    monkeypatch.setattr(repository, '_locked_runtime', lambda *_: row)
    monkeypatch.setattr(repository, '_authenticated_runtime', lambda *_: row)
    monkeypatch.setattr(repository, '_has_unresolved_plans', lambda *_: False)
    monkeypatch.setattr(repository, '_retire_restart_safe_read_plans', lambda *_args, **_kwargs: None)
    expiry = NOW + timedelta(seconds=seconds)
    def invoke():
        if operation == 'register': return repository.register_runtime_session('device', 1, 'next', NOW, expiry)
        if operation == 'renew': return repository.renew_runtime('device', 1, 'prior', 'token', NOW, expiry)
        if operation == 'restart': return repository.restart_runtime_session('device', 1, 'prior', 'token', 'next', NOW, expiry)
        return repository.force_takeover('device', 1, 2, 'next', NOW, expiry,
            expected_runtime_instance_id='prior', expected_session_token_hash='hash', actor_id='actor', reason='test')
    if seconds != 660:
        with pytest.raises(persistence.ConnectorRepositoryError, match='runtime_session_expiry_invalid'): invoke()
    else:
        result = invoke()
        assert (result['expires_at'] if isinstance(result, dict) else result.expires_at) == expiry


@pytest.mark.parametrize('seconds', [301, 660])
def test_recovery_persistence_still_refuses_more_than_300_seconds(monkeypatch, seconds):
    def no_connection():
        pytest.fail('invalid recovery expiry must be refused before persistence')
    monkeypatch.setattr(persistence, 'get_simulation_conn', no_connection)
    with pytest.raises(persistence.ConnectorRepositoryError, match='runtime_session_expiry_invalid'):
        persistence.SimulationConnectorRepository().register_reconciliation_session(
            'device', 1, 'recovery', 'plan', 'a'*64, NOW+timedelta(seconds=seconds), now=NOW)


@pytest.mark.parametrize('second_update', ['unchanged', 'not_installed', 'replaced_identity'])
def test_authenticated_same_timestamp_renewal_accepts_only_exact_installed_values(monkeypatch, second_update):
    import hashlib
    row = dict(device_id='device', protocol=persistence.PROTOCOL_V2, status='active', runtime_generation=1,
        current_runtime_instance_id='runtime', session_token_hash=hashlib.sha256(b'token').hexdigest(),
        session_expires_at=NOW+timedelta(seconds=650), updated_at=NOW-timedelta(seconds=10))
    class Cursor:
        rowcount = 0
        updates = 0
        def execute(self, sql, params):
            if sql.startswith('UPDATE workmanship_sim_connector_runtime_devices SET session_expires_at='):
                self.updates += 1
                expiry, updated = params[:2]
                if self.updates == 2 and second_update != 'unchanged':
                    row['session_expires_at'] = NOW+timedelta(seconds=650)
                    if second_update == 'replaced_identity': row['current_runtime_instance_id'] = 'replacement'
                    self.rowcount = 0
                else:
                    self.rowcount = int((row['session_expires_at'], row['updated_at']) != (expiry, updated))
                    row.update(session_expires_at=expiry, updated_at=updated)
            else: self.rowcount = 1
        def fetchone(self): return dict(row)
        def __enter__(self): return self
        def __exit__(self, *_): return False
    cursor = Cursor()
    monkeypatch.setattr(persistence, 'get_simulation_conn', lambda: nullcontext(SimpleNamespace(cursor=lambda: cursor)))
    repository = persistence.SimulationConnectorRepository()
    expiry = NOW+timedelta(seconds=660)
    first = repository.renew_runtime('device', 1, 'runtime', 'token', NOW, expiry)
    if second_update == 'unchanged':
        assert repository.renew_runtime('device', 1, 'runtime', 'token', NOW, expiry) == first
    else:
        with pytest.raises(persistence.ConnectorRepositoryError):
            repository.renew_runtime('device', 1, 'runtime', 'token', NOW, expiry)

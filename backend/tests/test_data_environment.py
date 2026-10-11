from backend.base.data_environment import availability, normalize_record


def test_active_connection_test_uses_runtime_connection_and_is_read_only(monkeypatch):
    from types import SimpleNamespace
    from backend.base import data_environment as module
    from backend.db import table_prefix
    queries, checked, closed = [], [], []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql): queries.append(sql)
        def fetchone(self): return {'ok': 1}
    connection = SimpleNamespace(cursor=Cursor, close=lambda: closed.append(True))
    monkeypatch.setattr(module, 'connect', lambda: connection)
    monkeypatch.setattr(module, '_require_admin', lambda conn, prefix, gid: checked.append((prefix, gid)))
    monkeypatch.setattr(table_prefix, 'current_table_prefix', lambda: 'pp_')
    result = module.test_active_connection({}, SimpleNamespace(user_gid='admin'))
    assert result['connected'] and result['prefix'] == 'pp_'
    assert result['elapsed_ms'] >= 0
    assert queries == ['SELECT 1 AS ok'] and checked == [('pp_', 'admin')] and closed == [True]


def test_active_connection_failure_is_redacted(monkeypatch):
    from backend.base import data_environment as module
    from types import SimpleNamespace
    def fail(): raise RuntimeError('secret password and host')
    monkeypatch.setattr(module, 'connect', fail)
    result = module.test_active_connection({}, SimpleNamespace(user_gid='admin'))
    assert not result['connected']
    assert 'secret' not in str(result)


def test_fixed_test_baseline_even_when_pp_is_active():
    result = availability({'test_': {'a': [1]}, 'pp_': {'a': [2]}, '': {'a': [2]}})
    assert result['test_'] == []
    assert result['pp_']
    assert result['']


def test_production_requires_both_test_and_pp():
    result = availability({'test_': {'a': [1]}, 'pp_': {'a': [2]}, '': {'a': [1]}})
    assert result['']


def test_equal_schemas_and_missing_baseline():
    assert availability({p: {'a': [1]} for p in ('test_', 'pp_', '')}) == {p: [] for p in ('test_', 'pp_', '')}
    assert all(availability({p: {} for p in ('test_', 'pp_', '')}).values())


def test_business_field_prefix_is_preserved():
    row = normalize_record({'TABLE_NAME': 'pp_workmanship_a', 'COLUMN_NAME': 'pp_run_gid'}, 'pp_')
    assert row == {'TABLE_NAME': 'workmanship_a', 'COLUMN_NAME': 'pp_run_gid'}


def test_cross_environment_reference_is_not_normalized_away():
    row = normalize_record({'TABLE_NAME': 'pp_workmanship_a', 'REFERENCED_TABLE_NAME': 'test_workmanship_b'}, 'pp_')
    assert row['REFERENCED_TABLE_NAME'] == 'test_workmanship_b'


def test_trigger_identifiers_are_normalized_but_string_values_are_preserved():
    row = normalize_record({'ACTION_STATEMENT': "UPDATE pp_workmanship_a SET x='pp_workmanship_a'"}, 'pp_')
    assert row['ACTION_STATEMENT'] == "UPDATE workmanship_a SET x='pp_workmanship_a'"


def test_submit_rechecks_and_rejects_unavailable_target(monkeypatch):
    from types import SimpleNamespace
    from backend.base import data_environment as module
    from backend.db import table_prefix
    connection = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(module, 'switching_enabled', lambda: True)
    monkeypatch.setattr(module, 'connect', lambda: connection)
    monkeypatch.setattr(module, '_require_admin', lambda *args: None)
    monkeypatch.setattr(table_prefix, 'current_table_prefix', lambda: 'test_')
    monkeypatch.setattr(module, '_status', lambda connection: {'options': [{'prefix': 'pp_', 'available': False}]})
    import pytest
    with pytest.raises(ValueError, match='禁止切换'):
        module.change_environment({'prefix': 'pp_', 'expected_prefix': 'test_'}, SimpleNamespace(user_gid='1'))
    assert not module._pending


def test_fresh_database_role_blocks_stale_super_admin_claim():
    from backend.base.data_environment import _require_admin
    import pytest
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, *args): pass
        def fetchone(self): return {'system_role': 'member', 'org_role': 'member', 'is_active': 1}
    class Connection:
        def cursor(self): return Cursor()
    with pytest.raises(ValueError, match='有效超管'):
        _require_admin(Connection(), 'test_', '1')


def test_switch_persists_without_changing_live_connections(monkeypatch, tmp_path):
    import json
    from types import SimpleNamespace
    from backend.base import data_environment as module
    from backend.db import table_prefix
    monkeypatch.setattr(module, '_pending', False)
    monkeypatch.setattr(module, 'switching_enabled', lambda: True)
    monkeypatch.setattr(module, 'state_path', lambda: tmp_path / 'selection.json')
    monkeypatch.setattr(module, 'connect', lambda: SimpleNamespace(close=lambda: None))
    checked = []
    monkeypatch.setattr(module, '_require_admin', lambda connection, prefix, gid: checked.append(prefix))
    monkeypatch.setattr(table_prefix, 'current_table_prefix', lambda: 'test_')
    monkeypatch.setattr(module, '_status', lambda connection: {'options': [{'prefix': 'pp_', 'available': True}]})
    timers = []
    class Timer:
        def __init__(self, seconds, callback): timers.append((seconds, callback))
        def start(self): pass
    monkeypatch.setattr(module.threading, 'Timer', Timer)
    monkeypatch.setattr(module, '_restart', lambda: None)
    result = module.change_environment({'prefix': 'pp_', 'expected_prefix': 'test_'}, SimpleNamespace(user_gid='1'))
    assert result == {'accepted': True, 'prefix': 'pp_', 'restarting': True}
    assert checked == ['test_', 'pp_']
    assert json.loads((tmp_path / 'selection.json').read_text())['previous_prefix'] == 'test_'
    assert table_prefix.current_table_prefix() == 'test_'
    assert module._pending and len(timers) == 1


def test_lifespan_startup_failure_is_nonzero_for_supervisor_recovery(monkeypatch):
    from backend.base import data_environment as module
    from types import SimpleNamespace
    monkeypatch.setattr(module, '_restart', None)
    failed = SimpleNamespace(started=False, run=lambda: None)
    assert module.run_supervised_server(failed) == 1
    healthy = SimpleNamespace(started=True, should_exit=False, run=lambda: module._restart())
    assert module.run_supervised_server(healthy) == 75
    assert healthy.should_exit

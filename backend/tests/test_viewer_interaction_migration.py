import importlib.util
import sqlite3
import re

import pytest


def script():
    name = 'backend.scripts.prepare_viewer_interaction_test'
    assert importlib.util.find_spec(name), 'test-only migration preparation is missing'
    return __import__(name, fromlist=['test_migration'])


def test_0029_selects_only_additive_evidence_table():
    _, migration = script().test_migration('0029')
    assert migration.migration_id == '0029'
    assert set(re.findall(r'CREATE TABLE IF NOT EXISTS `([^`]+)`', migration.sql)) == {'test_workmanship_sim_viewer_grant_evidence'}


def test_migration_targets_only_three_additive_test_tables():
    module = script()
    manifest, migration = module.test_migration()
    assert migration.migration_id == '0028'
    sql = migration.sql
    sql = re.sub(r' CHARACTER SET \w+| COLLATE \w+', '', sql)
    sql = re.sub(r'\) ENGINE=InnoDB[^;]*;', ');', sql)
    sql = re.sub(r'^\s*(?:UNIQUE )?KEY [^\n]+\n', '', sql, flags=re.M)
    sql = re.sub(r',\s*\)', ')', sql)
    with sqlite3.connect(':memory:') as db:
        db.executescript(sql)
        db.executescript(sql)
        assert {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} == {
            'test_workmanship_sim_viewer_source_associations',
            'test_workmanship_sim_viewer_interaction_grants',
            'test_workmanship_sim_viewer_interaction_events'}


@pytest.mark.parametrize('sql', ["DROP TABLE test_workmanship_sim_viewer_interaction_events;",
    "CREATE TABLE IF NOT EXISTS workmanship_sim_viewer_interaction_events (id INT);",
    "CREATE TABLE IF NOT EXISTS test_workmanship_other (id INT);"])
def test_migration_rejects_destructive_or_out_of_scope_sql(sql):
    with pytest.raises(ValueError, match='test_migration_scope_invalid'):
        script().validate_test_sql(sql)


def test_check_needs_no_credentials_or_database_connection(capsys):
    assert script().main(['--check']) == 0
    text = capsys.readouterr().out
    assert '0028' in text and 'test_workmanship_sim_viewer_interaction_events' in text


@pytest.mark.parametrize('migration_id', ['0028', '0029'])
def test_apply_runs_exact_migration_and_prefixed_ledger_through_standard_runner(monkeypatch, migration_id):
    import dotenv
    import pymysql
    from backend.tests.test_domain_migration_runner import RecordingConnection, RecordingCursor
    from backend.db.table_prefix import configure_table_prefix
    from backend.db.versioned_migrations import strip_sql_comments
    connection = RecordingConnection()
    class Cursor(RecordingCursor):
        def execute(self, sql, params=()):
            super().execute(strip_sql_comments(sql), params)
            values = {'SELECT VERSION() AS version': ('OceanBase_CE 4.3.5.1',),
                "SHOW VARIABLES LIKE 'ob_compatibility_mode'": ('ob_compatibility_mode', 'MYSQL'),
                'SELECT @@sql_mode AS sql_mode': ('STRICT_TRANS_TABLES',)}
            if sql in values: self._one = values[sql]
    connection.cursor = lambda: Cursor(connection)
    connection.close = lambda: None
    monkeypatch.setattr(dotenv, 'dotenv_values', lambda _: {'USERS_DB_URL':'mysql://test:test@localhost/local_test'})
    monkeypatch.setattr(pymysql, 'connect', lambda **_: connection)
    try:
        assert script().main(['--apply', '--migration', migration_id, '--env-file', 'test-only-not-read.env']) == 0
    finally:
        configure_table_prefix('')
    writes = [sql for sql, _ in connection.statements if sql.startswith(('CREATE', 'INSERT', 'ALTER', 'UPDATE', 'DELETE', 'DROP'))]
    created = {re.search(r'CREATE TABLE IF NOT EXISTS `?([a-z0-9_]+)', sql)[1] for sql in writes if sql.startswith('CREATE')}
    assert created == (script().TABLES if migration_id == '0028' else script().EVIDENCE_TABLES) | {'test_ai00_simulation_schema_migrations'}
    inserts = [(sql, args) for sql, args in connection.statements if sql.startswith('INSERT')]
    assert len(inserts) == 1
    assert inserts[0][0].startswith('INSERT INTO test_ai00_simulation_schema_migrations')
    assert inserts[0][1][0] == migration_id
    assert not any(sql.startswith(('ALTER', 'UPDATE', 'DELETE', 'DROP')) for sql in writes)
    assert connection.rollbacks == 0
    assert connection.commits >= 1

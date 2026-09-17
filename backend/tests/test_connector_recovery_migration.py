from pathlib import Path
import re

import pytest

from backend.db import table_prefix
from backend.db.versioned_migrations import MigrationError, is_resumable_ddl, prepare_resumable_statement, split_sql

SQL = """-- AI00: RESUMABLE ADD EXPANDED STATUS CHECK
ALTER TABLE workmanship_sim_connector_runtime_plans ADD CONSTRAINT runtime_plan_status
CHECK (status IN ('queued','leased','executing','succeeded','failed_without_effect','outcome_unknown','manual_review_required','expired','cancelled'))"""
RETIRE_SQL = """-- AI00: RESUMABLE RETIRE OLD STATUS CHECK
ALTER TABLE workmanship_sim_connector_runtime_plans DROP CHECK sim_runtime_plan_status_pre_recovery"""


class Connection:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, sql, params):
        self.calls.append((sql, params))

    def fetchall(self):
        return self.rows


def row(name, values):
    return {'CONSTRAINT_NAME': name, 'CHECK_CLAUSE': f"(`status` in ({values}))"}


OLD = "'queued','leased','executing','succeeded','failed_without_effect','outcome_unknown','manual_review_required','expired'"


def test_adds_expanded_check_without_removing_old_with_test_prefix(monkeypatch):
    monkeypatch.setattr(table_prefix, '_PREFIX', 'test_')
    conn = Connection([row('old_status_3', OLD), {'CONSTRAINT_NAME': 'generation', 'CHECK_CLAUSE': '(runtime_generation >= 1)'}])
    assert is_resumable_ddl(SQL)
    result = prepare_resumable_statement(conn, SQL)
    assert 'ADD CONSTRAINT' in result and 'DROP' not in result
    assert conn.calls[0][1] == ('test_workmanship_sim_connector_runtime_plans',)
    assert 'generation' not in result


def test_both_checks_resume_by_retiring_only_old_check():
    rows = [row('old_status_3', OLD), row('expanded_status', OLD + ",'cancelled'")]
    assert prepare_resumable_statement(Connection(rows), SQL) is None
    connection = Connection(rows)
    assert is_resumable_ddl(RETIRE_SQL)
    assert prepare_resumable_statement(connection, RETIRE_SQL) == (
        'ALTER TABLE `workmanship_sim_connector_runtime_plans` DROP CHECK `old_status_3`')
    assert all(query.startswith('SELECT ') for query, _ in connection.calls)


def test_retirement_requires_confirmed_expanded_check():
    with pytest.raises(MigrationError):
        prepare_resumable_statement(Connection([row('old_status_3', OLD)]), RETIRE_SQL)


def test_actual_migration_has_two_resumable_single_action_phases(monkeypatch):
    monkeypatch.setattr(table_prefix, '_PREFIX', 'test_')
    migration = Path(__file__).resolve().parents[1] / 'db/migrations/domains/simulation/0027_connector_manual_recovery_status.sql'
    phases = split_sql(migration.read_text(encoding='utf-8'))
    assert len(phases) == 2 and all(is_resumable_ddl(phase) for phase in phases)
    original = [row('old_status', OLD)]
    add = prepare_resumable_statement(Connection(original), phases[0])
    assert 'ADD CONSTRAINT' in add and 'DROP CHECK' not in add and ';' not in add
    name = re.search(r'ADD CONSTRAINT `([^`]+)`', add).group(1)
    partial = original + [row(name, OLD + ",'cancelled'")]
    # Restart after the ADD commit: do not duplicate the new CHECK.
    assert prepare_resumable_statement(Connection(partial), phases[0]) is None
    drop = prepare_resumable_statement(Connection(partial), phases[1])
    assert drop.endswith('DROP CHECK `old_status`') and 'ADD' not in drop and ';' not in drop
    final = partial[1:]
    assert all(prepare_resumable_statement(Connection(final), phase) is None for phase in phases)


def test_invalid_old_identifier_and_changed_status_expression_refuse():
    with pytest.raises(MigrationError):
        prepare_resumable_statement(Connection([row('unsafe`name', OLD), row('new', OLD + ",'cancelled'")]), RETIRE_SQL)
    for phase in (SQL, RETIRE_SQL):
        with pytest.raises(MigrationError):
            prepare_resumable_statement(Connection([{'CONSTRAINT_NAME':'unknown', 'CHECK_CLAUSE':"status <> 'alien'"}]), phase)


def test_replay_already_expanded_status_is_noop():
    assert prepare_resumable_statement(Connection([row('new_status', OLD + ",'cancelled'")]), SQL) is None
    assert prepare_resumable_statement(Connection([row('new_status', OLD + ",'cancelled'")]), RETIRE_SQL) is None


def test_status_constraint_names_are_distinct_for_prefixed_tables(monkeypatch):
    names = []
    for prefix in ('', 'test_'):
        monkeypatch.setattr(table_prefix, '_PREFIX', prefix)
        connection = Connection([row('old_status', OLD)])
        prepared = prepare_resumable_statement(connection, SQL)
        rendered = table_prefix.rewrite_sql(prepared)
        names.append(re.search(r'ADD CONSTRAINT `([^`]+)`', rendered).group(1))
        assert f'ALTER TABLE `{prefix}workmanship_sim_connector_runtime_plans`' in rendered
        assert connection.calls[0][1] == (prefix + 'workmanship_sim_connector_runtime_plans',)
        assert all(query.startswith('SELECT ') for query, _ in connection.calls)
    assert names[0] != names[1]


def test_status_constraint_name_is_bounded_and_stable(monkeypatch):
    monkeypatch.setattr(table_prefix, '_PREFIX', 'a_very_long_test_environment_prefix_')
    statement = SQL.replace('ADD CONSTRAINT runtime_plan_status', 'ADD CONSTRAINT ' + 'constraint_' * 10)
    first = prepare_resumable_statement(Connection([row('old_status', OLD)]), statement)
    second = prepare_resumable_statement(Connection([row('old_status', OLD)]), statement)
    name = re.search(r'ADD CONSTRAINT `([^`]+)`', first).group(1)
    assert len(name) <= 64
    assert re.fullmatch(r'[a-zA-Z0-9_]+', name)
    assert first == second


@pytest.mark.parametrize('statement', [SQL, RETIRE_SQL])
@pytest.mark.parametrize('rows', [[], [row('bad', "'queued','foreign_status'")], [row('a', OLD), row('b', OLD)],
    [row('a', OLD + ",'cancelled'"), row('b', OLD + ",'cancelled'")],
    [row('old', OLD), row('new', OLD + ",'cancelled'"), row('foreign', "'queued'")]])
def test_unknown_or_ambiguous_constraint_fails_closed(rows, statement):
    with pytest.raises(MigrationError):
        prepare_resumable_statement(Connection(rows), statement)

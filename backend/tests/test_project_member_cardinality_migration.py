from pathlib import Path
from backend.db.versioned_migrations import prepare_resumable_statement, discover_migrations
import sqlite3
import re


def test_bootstrap_indexes_allow_multiple_members_in_one_project():
    sql = Path('backend/db/mysql_schema.sql').read_text(encoding='utf-8')
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE workmanship_auth_project_members (gid TEXT PRIMARY KEY, project_gid TEXT, user_gid TEXT, role TEXT, scope_gid TEXT)')
    indexes = re.findall(r'CREATE (?:UNIQUE )?INDEX idx_pm_[^;]+;', sql)
    for statement in indexes:
        if 'scope_type' in statement: continue
        conn.execute(re.sub(r'(role|scope_gid)\(\d+\)', r'\1', statement))
    conn.execute("INSERT INTO workmanship_auth_project_members VALUES ('a','p','u1','member',NULL)")
    conn.execute("INSERT INTO workmanship_auth_project_members VALUES ('b','p','u2','member',NULL)")
    assert conn.execute('SELECT COUNT(*) FROM workmanship_auth_project_members').fetchone()[0] == 2


def test_drop_legacy_unique_index_is_resumable_on_mysql():
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, args): pass
        def fetchone(self): return {'count': self.exists}
    class Connection:
        def __init__(self, exists): self.cur = Cursor(); self.cur.exists = exists
        def cursor(self): return self.cur
    sql = 'DROP INDEX IF EXISTS idx_pm_unique_global ON workmanship_auth_project_members'
    assert prepare_resumable_statement(Connection(1), sql) == sql.replace(' IF EXISTS', '')
    assert prepare_resumable_statement(Connection(0), sql) is None


def test_member_cardinality_migration_is_base_owned_and_forward_only():
    migrations = discover_migrations(Path('backend/db/migrations'))
    migration = next(item for item in migrations if item.migration_id == '202610140001')
    assert migration.domain == 'base'
    assert 'DROP INDEX IF EXISTS idx_pm_unique_global' in migration.sql
    assert 'DROP INDEX IF EXISTS idx_pm_unique_scoped' in migration.sql
    assert 'CREATE INDEX IF NOT EXISTS idx_pm_global' in migration.sql

"""Preview/apply exactly one selected viewer migration to the test_ projection."""
import argparse
from dataclasses import replace
from pathlib import Path
import re
from urllib.parse import urlparse, unquote

from backend.capability_v2.domain_manifest import load_domain_manifests
from backend.capability_v2.domain_migrations import discover_domain_migrations, apply_domain_migrations
from backend.db.versioned_migrations import split_sql, strip_sql_comments
from backend.db.table_prefix import configure_table_prefix, rewrite_sql

ROOT = Path(__file__).resolve().parents[2]
TABLES = frozenset('test_workmanship_sim_' + name for name in (
    'viewer_source_associations', 'viewer_interaction_grants', 'viewer_interaction_events'))


EVIDENCE_TABLES = frozenset({'test_workmanship_sim_viewer_grant_evidence'})


def validate_test_sql(sql, tables=TABLES):
    found = set()
    for statement in split_sql(sql):
        statement = strip_sql_comments(statement).strip()
        if not statement: continue
        match = re.fullmatch(r'CREATE TABLE IF NOT EXISTS `?(test_workmanship_sim_[a-z_]+)`?\s*\(.*\)\s*ENGINE=InnoDB[^;]*',
            statement, re.S | re.I)
        if not match or match[1] not in tables or match[1] in found:
            raise ValueError('test_migration_scope_invalid')
        found.add(match[1])
    if found != tables:
        raise ValueError('test_migration_scope_invalid')


def test_migration(migration_id='0028'):
    if migration_id not in {'0028', '0029'}:
        raise ValueError('test_migration_scope_invalid')
    manifest = load_domain_manifests(ROOT / 'backend/capability_v2/official_domains.json').require('simulation')
    migration = next(m for m in discover_domain_migrations(ROOT, manifest) if m.migration_id == migration_id)
    # Fixed target prefix; no option can select production tables. The checksum
    # stays the canonical 0028 checksum used by the standard migration ledger.
    sql = re.sub(r'(?<![A-Za-z0-9_])workmanship_', 'test_workmanship_', migration.sql)
    validate_test_sql(sql, TABLES if migration_id == '0028' else EVIDENCE_TABLES)
    return manifest, replace(migration, sql=sql)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--apply', action='store_true')
    parser.add_argument('--migration', choices=('0028', '0029'), default='0028')
    parser.add_argument('--env-file', type=Path, help='Same backend .env as run_current_test_backend.py (USERS_DB_URL)')
    args = parser.parse_args(argv)
    manifest, migration = test_migration(args.migration)
    print('migration=' + args.migration + ' prefix=test_ checksum=' + migration.checksum)
    print('tables=' + ','.join(sorted(TABLES if args.migration == '0028' else EVIDENCE_TABLES)) + '; ledger=test_ai00_simulation_schema_migrations')
    if args.check:
        print(migration.sql)
        return 0
    if args.env_file is None:
        parser.error('--apply requires the local test runner --env-file')
    from dotenv import dotenv_values
    import pymysql
    from backend.db.prefixed_cursor import wrap_connection
    from backend.db.oceanbase_compat import verify_live_server
    raw = dotenv_values(args.env_file).get('USERS_DB_URL', '')
    url = urlparse(raw)
    if url.scheme not in {'mysql', 'mysql+pymysql'} or not url.hostname or not url.path.strip('/'):
        raise ValueError('local_test_database_url_invalid')
    configure_table_prefix('test_')
    if rewrite_sql('ai00_simulation_schema_migrations') != 'test_ai00_simulation_schema_migrations':
        raise ValueError('test_migration_scope_invalid')
    conn = wrap_connection(pymysql.connect(host=url.hostname, port=url.port or 3306,
        user=unquote(url.username or ''), password=unquote(url.password or ''), database=url.path.lstrip('/'),
        charset='utf8mb4', autocommit=False, connect_timeout=5))
    try:
        verify_live_server(conn)
        applied = apply_domain_migrations(conn, manifest, (migration,))
        print('applied=' + ','.join(applied))
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

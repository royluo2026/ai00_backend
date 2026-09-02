import unittest
from pathlib import Path

from backend.db.versioned_migrations import (
    bootstrap_statements,
    canonicalize_migration_sql,
    discover_migrations,
    is_resumable_ddl,
    normalize_oceanbase_sql,
    prepare_resumable_statement,
    strip_sql_comments,
    validate_migration,
)
from backend.governance import load_registry
from backend.scripts.migrate_capability_governance_test import MIGRATION_FILE_RE


TEST_GOVERNANCE_DIR = Path(__file__).resolve().parents[1] / "db/migrations/test_governance"


class VersionedMigrationFileTests(unittest.TestCase):
    def test_business_governance_migration_is_discoverable(self):
        matches = (MIGRATION_FILE_RE.fullmatch(path.name) for path in TEST_GOVERNANCE_DIR.glob("*.sql"))
        ids = {match.group("id") for match in matches if match is not None}
        self.assertIn("0005", ids)
        self.assertIn("0006", ids)

    def test_bootstrap_stays_in_selected_database(self):
        statements = bootstrap_statements(
            "CREATE DATABASE IF NOT EXISTS wrong; USE wrong; "
            "CREATE TABLE IF NOT EXISTS workmanship_auth_users (gid CHAR(36));"
        )
        self.assertEqual(len(statements), 1)
        self.assertIn("workmanship_auth_users", statements[0])

    def test_migration_checksum_input_is_line_ending_stable(self):
        lf = "CREATE TABLE x (\n  gid VARCHAR(36)\n);\n"
        crlf = lf.replace("\n", "\r\n")
        self.assertEqual(
            canonicalize_migration_sql(lf),
            canonicalize_migration_sql(crlf),
        )
    def test_legacy_json_defaults_are_normalized_for_oceanbase(self):
        sql = "CREATE TABLE IF NOT EXISTS workmanship_app_x (payload JSON NOT NULL DEFAULT (JSON_OBJECT()));"
        normalized = normalize_oceanbase_sql(sql)
        self.assertIn("payload JSON NOT NULL", normalized)
        self.assertNotIn("JSON_OBJECT", normalized)

    def test_comment_stripping_preserves_comment_markers_inside_strings(self):
        sql = """CREATE TABLE x (
          color VARCHAR(16) DEFAULT ('#5b8dee'),
          note VARCHAR(32) DEFAULT ('--not-a-comment')
        ); # real comment
        -- another real comment
        SELECT 1 /* block comment */;
        """
        stripped = strip_sql_comments(sql)
        self.assertIn("'#5b8dee'", stripped)
        self.assertIn("'--not-a-comment'", stripped)
        self.assertNotIn("real comment", stripped)
    def test_all_committed_migrations_are_named_and_domain_safe(self):
        root = Path(__file__).resolve().parents[2]
        migrations = discover_migrations(root / "backend/db/migrations")
        self.assertGreaterEqual(len(migrations), 1)
        registry = load_registry()
        for migration in migrations:
            validate_migration(migration, registry)

    def test_marked_backfills_are_replay_safe_but_unmarked_dml_is_rejected(self):
        self.assertTrue(is_resumable_ddl(
            "-- AI00: RESUMABLE BACKFILL\nUPDATE workmanship_app_x SET tenant_gid='x' WHERE tenant_gid IS NULL"
        ))
        self.assertFalse(is_resumable_ddl("UPDATE workmanship_app_x SET tenant_gid='x'"))

    def test_completed_not_null_and_primary_key_steps_are_skipped(self):
        class MetadataCursor:
            def __init__(self):
                self.rows = []

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def execute(self, sql, _params=()):
                if "information_schema.COLUMNS" in sql:
                    self.rows = [("NO",)]
                elif "information_schema.STATISTICS" in sql:
                    self.rows = [("tenant_gid",), ("view_gid",)]

            def fetchone(self):
                return self.rows[0] if self.rows else None

            def fetchall(self):
                return self.rows

        class MetadataConnection:
            def cursor(self):
                return MetadataCursor()

        connection = MetadataConnection()
        self.assertIsNone(prepare_resumable_statement(
            connection,
            "ALTER TABLE workmanship_app_x MODIFY COLUMN tenant_gid VARCHAR(128) NOT NULL",
        ))
        self.assertIsNone(prepare_resumable_statement(
            connection,
            "ALTER TABLE workmanship_app_x DROP PRIMARY KEY, ADD PRIMARY KEY (tenant_gid,view_gid)",
        ))

    def test_not_null_hash_type_change_runs_until_binary_type_matches(self):
        class MetadataCursor:
            def __init__(self, column_type):
                self.column_type = column_type

            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def execute(self, _sql, _params=()): pass
            def fetchone(self): return ("NO", self.column_type)

        class MetadataConnection:
            def __init__(self, column_type):
                self.column_type = column_type

            def cursor(self): return MetadataCursor(self.column_type)

        statement = (
            "ALTER TABLE workmanship_base_capability_business_reviews "
            "MODIFY COLUMN definition_hash VARBINARY(71) NOT NULL"
        )

        self.assertEqual(
            prepare_resumable_statement(MetadataConnection("varchar(71)"), statement),
            statement,
        )
        self.assertIsNone(
            prepare_resumable_statement(MetadataConnection("varbinary(71)"), statement),
        )

    def test_historical_self_annotation_backfill_normalizes_join_collations(self):
        statement = """-- AI00: RESUMABLE BACKFILL
        UPDATE workmanship_base_self_annotations a
        LEFT JOIN workmanship_auth_users u ON u.gid=a.user_gid
        SET a.tenant_gid=u.team_id;
        UPDATE workmanship_base_self_annotation_states s
        JOIN workmanship_base_self_annotations a
          ON a.item_gid=s.item_gid AND a.user_gid=s.user_gid
        SET s.tenant_gid=a.tenant_gid
        """

        prepared = prepare_resumable_statement(object(), statement)

        self.assertIn("u.gid=a.user_gid COLLATE utf8mb4_unicode_ci", prepared)
        self.assertIn("a.item_gid COLLATE utf8mb4_unicode_ci=s.item_gid", prepared)
        self.assertIn("a.user_gid COLLATE utf8mb4_unicode_ci=s.user_gid", prepared)

    def test_legacy_rule_owner_backfill_is_skipped_when_creator_column_is_absent(self):
        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def execute(self, _sql, _params=()): self.row = (0,)
            def fetchone(self): return self.row

        class Connection:
            def cursor(self): return Cursor()

        statement = """-- AI00: RESUMABLE BACKFILL
        UPDATE workmanship_know_craft_rules
        SET owner_user_gid = creator_gid
        WHERE owner_user_gid IS NULL AND creator_gid IS NOT NULL
        """

        self.assertIsNone(prepare_resumable_statement(Connection(), statement))


if __name__ == "__main__":
    unittest.main()

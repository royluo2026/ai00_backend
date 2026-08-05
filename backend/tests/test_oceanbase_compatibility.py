import unittest
from pathlib import Path

from backend.db.versioned_migrations import Migration, MigrationError, validate_migration
from backend.governance import load_registry
from backend.scripts.oceanbase_compatibility_audit import declared_schema_columns

from backend.db.oceanbase_compat import (
    assert_supported_server,
    audit_sql,
    text_columns_with_defaults,
    verify_live_server,
)


class _Cursor:
    def __init__(self, rows):
        self.rows = iter(rows)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _sql, _params=None):
        return None

    def fetchone(self):
        return next(self.rows)


class _Connection:
    def __init__(self, rows):
        self.rows = rows

    def cursor(self):
        return _Cursor(self.rows)


class OceanBaseCompatibilityTests(unittest.TestCase):
    def test_declared_columns_include_create_and_alter_contracts(self):
        schema = declared_schema_columns([
            """CREATE TABLE IF NOT EXISTS workmanship_app_x (
                gid CHAR(36) PRIMARY KEY,
                name VARCHAR(64),
                PRIMARY KEY (gid)
            ) ENGINE=InnoDB;""",
            "ALTER TABLE workmanship_app_x ADD COLUMN IF NOT EXISTS status VARCHAR(32);",
        ])
        self.assertEqual(schema["workmanship_app_x"], {"gid", "name", "status"})
    def test_text_and_blob_defaults_are_rejected(self):
        sql = """
        CREATE TABLE IF NOT EXISTS workmanship_app_bad (
            gid CHAR(36) PRIMARY KEY,
            content TEXT NOT NULL DEFAULT ('')
        );
        ALTER TABLE workmanship_app_bad
            ADD COLUMN IF NOT EXISTS payload BLOB DEFAULT NULL;
        ALTER TABLE workmanship_app_bad
            ADD COLUMN IF NOT EXISTS metadata JSON DEFAULT (JSON_OBJECT());
        """
        self.assertEqual(text_columns_with_defaults(sql), ["content", "payload", "metadata"])
        self.assertEqual([issue.code for issue in audit_sql(Path("bad.sql"), sql)], ["OB010", "OB010", "OB010"])

    def test_text_column_is_not_confused_by_later_column_default(self):
        sql = "CREATE TABLE IF NOT EXISTS workmanship_app_ok (message TEXT NOT NULL, status VARCHAR(32) DEFAULT 'open');"
        self.assertEqual(text_columns_with_defaults(sql), [])

    def test_minimum_version_and_mysql_mode_are_enforced(self):
        assert_supported_server("OceanBase_CE 4.3.5.1", "MYSQL")
        with self.assertRaises(RuntimeError):
            assert_supported_server("OceanBase_CE 4.2.1.0", "MYSQL")
        with self.assertRaises(RuntimeError):
            assert_supported_server("OceanBase_CE 4.3.5.1", "ORACLE")

    def test_non_resumable_ddl_is_rejected(self):
        sql = "ALTER TABLE workmanship_plugin_releases MODIFY COLUMN version VARCHAR(128);"
        migration = Migration(
            migration_id="202608049999",
            domain="base",
            name="bad_modify",
            path=Path("202608049999_base_bad_modify.sql"),
            sql=sql,
            checksum="x" * 64,
        )
        with self.assertRaises(MigrationError):
            validate_migration(migration, load_registry())
    def test_live_profile_requires_strict_sql_mode(self):
        conn = _Connection([
            {"version": "OceanBase_CE 4.3.5.1"},
            {"Variable_name": "ob_compatibility_mode", "Value": "MYSQL"},
            {"sql_mode": "STRICT_TRANS_TABLES,NO_ZERO_DATE"},
        ])
        profile = verify_live_server(conn)
        self.assertEqual(profile["compatibility_mode"], "MYSQL")

        loose = _Connection([
            {"version": "OceanBase_CE 4.3.5.1"},
            {"Variable_name": "ob_compatibility_mode", "Value": "MYSQL"},
            {"sql_mode": "NO_ZERO_DATE"},
        ])
        with self.assertRaises(RuntimeError):
            verify_live_server(loose)


if __name__ == "__main__":
    unittest.main()
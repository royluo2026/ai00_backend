import unittest
from pathlib import Path

from backend.db.versioned_migrations import (
    bootstrap_statements,
    discover_migrations,
    normalize_oceanbase_sql,
    validate_migration,
)
from backend.governance import load_registry


class VersionedMigrationFileTests(unittest.TestCase):
    def test_bootstrap_stays_in_selected_database(self):
        statements = bootstrap_statements(
            "CREATE DATABASE IF NOT EXISTS wrong; USE wrong; "
            "CREATE TABLE IF NOT EXISTS workmanship_auth_users (gid CHAR(36));"
        )
        self.assertEqual(len(statements), 1)
        self.assertIn("workmanship_auth_users", statements[0])

    def test_legacy_json_defaults_are_normalized_for_oceanbase(self):
        sql = "CREATE TABLE IF NOT EXISTS workmanship_app_x (payload JSON NOT NULL DEFAULT (JSON_OBJECT()));"
        normalized = normalize_oceanbase_sql(sql)
        self.assertIn("payload JSON NOT NULL", normalized)
        self.assertNotIn("JSON_OBJECT", normalized)
    def test_all_committed_migrations_are_named_and_domain_safe(self):
        root = Path(__file__).resolve().parents[2]
        migrations = discover_migrations(root / "backend/db/migrations")
        self.assertGreaterEqual(len(migrations), 1)
        registry = load_registry()
        for migration in migrations:
            validate_migration(migration, registry)


if __name__ == "__main__":
    unittest.main()

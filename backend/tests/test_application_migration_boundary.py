import unittest
from pathlib import Path

from backend.db.migration_readiness import DatabaseNotMigratedError, assert_migrations_applied


class Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.sql = ""

    def __enter__(self): return self
    def __exit__(self, *_): return False
    def execute(self, sql): self.sql = sql
    def fetchall(self): return self.rows


class Connection:
    def __init__(self, rows): self.cursor_value = Cursor(rows)
    def cursor(self): return self.cursor_value


class ApplicationMigrationBoundaryTests(unittest.TestCase):
    def test_main_never_runs_legacy_safe_migrations(self):
        root = Path(__file__).resolve().parents[2]
        main = (root / "backend/main.py").read_text(encoding="utf-8")
        self.assertNotIn("run_safe_migrations", main)
        self.assertIn("assert_migrations_applied", main)
        self.assertNotIn("def _ensure_", main)
        self.assertNotIn("CREATE TABLE", main.upper())
        self.assertNotIn("ALTER TABLE", main.upper())

    def test_readiness_check_is_select_only(self):
        root = Path(__file__).resolve().parents[2]
        migrations = __import__("backend.db.versioned_migrations", fromlist=["discover_migrations"]).discover_migrations(root / "backend/db/migrations")
        rows = [{"migration_id": item.migration_id, "checksum": item.checksum, "status": "applied"} for item in migrations]
        connection = Connection(rows)
        assert_migrations_applied(connection, root / "backend/db/migrations")
        self.assertTrue(connection.cursor_value.sql.startswith("SELECT"))

    def test_missing_migration_fails_closed(self):
        root = Path(__file__).resolve().parents[2]
        with self.assertRaises(DatabaseNotMigratedError):
            assert_migrations_applied(Connection([]), root / "backend/db/migrations")


if __name__ == "__main__":
    unittest.main()

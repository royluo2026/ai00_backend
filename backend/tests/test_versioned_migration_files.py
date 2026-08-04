import unittest
from pathlib import Path

from backend.db.versioned_migrations import discover_migrations, validate_migration
from backend.governance import load_registry


class VersionedMigrationFileTests(unittest.TestCase):
    def test_all_committed_migrations_are_named_and_domain_safe(self):
        root = Path(__file__).resolve().parents[2]
        migrations = discover_migrations(root / "backend/db/migrations")
        self.assertGreaterEqual(len(migrations), 1)
        registry = load_registry()
        for migration in migrations:
            validate_migration(migration, registry)


if __name__ == "__main__":
    unittest.main()

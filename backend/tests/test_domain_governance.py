import json
import unittest
from pathlib import Path

from backend.db.versioned_migrations import Migration, MigrationError, split_sql, validate_migration
from backend.governance import OwnershipError, load_registry
from backend.scripts.audit_domain_boundaries import audit_repository


class DomainGovernanceTests(unittest.TestCase):
    def test_every_inventory_table_has_exactly_one_owner(self):
        root = Path(__file__).resolve().parents[2]
        inventory = json.loads((root / "backend/governance/table_inventory.json").read_text(encoding="utf-8"))
        registry = load_registry()
        self.assertEqual(inventory["registry_version"], registry.version)
        self.assertEqual(inventory["table_count"], len(inventory["tables"]))
        self.assertFalse([item for item in inventory["tables"] if registry.table_owner(item["table"]) is None])

    def test_app_prefix_is_split_into_explicit_owners(self):
        registry = load_registry()
        self.assertEqual(registry.table_owner("workmanship_app_ai_sessions").owner, "agent")
        self.assertEqual(registry.table_owner("workmanship_app_wfc_canvases").owner, "craft")
        self.assertEqual(registry.table_owner("workmanship_app_system_config").owner, "base")
        self.assertIsNone(registry.table_owner("workmanship_app_unknown"))

    def test_source_overrides_align_legacy_files_with_first_class_domains(self):
        registry = load_registry()
        self.assertEqual(registry.source_domain("backend/capabilities/knowledge_context_next.py"), "knowledge")
        self.assertEqual(registry.source_domain("backend/capabilities/ontology_releases_next.py"), "ontology")

    def test_audit_does_not_report_same_domain_import_as_base_internal(self):
        root = Path(__file__).resolve().parents[2]
        violations, _ = audit_repository(root, load_registry())
        self.assertFalse([
            item for item in violations
            if item.path == "backend/ontology/proposals.py"
            and item.target == "backend.ontology.canonical"
        ])

    def test_runtime_domain_boundary_audit_is_empty(self):
        """Any production cross-domain SQL/import is a release-blocking boundary break."""
        root = Path(__file__).resolve().parents[2]
        violations, _ = audit_repository(root, load_registry())
        self.assertEqual([], violations)

    def test_sql_splitter_preserves_semicolons_inside_literals_and_comments(self):
        sql = "INSERT INTO t VALUES ('a;b'); -- x;y\nUPDATE t SET c=\"z;z\";"
        self.assertEqual(len(split_sql(sql)), 2)

    def test_migration_cannot_touch_another_domains_table(self):
        migration = Migration(
            "202608030001",
            "agent",
            "bad",
            Path("202608030001_agent_bad.sql"),
            "SELECT * FROM workmanship_bop_bop_line;",
            "x",
        )
        with self.assertRaises(OwnershipError):
            validate_migration(migration, load_registry())

    def test_empty_migration_is_rejected(self):
        migration = Migration(
            "202608030001",
            "base",
            "empty",
            Path("202608030001_base_empty.sql"),
            "-- only a comment",
            "x",
        )
        with self.assertRaises(MigrationError):
            validate_migration(migration, load_registry())


    def test_schema_tooling_is_not_application_runtime(self):
        registry = load_registry()
        self.assertTrue(registry.is_non_runtime_path("backend/db/pg_to_mysql_migrate.py"))
        self.assertTrue(
            registry.is_non_runtime_path(
                "backend/capability_v2/database_isolation.py"
            )
        )
        self.assertTrue(registry.is_non_runtime_path("backend/capability_v2/schema_sql.py"))
        self.assertFalse(registry.is_non_runtime_path("backend/routers/ontology.py"))

    def test_domain_migration_runner_is_deployment_only_migration_tooling(self):
        registry = load_registry()
        self.assertTrue(
            registry.is_migration_path("backend/capability_v2/domain_migrations.py")
        )
        self.assertTrue(
            registry.is_migration_path("backend/scripts/run_domain_migrations.py")
        )


if __name__ == "__main__":
    unittest.main()

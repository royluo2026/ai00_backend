import inspect
import unittest
from pathlib import Path

from backend.capabilities.knowledge_migration_next import (
    migration_status,
    register_knowledge_migration_capabilities,
)
from backend.capabilities.registry_next import CapabilityRegistry, capability_registry


class KnowledgeMigrationControlTests(unittest.TestCase):
    def test_production_registry_contains_revision_and_migration_capabilities(self):
        self.assertEqual(
            capability_registry.get("knowledge.document.get").spec.id,
            "knowledge.document.get",
        )
        self.assertEqual(
            capability_registry.get("knowledge.migration.status").spec.id,
            "knowledge.migration.status",
        )

    def test_status_is_read_only_and_requires_knowledge_management(self):
        registry = CapabilityRegistry()
        register_knowledge_migration_capabilities(registry)
        spec = registry.get("knowledge.migration.status").spec
        self.assertEqual(spec.confirmation, "none")
        self.assertEqual(spec.permissions, ("knowledge.manage",))

    def test_status_uses_identity_projection_instead_of_auth_join(self):
        source = inspect.getsource(migration_status)
        self.assertIn("get_user_summaries", source)
        self.assertNotIn("workmanship_auth_", source)
        self.assertIn("r.tenant_gid=%s", source)

    def test_apply_cannot_skip_ois_read_after_write_verification(self):
        root = Path(__file__).resolve().parents[2]
        script = (root / "backend/scripts/migrate_knowledge_markdown_revisions.py").read_text(encoding="utf-8")
        self.assertNotIn("--no-verify", script)
        self.assertIn("result = verify_migration_run(conn, run_gid)", script)
    def test_batch_level_failure_is_persisted_instead_of_staying_running(self):
        root = Path(__file__).resolve().parents[2]
        script = (root / "backend/scripts/migrate_knowledge_markdown_revisions.py").read_text(encoding="utf-8")
        self.assertIn("def fail_migration_run", script)
        self.assertIn("SET status='failed',last_error=%s", script)
        self.assertIn("result = fail_migration_run(conn, run_gid, exc)", script)
    def test_control_tables_are_knowledge_owned_and_source_is_never_deleted(self):
        root = Path(__file__).resolve().parents[2]
        ddl = (root / "backend/db/migrations/202608040004_knowledge_legacy_migration_runs.sql").read_text(encoding="utf-8")
        script = (root / "backend/scripts/migrate_knowledge_markdown_revisions.py").read_text(encoding="utf-8")
        self.assertIn("workmanship_know_migration_runs", ddl)
        self.assertIn("workmanship_know_migration_items", ddl)
        self.assertNotIn("DELETE FROM WORKMANSHIP_KNOW_ENTRIES", script.upper())
        self.assertIn('"source_retained": True', script)


if __name__ == "__main__":
    unittest.main()

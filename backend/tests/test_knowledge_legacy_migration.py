from pathlib import Path
import unittest

from backend.scripts.migrate_knowledge_markdown_revisions import (
    inventory_summary,
    partition_inventory,
    plan_legacy_revision,
)


class KnowledgeLegacyMigrationTests(unittest.TestCase):
    def test_plan_is_deterministic_and_newline_stable(self):
        first = plan_legacy_revision("entry-1", "# A\r\n")
        second = plan_legacy_revision("entry-1", "# A\n")
        self.assertEqual(first, second)
        self.assertTrue(first.document_gid.startswith("legacy-doc-"))
        self.assertTrue(first.revision_gid.startswith("legacy-rev-"))

    def test_different_content_gets_new_revision_but_same_document(self):
        first = plan_legacy_revision("entry-1", "one")
        second = plan_legacy_revision("entry-1", "two")
        self.assertEqual(first.document_gid, second.document_gid)
        self.assertNotEqual(first.revision_gid, second.revision_gid)

    def test_source_id_is_required(self):
        with self.assertRaises(ValueError):
            plan_legacy_revision("", "text")

    def test_inventory_is_partitioned_by_creator_team_without_guessing(self):
        rows = [
            {"gid": "a", "creator_gid": "u1", "content_md": "A", "share_scope": "local"},
            {"gid": "b", "creator_gid": "u2", "content_md": "B"},
            {"gid": "c", "creator_gid": None, "content_md": "C"},
            {"gid": "d", "creator_gid": "inactive", "content_md": "D"},
            {"gid": "e", "creator_gid": "u1", "content_md": "E", "share_scope": "global"},
        ]
        result = partition_inventory(
            rows,
            "team-1",
            {"u1": {"team_id": "team-1"}, "u2": {"team_id": "team-2"}},
        )
        self.assertEqual([row["gid"] for row in result["eligible"]], ["a"])
        self.assertEqual([row["gid"] for row in result["other_tenant"]], ["b"])
        self.assertEqual([row["gid"] for row in result["quarantined"]], ["c", "d", "e"])

    def test_migration_preserves_local_vs_team_acl_semantics(self):
        source = Path(__file__).resolve().parents[1].joinpath("scripts/migrate_knowledge_markdown_revisions.py").read_text(encoding="utf-8")
        self.assertIn('share_scope") or "team") == "team"', source)
        self.assertIn("VALUES (%s,'user',%s,'admin',%s)", source)
        self.assertIn("VALUES (%s,'team',%s,'edit',%s)", source)
    def test_inventory_bytes_use_canonical_markdown(self):
        summary = inventory_summary([{"content_md": "A\r\n"}, {"content_md": "中"}])
        self.assertEqual(summary["entries"], 2)
        self.assertEqual(summary["bytes"], len("A\n".encode()) + len("中\n".encode()))

if __name__ == "__main__":
    unittest.main()
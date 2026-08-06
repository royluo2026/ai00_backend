import unittest
from pathlib import Path


class KnowledgeWorkspaceWebContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[2]
        workspace = root.parents[1] if root.parent.name == ".worktrees" else root.parent
        cls.web = (workspace / "workmanship-web/web/knowledge_hub/knowledge_hub.js").read_text(encoding="utf-8")

    def test_team_cocreation_has_distinct_navigation_and_storage_path(self):
        self.assertIn("_makeSpecialNode('workspace'", self.web)
        self.assertIn("knowledge.document.search", self.web)
        self.assertIn("_revisionDocument: true", self.web)

    def test_revision_writes_require_explicit_ui_confirmation_and_gateway_confirmation(self):
        self.assertIn("_confirmDialog('确认发布新版本？", self.web)
        self.assertIn("knowledge.document.revise", self.web)
        self.assertIn(":confirm", self.web)
        self.assertIn("confirmation_token", self.web)

    def test_revision_editor_never_uses_legacy_overwrite_route(self):
        start = self.web.index("async function _renderWorkspaceDocument")
        end = self.web.index("async function _loadWorkspaceHistory", start)
        source = self.web[start:end]
        self.assertNotIn("/api/knowledge_hub/items/", source)
        self.assertIn("knowledge.document.get", source)
        self.assertIn("knowledge.document.rollback", source)

    def test_revision_diff_is_computed_by_capability_not_in_browser(self):
        start = self.web.index("async function _showWorkspaceDiff")
        end = self.web.index("// ── Center 内容渲染", start)
        source = self.web[start:end]
        self.assertIn("knowledge.document.diff", source)
        self.assertNotIn("diffLines", source)
        self.assertIn("textContent = result.data?.diff", source)
    def test_migration_panel_is_read_only_and_capability_backed(self):
        self.assertIn("_makeSpecialNode('migration'", self.web)
        start = self.web.index("async function _renderMigrationStatus")
        end = self.web.index("async function _createWorkspaceDocument", start)
        source = self.web[start:end]
        self.assertIn("knowledge.migration.status", source)
        self.assertIn("实际迁移由部署作业执行", source)
        self.assertNotIn(":confirm", source)
        self.assertNotIn("knowledge.migration.apply", source)
    def test_history_uses_immutable_revision_capability(self):
        self.assertIn("knowledge.document.revisions", self.web)
        self.assertIn("不可变版本历史", self.web)


if __name__ == "__main__":
    unittest.main()

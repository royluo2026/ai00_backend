import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from backend.capabilities.knowledge_documents_next import (
    _evidence,
    diff_document_revisions,
    list_document_acl,
    rollback_document,
    register_knowledge_document_capabilities,
)
from backend.capabilities.registry_next import CapabilityRegistry
from backend.capabilities.models_next import CapabilityContext, CapabilityOutput


class KnowledgeDocumentCapabilityTests(unittest.TestCase):
    def test_revision_evidence_is_stable_and_complete(self):
        evidence = _evidence({
            "title": "标准作业", "tenant_gid": "t1", "space_gid": "s1",
            "document_gid": "d1", "revision_gid": "r2", "revision_no": 2,
            "object_key": "knowledge/t1/s1/d1/revisions/r2/document.abc.md",
            "content_sha256": "a" * 64, "state": "published",
        })
        self.assertEqual(evidence.kind, "ois.revision")
        self.assertTrue(evidence.reference.startswith("ois://knowledge/"))
        self.assertEqual(evidence.digest, "sha256:" + "a" * 64)
        self.assertEqual(evidence.metadata["revision_gid"], "r2")

    def test_write_capabilities_require_confirmation(self):
        registry = CapabilityRegistry()
        register_knowledge_document_capabilities(registry)
        self.assertEqual(registry.get("knowledge.document.create").spec.confirmation, "user")
        self.assertEqual(registry.get("knowledge.document.revise").spec.confirmation, "user")
        self.assertEqual(registry.get("knowledge.document.restore").spec.confirmation, "user")
        self.assertEqual(registry.get("knowledge.document.get").spec.confirmation, "none")
        self.assertTrue(all("knowledge" in spec.tags for spec in registry.list()))

    def test_revision_history_is_registered_read_only(self):
        registry = CapabilityRegistry()
        register_knowledge_document_capabilities(registry)
        spec = registry.get("knowledge.document.history.get").spec
        self.assertEqual(spec.confirmation, "none")
        self.assertEqual(spec.permissions, ())

    def test_document_search_and_acl_are_governed_public_capabilities(self):
        registry = CapabilityRegistry()
        register_knowledge_document_capabilities(registry)
        ids = {spec.id for spec in registry.list()}
        self.assertIn("knowledge.document.search", ids)
        self.assertTrue({
            "knowledge.document.acl.list",
            "knowledge.document.acl.grant",
            "knowledge.document.acl.revoke",
        } <= ids)
        self.assertEqual(registry.get("knowledge.document.acl.list").spec.confirmation, "none")
        self.assertEqual(registry.get("knowledge.document.acl.grant").spec.confirmation, "user")
        self.assertEqual(registry.get("knowledge.document.acl.revoke").spec.confirmation, "user")

    def test_acl_list_serializes_database_values_and_returns_stable_document_evidence(self):
        class Cursor:
            def __init__(self): self.query = 0
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def execute(self, *_args): self.query += 1
            def fetchone(self): return {"gid": "doc_1"}
            def fetchall(self):
                return [{
                    "subject_type": "user", "subject_gid": "user_2", "permission": "view",
                    "created_by": "user_1", "created_at": datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
                }]

        class Connection:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def cursor(self): return Cursor()

        with patch("backend.knowledge.data.connection.get_knowledge_conn", return_value=Connection()):
            result = list_document_acl(
                {"document_gid": "doc_1"}, CapabilityContext(user_gid="user_1", team_gid="tenant_1")
            )

        self.assertEqual(result.data["document_ref"], "knowledge-document:doc_1")
        self.assertEqual(result.data["items"][0]["created_at"], "2026-08-10T12:00:00+00:00")
        self.assertEqual(result.evidence[0].reference, "knowledge-document:doc_1")

    def test_diff_returns_both_revision_evidence(self):
        context = CapabilityContext(user_gid="u", team_gid="t")
        before = CapabilityOutput(
            data={"markdown": "one\n", "revision_no": 1},
            evidence=(_evidence({"title":"D","tenant_gid":"t","space_gid":"s","document_gid":"d","revision_gid":"r1","revision_no":1,"object_key":"k1","content_sha256":"a"*64,"state":"published"}),),
        )
        after = CapabilityOutput(
            data={"markdown": "two\n", "revision_no": 2},
            evidence=(_evidence({"title":"D","tenant_gid":"t","space_gid":"s","document_gid":"d","revision_gid":"r2","revision_no":2,"object_key":"k2","content_sha256":"b"*64,"state":"published"}),),
        )
        with patch("backend.capabilities.knowledge_documents_next.get_document", side_effect=[before, after]):
            result = diff_document_revisions({"document_gid":"d","from_revision_gid":"r1","to_revision_gid":"r2"}, context)
        self.assertIn("-one", result.data["diff"])
        self.assertIn("+two", result.data["diff"])
        self.assertEqual(len(result.evidence), 2)

    def test_restore_publishes_new_revision_from_historical_content(self):
        context = CapabilityContext(user_gid="u", team_gid="t")
        target = CapabilityOutput(data={"title":"D","markdown":"old\n"})
        created = CapabilityOutput(data={"revision_gid":"new"})
        with patch("backend.capabilities.knowledge_documents_next.get_document", return_value=target), patch("backend.capabilities.knowledge_documents_next._create_revision", return_value=created) as create:
            result = rollback_document({"document_gid":"d","base_revision_gid":"r2","target_revision_gid":"r1"}, context)
        self.assertEqual(result.data["revision_gid"], "new")
        payload = create.call_args.args[0]
        self.assertEqual(payload["markdown"], "old\n")
        self.assertEqual(payload["base_revision_gid"], "r2")
        self.assertEqual(payload["_restored_from_revision_gid"], "r1")


if __name__ == "__main__":
    unittest.main()

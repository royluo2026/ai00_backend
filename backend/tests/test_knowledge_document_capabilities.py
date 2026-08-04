import inspect
import unittest
from unittest.mock import patch

from backend.capabilities.knowledge_documents_next import (
    _access_sql,
    _evidence,
    diff_document_revisions,
    rollback_document,
    register_knowledge_document_capabilities,
)
from backend.capabilities.registry_next import CapabilityRegistry
from backend.capabilities.models_next import CapabilityContext, CapabilityOutput


class KnowledgeDocumentCapabilityTests(unittest.TestCase):
    def test_acl_query_is_knowledge_owned_and_tenant_scoped_by_caller(self):
        sql = _access_sql("view")
        self.assertIn("workmanship_know_document_acl", sql)
        self.assertIn("subject_type='user'", sql)
        self.assertIn("subject_type='team'", sql)
        self.assertNotIn("workmanship_auth_", sql)

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
        self.assertEqual(registry.get("knowledge.document.acl.grant").spec.confirmation, "user")
        self.assertEqual(registry.get("knowledge.document.acl.revoke").spec.confirmation, "user")
        self.assertEqual(registry.get("knowledge.document.acl.list").spec.confirmation, "none")
        self.assertEqual(registry.get("knowledge.document.rollback").spec.confirmation, "user")
        self.assertEqual(registry.get("knowledge.document.get").spec.confirmation, "none")
        self.assertTrue(all("knowledge" in spec.tags for spec in registry.list()))


    def test_revision_listing_is_registered_read_only(self):
        registry = CapabilityRegistry()
        register_knowledge_document_capabilities(registry)
        spec = registry.get("knowledge.document.revisions").spec
        self.assertEqual(spec.confirmation, "none")
        self.assertEqual(spec.permissions, ("knowledge.view",))

    def test_private_space_write_and_team_coauthoring_are_explicit(self):
        from backend.capabilities.knowledge_documents_next import _create_revision
        source = inspect.getsource(_create_revision)
        self.assertIn("visibility='team' OR created_by=%s", source)
        self.assertIn("VALUES (%s,'team',%s,'edit',%s)", source)

    def test_acl_revoke_preserves_creator_administration(self):
        from backend.capabilities.knowledge_documents_next import revoke_document_acl
        source = inspect.getsource(revoke_document_acl)
        self.assertIn("document creator admin access cannot be revoked", source)
        self.assertIn("FOR UPDATE", source)
        self.assertIn("subject_gid != tenant", source)
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

    def test_rollback_publishes_new_revision_from_historical_content(self):
        context = CapabilityContext(user_gid="u", team_gid="t")
        target = CapabilityOutput(data={"title":"D","markdown":"old\n"})
        created = CapabilityOutput(data={"revision_gid":"new"})
        with patch("backend.capabilities.knowledge_documents_next.get_document", return_value=target), patch("backend.capabilities.knowledge_documents_next._create_revision", return_value=created) as create:
            result = rollback_document({"document_gid":"d","target_revision_gid":"r1"}, context)
        self.assertEqual(result.data["revision_gid"], "new")
        payload = create.call_args.args[0]
        self.assertEqual(payload["markdown"], "old\n")
        self.assertEqual(payload["_restored_from_revision_gid"], "r1")
if __name__ == "__main__":
    unittest.main()
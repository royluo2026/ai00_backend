"""Document-level edit rights on the test-branch Knowledge Capability."""
import unittest
from unittest.mock import patch

from backend.capabilities.knowledge_documents_next import (
    grant_document_acl,
    revise_document,
)
from backend.capabilities.models_next import CapabilityContext


class _Cursor:
    def __init__(self, *, collaborator=False):
        self.sql = ""
        self.collaborator = collaborator
        self.calls = []
        self.rowcount = 1

    def __enter__(self): return self
    def __exit__(self, *_args): return False

    def execute(self, sql, params=()):
        self.sql = sql
        self.calls.append((sql, params))

    def fetchone(self):
        if "FROM workmanship_know_documents d" in self.sql:
            return {
                "gid": "doc_1", "tenant_gid": "team_1", "space_gid": "space_1",
                "created_by": "creator", "title": "BOP", "current_revision_gid": "rev_1",
                "before_sha256": "a" * 64,
            }
        if "workmanship_know_document_acl" in self.sql:
            return {"permission": "edit"} if self.collaborator else None
        if "MAX(revision_no)" in self.sql:
            return {"n": 1}
        return None


class _Connection:
    def __init__(self, cursor): self._cursor = cursor
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def cursor(self): return self._cursor
    def commit(self): pass


def _profile(role="member"):
    return {"gid": "reader", "team_id": "team_1", "system_role": role, "is_active": True}


class DocumentEditAccessTests(unittest.TestCase):
    def _revise(self, cursor, role="member"):
        with (
            patch("backend.knowledge.data.connection.get_knowledge_conn", return_value=_Connection(cursor)),
            patch("backend.platform_sdk.identity.get_active_identity_profile", return_value=_profile(role)),
            patch("backend.capabilities.knowledge_documents_next.new_knowledge_id", return_value="rev_2"),
            patch("backend.capabilities.knowledge_documents_next.prepare_markdown_revision", return_value="prepared"),
            patch("backend.capabilities.knowledge_documents_next.store_markdown_revision", return_value={
                "object_key": "knowledge/rev_2.md", "sha256": "b" * 64,
                "byte_size": 4, "media_type": "text/markdown; charset=utf-8",
            }),
        ):
            return revise_document(
                {"document_gid": "doc_1", "base_revision_gid": "rev_1", "markdown": "new\n"},
                CapabilityContext(user_gid="reader", team_gid="team_1"),
            )

    def test_team_member_without_explicit_user_grant_cannot_revise(self):
        cursor = _Cursor(collaborator=False)
        with self.assertRaises(PermissionError):
            self._revise(cursor)
        self.assertFalse(any("INSERT INTO workmanship_know_revisions" in sql for sql, _ in cursor.calls))

    def test_explicit_collaborator_can_revise(self):
        result = self._revise(_Cursor(collaborator=True))
        self.assertEqual(result.data["revision_gid"], "rev_2")

    def test_superadmin_can_revise_without_collaborator_grant(self):
        result = self._revise(_Cursor(collaborator=False), role="super_admin")
        self.assertEqual(result.data["revision_gid"], "rev_2")

    def test_creator_cannot_grant_collaborators(self):
        cursor = _Cursor()
        with (
            patch("backend.knowledge.data.connection.get_knowledge_conn", return_value=_Connection(cursor)),
            patch("backend.platform_sdk.identity.get_active_identity_profile", return_value={
                "gid": "creator", "team_id": "team_1", "system_role": "member", "is_active": True,
            }),
            patch("backend.platform_sdk.identity.get_user_summaries", return_value={
                "reader": {"gid": "reader", "team_id": "team_1"},
            }),
        ):
            with self.assertRaises(PermissionError):
                grant_document_acl(
                    {"document_gid": "doc_1", "subject_type": "user", "subject_gid": "reader", "permission": "edit"},
                    CapabilityContext(user_gid="creator", team_gid="team_1"),
                )
        self.assertFalse(any("INSERT INTO workmanship_know_document_acl" in sql for sql, _ in cursor.calls))


if __name__ == "__main__":
    unittest.main()

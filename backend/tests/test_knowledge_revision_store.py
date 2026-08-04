import hashlib
import unittest
from unittest.mock import patch

import backend.core.ois_storage as ois_storage

from backend.knowledge.revision_store import (
    canonical_markdown,
    load_markdown_revision,
    prepare_markdown_revision,
    store_markdown_revision,
)


class KnowledgeRevisionStoreTests(unittest.TestCase):
    def test_markdown_is_canonical_and_content_addressed(self):
        prepared = prepare_markdown_revision(
            tenant_gid="team-1",
            space_gid="space-1",
            document_gid="doc-1",
            revision_gid="rev-1",
            markdown="# 标题\r\n正文",
        )
        self.assertEqual(prepared.markdown, "# 标题\n正文\n")
        self.assertEqual(prepared.sha256, hashlib.sha256(prepared.data).hexdigest())
        self.assertEqual(
            prepared.object_key,
            f"knowledge/team-1/space-1/doc-1/revisions/rev-1/document.{prepared.sha256}.md",
        )

    def test_equivalent_newlines_produce_same_digest(self):
        one = prepare_markdown_revision(
            tenant_gid="t", space_gid="s", document_gid="d", revision_gid="r1", markdown="a\r\nb"
        )
        two = prepare_markdown_revision(
            tenant_gid="t", space_gid="s", document_gid="d", revision_gid="r2", markdown="a\nb\n"
        )
        self.assertEqual(one.sha256, two.sha256)

    def test_unsafe_object_path_segment_is_rejected(self):
        with self.assertRaises(ValueError):
            prepare_markdown_revision(
                tenant_gid="../team", space_gid="s", document_gid="d", revision_gid="r", markdown="x"
            )

    def test_store_fails_closed_and_verifies_reference(self):
        prepared = prepare_markdown_revision(
            tenant_gid="t", space_gid="s", document_gid="d", revision_gid="r", markdown="x"
        )
        with patch.object(ois_storage, "put_immutable", return_value=None):
            with self.assertRaises(RuntimeError):
                store_markdown_revision(prepared)
        with patch.object(
            ois_storage, "put_immutable",
            return_value={"object_key": prepared.object_key, "sha256": prepared.sha256},
        ):
            result = store_markdown_revision(prepared)
        self.assertEqual(result["sha256"], prepared.sha256)

    def test_load_revision_fails_closed_on_missing_or_invalid_utf8(self):
        with patch.object(ois_storage, "get_immutable", return_value=None):
            with self.assertRaises(RuntimeError):
                load_markdown_revision("knowledge/t/s/d/r.md", "a" * 64)
        with patch.object(ois_storage, "get_immutable", return_value=b"\xff"):
            with self.assertRaises(RuntimeError):
                load_markdown_revision("knowledge/t/s/d/r.md", "a" * 64)
        with patch.object(ois_storage, "get_immutable", return_value="正文\n".encode("utf-8")):
            self.assertEqual(load_markdown_revision("knowledge/t/s/d/r.md", "a" * 64), "正文\n")
    def test_canonical_markdown_requires_text(self):
        with self.assertRaises(TypeError):
            canonical_markdown(b"not text")


if __name__ == "__main__":
    unittest.main()
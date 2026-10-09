from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.capability_v2.provider_contracts import CapabilityContext
from plugins.knowledge.knowledge_backend.capabilities.extraction_candidates import _selection_matches, save_candidate


class Cursor:
    def __init__(self, revision="r1"):
        self.revision = revision
        self.queries = []

    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def execute(self, sql, _args): self.queries.append(sql)
    def fetchone(self):
        if len(self.queries) == 1:
            return {"gid": "d1", "created_by": "owner", "published_revision_gid": self.revision}
        return {"object_key": "k", "content_sha256": "a" * 64}


class Connection:
    def __init__(self, cursor): self._cursor = cursor
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def cursor(self): return self._cursor
    def commit(self): pass


PAYLOAD = {"document_gid": "d1", "revision_gid": "r1", "card_type": "ontology", "title": "BOP 版本",
           "body": "应当建为 BOP 的属性", "evidence_text": "BOP 版本", "evidence_from": 0, "evidence_to": 6}


def test_selection_uses_codemirror_utf16_offsets():
    assert _selection_matches("😀BOP 版本", 2, 8, "BOP 版本")
    assert not _selection_matches("😀BOP 版本", 1, 8, "BOP 版本")


def test_candidate_rejects_unpublished_source_revision_before_writing():
    cursor = Cursor(revision="r2")
    with patch("plugins.knowledge.knowledge_backend.capabilities.extraction_candidates.get_knowledge_conn", return_value=Connection(cursor)), \
         patch("plugins.knowledge.knowledge_backend.capabilities.extraction_candidates._require_document_editor"):
        with pytest.raises(ValueError, match="source revision changed"):
            save_candidate(PAYLOAD, CapabilityContext(user_gid="owner", team_gid="t1"))
    assert not any(query.startswith(("INSERT", "UPDATE")) for query in cursor.queries)


def test_candidate_requires_document_editor_before_reading_revision():
    cursor = Cursor()
    with patch("plugins.knowledge.knowledge_backend.capabilities.extraction_candidates.get_knowledge_conn", return_value=Connection(cursor)), \
         patch("plugins.knowledge.knowledge_backend.capabilities.extraction_candidates._require_document_editor", side_effect=PermissionError("denied")):
        with pytest.raises(PermissionError, match="denied"):
            save_candidate(PAYLOAD, CapabilityContext(user_gid="reader", team_gid="t1"))
    assert len(cursor.queries) == 1


def test_candidate_draft_uses_stable_gid_and_exact_saved_evidence():
    class InsertCursor(Cursor):
        def fetchone(self):
            if len(self.queries) == 1:
                return {"gid": "d1", "created_by": "owner", "published_revision_gid": "r1"}
            if len(self.queries) == 2:
                return {"object_key": "k", "content_sha256": "a" * 64}
            return {"gid": "kncand_test", "document_gid": "d1", "revision_gid": "r1", "card_type": "ontology",
                    "title": "BOP 版本", "body": "应当建为 BOP 的属性", "evidence_text": "BOP 版本",
                    "evidence_from": 0, "evidence_to": 6, "evidence_sha256": "a" * 64,
                    "target_gid": None, "status": "draft", "created_by": "owner", "updated_by": "owner",
                    "created_at": None, "updated_at": None}

    cursor = InsertCursor()
    with patch("plugins.knowledge.knowledge_backend.capabilities.extraction_candidates.get_knowledge_conn", return_value=Connection(cursor)), \
         patch("plugins.knowledge.knowledge_backend.capabilities.extraction_candidates._require_document_editor"), \
         patch("plugins.knowledge.knowledge_backend.capabilities.extraction_candidates.load_markdown_revision", return_value="BOP 版本"):
        result = save_candidate(PAYLOAD, CapabilityContext(user_gid="owner", team_gid="t1"))
    assert result.data["gid"] == "kncand_test"
    assert any(query.startswith("INSERT INTO workmanship_know_extraction_candidates") for query in cursor.queries)

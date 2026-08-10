from __future__ import annotations

import inspect
from unittest.mock import patch

import pytest

from backend.capabilities.knowledge_documents_next import (
    _create_revision,
    create_space,
    get_document,
    list_document_revisions,
    list_spaces,
    search_documents,
)
from backend.capabilities.models_next import CapabilityContext


class RecordingCursor:
    def __init__(self, rows):
        self._rows = iter(rows)
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.executed.append((" ".join(str(sql).split()), params))

    def fetchone(self):
        return next(self._rows)


class RecordingConnection:
    def __init__(self, rows):
        self.cursor_instance = RecordingCursor(rows)
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True


def test_normal_document_capabilities_do_not_reference_document_acl():
    handlers = (_create_revision, get_document, search_documents, list_document_revisions)
    for handler in handlers:
        source = inspect.getsource(handler)
        assert "workmanship_know_document_acl" not in source
        assert "_access_sql(" not in source


def test_knowledge_spaces_are_not_access_boundaries_within_tenant():
    source = inspect.getsource(list_spaces) + inspect.getsource(_create_revision)
    assert "visibility='team' OR created_by" not in source
    assert "visibility='team' OR created_by=%s" not in source


def test_new_spaces_and_documents_reject_false_private_visibility():
    context = CapabilityContext(user_gid="member-1", team_gid="t1")
    with pytest.raises(ValueError, match="tenant-wide"):
        create_space({"name": "Private", "visibility": "private"}, context)
    with pytest.raises(ValueError, match="tenant-wide"):
        _create_revision(
            {
                "space_gid": "s1",
                "title": "Private",
                "slug": "private",
                "markdown": "content",
                "visibility": "private",
            },
            context,
            existing=False,
        )


def test_authenticated_tenant_member_can_revise_without_document_acl_predicate():
    connection = RecordingConnection(
        [
            {
                "gid": "d1",
                "title": "Team document",
                "space_gid": "s1",
                "current_revision_gid": "r1",
                "before_sha256": "a" * 64,
            },
            {"n": 1},
        ]
    )
    stored = {
        "object_key": "knowledge/t1/s1/d1/revisions/r2/document.md",
        "sha256": "b" * 64,
        "byte_size": 7,
        "media_type": "text/markdown",
    }
    context = CapabilityContext(user_gid="member-2", team_gid="t1", request_id="req-1")

    with patch("backend.knowledge.data.connection.get_knowledge_conn", return_value=connection), patch(
        "backend.capabilities.knowledge_documents_next.next_gid",
        create=True,
        side_effect=["r2"],
    ), patch(
        "backend.capabilities.knowledge_documents_next.prepare_markdown_revision",
        return_value=object(),
    ), patch(
        "backend.capabilities.knowledge_documents_next.store_markdown_revision",
        return_value=stored,
    ):
        result = _create_revision(
            {
                "document_gid": "d1",
                "base_revision_gid": "r1",
                "markdown": "updated",
                "change_summary": "team edit",
            },
            context,
            existing=True,
        )

    select_sql, select_params = connection.cursor_instance.executed[0]
    assert "workmanship_know_document_acl" not in select_sql
    assert select_params == ("d1", "t1")
    assert result.data["revision_no"] == 2
    assert result.data["content_sha256"] == "b" * 64
    assert connection.committed is True

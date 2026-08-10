from __future__ import annotations

import hashlib
from unittest.mock import patch

import pytest

from backend.capabilities.models_next import CapabilityBusinessError, CapabilityContext
from backend.capabilities.review_next import review_proposal
from backend.knowledge.storage import publish_proposal_markdown


class Cursor:
    def __init__(self, proposal):
        self.proposal = proposal
        self.executed = []

    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def execute(self, sql, params=()): self.executed.append((sql, params))
    def fetchone(self): return self.proposal


class Connection:
    def __init__(self, proposal):
        self.cursor_instance = Cursor(proposal)
        self.committed = False
        self.exited = False

    def __enter__(self): return self
    def __exit__(self, *_args): self.exited = True; return False
    def cursor(self): return self.cursor_instance
    def commit(self): self.committed = True


def _context(user="reviewer"):
    return CapabilityContext(user_gid=user, team_gid="team-1")


def test_review_is_tenant_scoped_and_self_review_is_forbidden():
    connection = Connection({"gid": "p1", "team_gid": "team-1", "creator_gid": "author", "status": "pending"})
    with patch(
        "backend.knowledge.data.connection.get_knowledge_conn", return_value=connection
    ):
        with pytest.raises(CapabilityBusinessError, match="own proposal") as caught:
            review_proposal(
                {"proposal_gid": "p1", "decision": "approved"}, _context("author")
            )

    select_sql, select_params = connection.cursor_instance.executed[0]
    assert "team_gid=%s" in select_sql
    assert select_params == ("p1", "team-1")
    assert caught.value.code == "self_review_forbidden"


def test_approved_review_commits_outbox_before_publication_saga_runs():
    connection = Connection({"gid": "p1", "team_gid": "team-1", "creator_gid": "author", "status": "pending"})

    def retry(_payload, _context):
        assert connection.committed is True
        assert connection.exited is True
        return {"published_gid": "entry-1"}

    with patch(
        "backend.knowledge.data.connection.get_knowledge_conn", return_value=connection
    ), patch("backend.capabilities.outbox_retry_next.retry_publish", side_effect=retry):
        result = review_proposal(
            {"proposal_gid": "p1", "decision": "approved", "review_note": "ok"},
            _context(),
        )

    sql = "\n".join(item[0] for item in connection.cursor_instance.executed)
    assert "workmanship_know_publish_outbox" in sql
    assert "workmanship_know_entries" not in sql
    assert "status='publishing'" in sql
    assert result["published_gid"] == "entry-1"


def test_proposal_publication_uses_a_deterministic_immutable_object_key():
    calls = []

    class Store:
        def put_immutable(self, object_key, data, media_type):
            calls.append((object_key, data, media_type))
            return {"object_key": object_key, "sha256": hashlib.sha256(data).hexdigest()}

        def get_immutable(self, *_args): return None

    with patch("backend.knowledge.storage._store", Store()):
        first = publish_proposal_markdown("proposal-1", "# title\n")
        second = publish_proposal_markdown("proposal-1", "# title\n")

    assert first == second
    assert first["ois_url"].startswith("ois://knowledge/proposals/proposal-1/")
    assert calls[0][0] == calls[1][0]

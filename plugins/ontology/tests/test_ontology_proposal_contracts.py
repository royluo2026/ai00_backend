from datetime import UTC, datetime
from types import SimpleNamespace

from jsonschema import Draft202012Validator

from plugins.ontology.ontology_backend.capabilities import ontology_proposals_next as proposals


ACTIVE_RELEASE = {
    "release_gid": "release-1",
    "content_sha256": "a" * 64,
}


class ProposalRepository:
    def search(self, *, status=None, limit=50):
        return [{
            "proposal_gid": "proposal-1",
            "base_release_gid": "release-1",
            "status": "review",
            "author_gid": "user-1",
            "channel": "web",
            "updated_at": datetime(2026, 9, 8, 9, 30, tzinfo=UTC),
        }]

    def get(self, proposal_gid):
        return {
            "proposal_gid": proposal_gid,
            "proposal_revision_gid": "revision-1",
            "revision_no": 1,
            "base_release_gid": "release-1",
            "content_sha256": "b" * 64,
            "changes": [],
            "status": "review",
            "author_gid": "user-1",
            "channel": "web",
            "created_at": datetime(2026, 9, 8, 9, 30, tzinfo=UTC),
        }


class ReleaseRepository:
    def resolve_release(self, release_gid):
        assert release_gid == "release-1"
        return ACTIVE_RELEASE


def test_proposal_reads_serialize_database_timestamps_for_v2_contract(monkeypatch):
    monkeypatch.setattr(proposals, "OntologyProposalRepository", ProposalRepository)
    monkeypatch.setattr(proposals, "OntologyReleaseRepository", ReleaseRepository)

    search = proposals.search_proposals({}, SimpleNamespace())
    Draft202012Validator(proposals.PROPOSAL_SEARCH_V2_SCHEMA).validate(search)

    detail = proposals.get_proposal({"proposal_gid": "proposal-1"}, SimpleNamespace()).data
    Draft202012Validator(proposals.PROPOSAL_SCHEMA).validate(detail)

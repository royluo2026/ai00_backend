from datetime import datetime
from unittest.mock import Mock, patch

from plugins.ontology.ontology_backend.capabilities import ontology_proposals_next as proposals
from plugins.ontology.ontology_backend.capabilities import ontology_releases_next as releases
from plugins.ontology.ontology_backend.capabilities.ontology_releases_next import register_ontology_release_capabilities
from backend.capabilities.registry_next import CapabilityRegistry


def test_reviewable_proposal_reads_bound_history_and_independent_approval():
    repository = Mock()
    repository.get.return_value = {
        "proposal_gid": "p1", "proposal_revision_gid": "pr1", "revision_no": 1,
        "base_release_gid": "r1", "content_sha256": "a" * 64, "changes": [],
        "status": "review", "author_gid": "author",
    }
    repository.list_reviews.return_value = [{
        "review_gid": "review1", "proposal_gid": "p1", "proposal_revision_gid": "pr1",
        "content_sha256": "a" * 64, "decision": "approve", "reviewer_gid": "reviewer",
        "comment": "Checked", "created_at": datetime(2026, 10, 12),
    }]
    release_repository = Mock()
    release_repository.resolve_release.return_value = {"release_gid": "r1", "content_sha256": "b" * 64}
    with patch.object(proposals, "OntologyProposalRepository", return_value=repository), patch.object(proposals, "OntologyReleaseRepository", return_value=release_repository):
        result = proposals.get_reviewable_proposal({"proposal_gid": "p1"}, None).data
    repository.list_reviews.assert_called_once_with("p1", "pr1")
    assert result["publishable"] is True
    assert result["reviews"][0]["created_at"] == "2026-10-12T00:00:00"


def test_legacy_proposal_read_keeps_its_existing_output():
    repository = Mock()
    repository.get.return_value = {
        "proposal_gid": "p1", "proposal_revision_gid": "pr1", "revision_no": 1,
        "base_release_gid": "r1", "content_sha256": "a" * 64, "changes": [],
        "status": "review", "author_gid": "author",
    }
    release_repository = Mock()
    release_repository.resolve_release.return_value = {"release_gid": "r1", "content_sha256": "b" * 64}
    with patch.object(proposals, "OntologyProposalRepository", return_value=repository), patch.object(proposals, "OntologyReleaseRepository", return_value=release_repository):
        result = proposals.get_proposal({"proposal_gid": "p1"}, None).data
    repository.list_reviews.assert_not_called()
    assert "reviews" not in result and "publishable" not in result


def test_release_queries_declare_the_existing_target_and_limit_arguments():
    registry = CapabilityRegistry()
    register_ontology_release_capabilities(registry)
    assert "release_gid" in registry.get("ontology.release.get").spec.input_schema["properties"]
    assert registry.get("ontology.release.search").spec.input_schema["properties"]["limit"]["maximum"] == 100


def test_release_search_serializes_database_timestamps():
    repository = Mock()
    repository.search_releases.return_value = [{"release_gid": "r1", "content_sha256": "b" * 64,
        "created_at": datetime(2026, 10, 12)}]
    with patch.object(releases, "OntologyReleaseRepository", return_value=repository):
        result = releases.search_releases({"limit": 100}, None)
    assert result["items"][0]["created_at"] == "2026-10-12T00:00:00"

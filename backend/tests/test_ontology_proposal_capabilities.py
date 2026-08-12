from unittest.mock import Mock, patch

import pytest

from backend.capabilities.models_next import CapabilityBusinessError, CapabilityContext
from backend.capabilities.ontology_proposals_next import (
    create_proposal,
    register_ontology_proposal_capabilities,
    submit_review,
)
from backend.capabilities.registry_next import CapabilityRegistry
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec as adapt_v1_spec
from backend.ontology.proposals import normalize_changes
from backend.ontology.review_policy import is_publishable


HUMAN = CapabilityContext(user_gid="u1", source="web", permissions=("ontology.review",))


def test_proposal_requires_exact_active_base_release():
    repository = Mock()
    repository.get_active.return_value = {"release_gid": "r2", "release_sha256": "b" * 64}
    with patch("backend.capabilities.ontology_proposals_next.OntologyProposalRepository", return_value=repository):
        with pytest.raises(CapabilityBusinessError) as caught:
            create_proposal(
                {"base_release_gid": "r1", "changes": [{"operation": "concept.add", "stable_gid": "c1", "value": {"name": "工位"}}]},
                HUMAN,
            )
    assert caught.value.code == "base_release_conflict"
    repository.create.assert_not_called()


def test_agent_cannot_submit_formal_review():
    repository = Mock()
    with patch("backend.capabilities.ontology_proposals_next.OntologyProposalRepository", return_value=repository):
        with pytest.raises(CapabilityBusinessError, match="human reviewer"):
            submit_review(
                {"proposal_gid": "p1", "proposal_revision_gid": "pr1", "content_sha256": "a" * 64, "decision": "approve"},
                CapabilityContext(user_gid="agent1", source="agent", permissions=("ontology.review",)),
            )
    repository.save_review.assert_not_called()


def test_author_cannot_be_only_approver():
    reviews = [{"reviewer_gid": "author", "decision": "approve", "content_sha256": "a" * 64}]
    assert is_publishable(reviews=reviews, author_gid="author", content_sha256="a" * 64) is False
    reviews.append({"reviewer_gid": "reviewer", "decision": "approve", "content_sha256": "a" * 64})
    assert is_publishable(reviews=reviews, author_gid="author", content_sha256="a" * 64) is True


def test_proposal_author_cannot_submit_approve_decision():
    repository = Mock()
    repository.get.return_value = {
        "proposal_gid": "p1", "proposal_revision_gid": "pr1",
        "content_sha256": "a" * 64, "author_gid": "u1",
    }
    with patch("backend.capabilities.ontology_proposals_next.OntologyProposalRepository", return_value=repository):
        with pytest.raises(CapabilityBusinessError) as caught:
            submit_review({
                "proposal_gid": "p1", "proposal_revision_gid": "pr1",
                "content_sha256": "a" * 64, "decision": "approve",
            }, HUMAN)

    assert caught.value.code == "independent_reviewer_required"
    repository.save_review.assert_not_called()


def test_typed_changes_are_normalized_and_invalid_operations_rejected():
    normalized = normalize_changes([
        {"operation": "property.change", "stable_gid": "p1", "value": {"value_type": "number"}},
        {"operation": "parent.change", "stable_gid": "c1", "value": {"parent_stable_gid": "c0"}},
    ])
    assert [item["operation"] for item in normalized] == ["parent.change", "property.change"]
    with pytest.raises(ValueError, match="operation"):
        normalize_changes([{"operation": "release.delete", "stable_gid": "r1", "value": {}}])


def test_constraint_changes_are_first_class_reviewed_proposals():
    normalized = normalize_changes([{
        "operation": "constraint.change",
        "stable_gid": "constraint.operation.duration",
        "value": {"minimum": 1, "required": True},
        "source_evidence": [{"kind": "standard", "reference": "std-1"}],
    }])

    assert normalized[0]["operation"] == "constraint.change"
    assert normalized[0]["source_evidence"][0]["reference"] == "std-1"


def test_review_binds_exact_revision_hash_and_returns_immutable_ref():
    repository = Mock()
    repository.save_review.return_value = {
        "review_gid": "rv1", "proposal_gid": "p1", "proposal_revision_gid": "pr1",
        "content_sha256": "a" * 64, "decision": "approve", "reviewer_gid": "u1",
    }
    with patch("backend.capabilities.ontology_proposals_next.OntologyProposalRepository", return_value=repository):
        result = submit_review(
            {"proposal_gid": "p1", "proposal_revision_gid": "pr1", "content_sha256": "a" * 64, "decision": "approve"},
            HUMAN,
        )
    assert result.data["review_gid"] == "rv1"
    assert result.evidence[0].digest == "sha256:" + "a" * 64


def test_proposal_capabilities_have_governed_write_and_review_contracts():
    registry = CapabilityRegistry()
    register_ontology_proposal_capabilities(registry)
    assert registry.get("ontology.change.proposal.create").spec.confirmation == "user"
    assert registry.get("ontology.change.proposal.review.submit").spec.permissions == ("ontology.review",)
    assert registry.get("ontology.change.proposal.review.submit").spec.confirmation == "user"

    read_descriptor = adapt_v1_spec(registry.get("ontology.change.proposal.get").spec)
    assert "base_ontology_version_ref" in read_descriptor.output_schema["properties"]

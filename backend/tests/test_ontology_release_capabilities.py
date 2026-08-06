from unittest.mock import Mock, patch

import pytest

from backend.capabilities.models_next import CapabilityBusinessError, CapabilityContext
from backend.capabilities.ontology_releases_next import (
    activate_release,
    publish_release,
    register_ontology_release_capabilities,
)
from backend.capabilities.registry_next import CapabilityRegistry
from backend.ontology.diff import semantic_diff


PUBLISHER = CapabilityContext(user_gid="u1", source="web", permissions=("ontology.publish",))
ADMIN = CapabilityContext(user_gid="admin", source="web", permissions=("ontology.activate",))


def _proposal():
    return {
        "proposal_gid": "p1", "proposal_revision_gid": "pr1", "base_release_gid": "r1",
        "content_sha256": "a" * 64, "author_gid": "author", "status": "review",
        "changes": [{"operation": "concept.add", "stable_gid": "c2", "value": {"name": "工位"}, "source_evidence": []}],
    }


def test_publish_creates_immutable_release_without_changing_active_ref():
    release_repository = Mock()
    release_repository.resolve_release.side_effect = [
        {"release_gid": "r1", "content_sha256": "1" * 64, "ois_object_key": "ontology/r1.json"},
    ]
    release_repository.list_objects.return_value = [
        {"kind": "concept", "stable_gid": "c1", "name": "线体"},
    ]
    release_repository.create_release.return_value = {
        "release_gid": "r2", "parent_release_gid": "r1", "content_sha256": "2" * 64,
        "object_count": 2, "ois_object_key": "ontology/releases/r2.json",
    }
    proposal_repository = Mock()
    proposal_repository.get.return_value = _proposal()
    proposal_repository.list_reviews.return_value = [
        {"reviewer_gid": "reviewer", "decision": "approve", "content_sha256": "a" * 64},
    ]
    with patch("backend.capabilities.ontology_releases_next.OntologyReleaseRepository", return_value=release_repository), patch(
        "backend.capabilities.ontology_releases_next.OntologyProposalRepository", return_value=proposal_repository
    ), patch("backend.capabilities.ontology_releases_next.next_gid", return_value="r2"), patch(
        "backend.capabilities.ontology_releases_next.put_immutable",
        return_value={"object_key": "ontology/releases/r2/release.snapshot.json", "sha256": "placeholder"},
    ) as writer:
        writer.side_effect = lambda key, data, mime: {"object_key": key, "sha256": __import__("hashlib").sha256(data).hexdigest()}
        result = publish_release(
            {"proposal_gid": "p1", "proposal_revision_gid": "pr1", "content_sha256": "a" * 64},
            PUBLISHER,
        )
    assert result.data["release_gid"] == "r2"
    release_repository.activate.assert_not_called()
    release_repository.create_release.assert_called_once()


def test_activate_rejects_unmet_migration_gate():
    with pytest.raises(CapabilityBusinessError) as caught:
        activate_release(
            {
                "release_gid": "r2", "release_sha256": "2" * 64,
                "expected_active_release_gid": "r1",
                "attestations": [{"provider": "rules", "status": "passed", "blocking_count": 0}],
            },
            ADMIN,
        )
    assert caught.value.code == "activation_gate_failed"
    assert "migration" in str(caught.value.details)


def test_release_diff_is_semantic_not_raw_json():
    result = semantic_diff(
        [{"kind": "concept", "stable_gid": "c1", "name": "A"}],
        [
            {"kind": "concept", "stable_gid": "c1", "name": "B"},
            {"kind": "property", "stable_gid": "p1", "name": "x", "value_type": "number"},
        ],
    )
    assert set(result) >= {"concepts", "properties", "relations", "mappings", "constraints", "compatibility"}
    assert result["concepts"]["changed"][0]["stable_gid"] == "c1"
    assert result["properties"]["added"][0]["stable_gid"] == "p1"


def test_release_capabilities_separate_publish_and_activation_authority():
    registry = CapabilityRegistry()
    register_ontology_release_capabilities(registry)
    publish = registry.get("ontology.release.publish").spec
    activate = registry.get("ontology.release.activate").spec
    assert publish.permissions == ("ontology.publish",)
    assert activate.permissions == ("ontology.activate",)
    assert publish.confirmation == "admin"
    assert activate.confirmation == "admin"

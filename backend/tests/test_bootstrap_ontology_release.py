from unittest.mock import Mock

from backend.ontology.canonical import canonicalize_release
from backend.scripts.bootstrap_ontology_release import bootstrap_ontology_release


OBJECTS = [
    {"kind": "concept", "stable_gid": "c1", "name": "工位", "aliases": []},
    {"kind": "property", "stable_gid": "p1", "name": "节拍", "value_type": "number"},
]


def test_dry_run_emits_counts_and_hash_without_writes():
    repository = Mock()
    result = bootstrap_ontology_release(
        repository=repository, objects=OBJECTS, actor_gid="u1", dry_run=True,
        snapshot_writer=Mock(), gid_factory=lambda: "r1",
    )
    assert result["dry_run"] is True
    assert result["object_count"] == 2
    assert len(result["content_sha256"]) == 64
    repository.create_release.assert_not_called()
    repository.activate.assert_not_called()


def test_second_run_returns_existing_bootstrap_release_without_duplication():
    repository = Mock()
    repository.find_by_source.return_value = {
        "release_gid": "r1", "content_sha256": "a" * 64, "object_count": 2,
    }
    writer = Mock()
    result = bootstrap_ontology_release(
        repository=repository, objects=OBJECTS, actor_gid="u1", dry_run=False,
        snapshot_writer=writer, gid_factory=lambda: "r2",
    )
    assert result["release_gid"] == "r1"
    assert result["existing"] is True
    writer.assert_not_called()
    repository.create_release.assert_not_called()


def test_real_bootstrap_verifies_snapshot_then_creates_and_activates_once():
    repository = Mock()
    repository.find_by_source.return_value = None
    repository.get_active.return_value = None
    digest = canonicalize_release(OBJECTS)[1]
    repository.create_release.return_value = {
        "release_gid": "r1", "content_sha256": digest, "object_count": 2,
    }
    writer = Mock(return_value={"object_key": f"ontology/releases/r1/release.{digest}.json", "sha256": digest})
    result = bootstrap_ontology_release(
        repository=repository, objects=OBJECTS, actor_gid="u1", dry_run=False,
        snapshot_writer=writer, gid_factory=lambda: "r1",
    )
    assert result["release_gid"] == "r1"
    repository.create_release.assert_called_once()
    repository.activate.assert_called_once_with(
        ref_name="default", release_gid="r1", expected_release_gid=None,
        release_sha256=digest, actor_gid="u1",
    )

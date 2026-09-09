import pytest

from plugins.craft.craft_backend.data.bop_repository import (
    BopRepositoryError,
    BopRepositoryStore,
    MemoryBopRepositoryStore,
)


def _store():
    return MemoryBopRepositoryStore(gid_source=iter(range(100, 200)).__next__)


def test_mysql_store_exposes_the_same_foundation_operations():
    required = {
        "create_repository", "create_personal_space", "get_space",
        "save_space_version", "freeze_team_space", "set_baseline",
        "delete_personal_space",
    }
    assert required <= set(dir(BopRepositoryStore))


def test_create_repository_is_idempotent_and_enforces_project_slot():
    store = _store()
    first = store.create_repository(
        project_gid="10", tenant_gid="20", actor_gid="30", idempotency_key="r-1"
    )
    assert store.create_repository(
        project_gid="10", tenant_gid="20", actor_gid="30", idempotency_key="r-1"
    ) == first
    assert first["team_space_gid"] and first["head_gid"]
    with pytest.raises(BopRepositoryError, match="target_repository_exists"):
        store.create_repository(
            project_gid="10", tenant_gid="20", actor_gid="30", idempotency_key="r-2"
        )


def test_same_idempotency_key_with_different_payload_is_rejected():
    store = _store()
    store.create_repository(
        project_gid="10", tenant_gid="20", actor_gid="30", idempotency_key="same"
    )
    with pytest.raises(BopRepositoryError, match="idempotency_conflict"):
        store.create_repository(
            project_gid="11", tenant_gid="20", actor_gid="30", idempotency_key="same"
        )


def test_space_version_is_immutable_and_freeze_uses_head_cas():
    store = _store()
    created = store.create_repository(
        project_gid="10", tenant_gid="20", actor_gid="30", idempotency_key="create"
    )
    version = store.save_space_version(
        space_gid=created["team_space_gid"], tenant_gid="20", actor_gid="30",
        expected_head_version=1, version_kind="saved", source_refs=[],
        algorithm_versions={}, idempotency_key="save-1",
    )
    frozen = store.freeze_team_space(
        space_gid=created["team_space_gid"], tenant_gid="20", actor_gid="30",
        expected_head_version=1, version_gid=version["version_gid"],
        idempotency_key="freeze-1",
    )
    assert frozen["frozen_version_gid"] == version["version_gid"]
    with pytest.raises(BopRepositoryError, match="resource_version_conflict"):
        store.freeze_team_space(
            space_gid=created["team_space_gid"], tenant_gid="20", actor_gid="30",
            expected_head_version=1, version_gid=version["version_gid"],
            idempotency_key="freeze-2",
        )


def test_baseline_must_be_an_immutable_version_of_same_repository_team_space():
    store = _store()
    left = store.create_repository(
        project_gid="10", tenant_gid="20", actor_gid="30", idempotency_key="left"
    )
    right = store.create_repository(
        project_gid="11", tenant_gid="20", actor_gid="30", idempotency_key="right"
    )
    foreign = store.save_space_version(
        space_gid=right["team_space_gid"], tenant_gid="20", actor_gid="30",
        expected_head_version=1, version_kind="saved", source_refs=[],
        algorithm_versions={}, idempotency_key="foreign-version",
    )
    with pytest.raises(BopRepositoryError, match="baseline_version_invalid"):
        store.set_baseline(
            repository_gid=left["repository_gid"], tenant_gid="20", actor_gid="30",
            expected_row_version=1, version_gid=foreign["version_gid"],
            idempotency_key="baseline",
        )


def test_personal_tombstone_does_not_change_team_head():
    store = _store()
    created = store.create_repository(
        project_gid="10", tenant_gid="20", actor_gid="30", idempotency_key="create"
    )
    personal = store.create_personal_space(
        repository_gid=created["repository_gid"], tenant_gid="20", owner_gid="30",
        actor_gid="30", idempotency_key="personal",
    )
    before = store.get_space(created["team_space_gid"], tenant_gid="20", actor_gid="30")
    store.delete_personal_space(
        space_gid=personal["space_gid"], tenant_gid="20", owner_gid="30",
        expected_row_version=1, idempotency_key="delete",
    )
    after = store.get_space(created["team_space_gid"], tenant_gid="20", actor_gid="30")
    assert before == after

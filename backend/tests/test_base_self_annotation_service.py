from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy

import pytest


ATTACHMENT = {
    "attachment_gid": "att_1",
    "media_type": "image/png",
    "display_name": "photo.png",
    "size": 42,
    "checksum": "sha256:" + "a" * 64,
}
CHANGE = {
    "item_gid": "item_1", "expected_revision": 1, "status": "open",
    "schedule": "2026-08-28", "note": "note", "attachments": [ATTACHMENT],
    "idempotency_key": "idem-ann-1",
}
OWNER = {"gid": "user_owner", "tenant_gid": "tenant_1", "visible_attachment_gids": ["att_1"]}
OTHER = {"gid": "user_other", "tenant_gid": "tenant_1", "visible_attachment_gids": ["att_1"]}


class FakeAnnotationRepository:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str, str], dict] = {}
        self.replays: dict[tuple[str, str, str, str], tuple[str, dict]] = {}
        self.claimed: dict[tuple[str, str, str, str], str] = {}
        self.audits: list[dict] = []
        self.locked: list[tuple[str, str]] = []

    @contextmanager
    def transaction(self):
        yield self

    def get(self, *, tenant_gid: str, actor_gid: str, item_gid: str, lock: bool = False) -> dict | None:
        if lock:
            self.locked.append((actor_gid, item_gid))
        row = self.rows.get((tenant_gid, actor_gid, item_gid))
        return deepcopy(row) if row else None

    def list(self, *, tenant_gid: str, actor_gid: str, limit: int, status: str | None, module: str | None) -> list[dict]:
        rows = [deepcopy(row) for (tenant, owner, _), row in self.rows.items()
                if tenant == tenant_gid and owner == actor_gid and not row["deleted"]
                and (status is None or row["status"] == status) and (module is None or row["module"] == module)]
        return rows[:limit]

    def batch(self, *, tenant_gid: str, actor_gid: str, item_gids: list[str]) -> list[dict]:
        return [deepcopy(self.rows[(tenant_gid, actor_gid, gid)]) for gid in item_gids if (tenant_gid, actor_gid, gid) in self.rows]

    def save(self, row: dict) -> None:
        self.rows[(row["tenant_gid"], row["actor_gid"], row["item_gid"])] = deepcopy(row)

    def claim(self, *, tenant_gid: str, actor_gid: str, operation: str, idempotency_key: str, command_digest: str) -> dict | None:
        key = (tenant_gid, actor_gid, operation, idempotency_key)
        value = self.replays.get(key)
        if value and value[0] != command_digest:
            from backend.base.self_annotations import SelfAnnotationError
            raise SelfAnnotationError("idempotency_conflict", "different command")
        self.claimed[key] = command_digest
        return deepcopy(value[1]) if value else None

    def complete(self, *, tenant_gid: str, actor_gid: str, operation: str, idempotency_key: str, result: dict, item_gid: str) -> None:
        key = (tenant_gid, actor_gid, operation, idempotency_key)
        self.replays[key] = (self.claimed[key], deepcopy(result))

    def audit(self, event: dict) -> None:
        self.audits.append(deepcopy(event))


class FakeAttachmentVisibilityPort:
    def __init__(self, allowed: set[tuple[str, str, str]] = set()) -> None:
        self.allowed = allowed
        self.calls: list[tuple[str, str, str]] = []

    def new_reference_visible(self, *, actor: dict, reference: dict) -> bool:
        key = (str(actor["gid"]), str(actor.get("tenant_gid", actor.get("team_id"))), reference["attachment_gid"])
        self.calls.append(key)
        return key in self.allowed


@pytest.fixture
def service():
    from backend.base.self_annotations import SelfAnnotationService

    return SelfAnnotationService(
        repository=FakeAnnotationRepository(),
        visibility_port=FakeAttachmentVisibilityPort({("user_owner", "tenant_1", "att_1"), ("user_other", "tenant_1", "att_1")} ),
    )


def test_get_and_search_are_actor_bound_and_search_is_bounded(service):
    service.apply_change(actor=OWNER, command=CHANGE)
    service.apply_change(actor=OTHER, command={**CHANGE, "status": "done", "idempotency_key": "other"})

    assert service.get(actor=OWNER, item_gid="item_1")["annotation"]["status"] == "open"
    assert service.search(actor=OWNER, query={"limit": 200})["items"] == [
        service.get(actor=OWNER, item_gid="item_1")["annotation"]
    ]
    with pytest.raises(Exception) as caught:
        service.search(actor=OWNER, query={"limit": 201})
    assert caught.value.code == "invalid_input"


def test_search_honors_the_bounded_actor_scoped_module_filter(service):
    service.repository.rows[(OWNER["tenant_gid"], OWNER["gid"], "item_1") ] = {
        "item_gid": "item_1", "tenant_gid": OWNER["tenant_gid"], "actor_gid": OWNER["gid"], "module": "craft",
        "status": "open", "schedule": None, "note": "", "attachments": [], "revision": 1, "deleted": False, "restore": None,
    }
    service.repository.rows[(OWNER["tenant_gid"], OWNER["gid"], "item_2")] = {
        "item_gid": "item_2", "tenant_gid": OWNER["tenant_gid"], "actor_gid": OWNER["gid"], "module": "knowledge",
        "status": "open", "schedule": None, "note": "", "attachments": [], "revision": 1, "deleted": False, "restore": None,
    }

    assert [item["item_gid"] for item in service.search(actor=OWNER, query={"module": "craft"})["items"]] == ["item_1"]
    with pytest.raises(Exception) as caught:
        service.search(actor=OWNER, query={"module": "x" * 129})
    assert caught.value.code == "invalid_input"


def test_write_is_locked_revisioned_idempotent_and_audited(service):
    first = service.apply_change(actor=OWNER, command=CHANGE)
    replay = service.apply_change(actor=OWNER, command=CHANGE)

    assert replay == first
    assert first["annotation"]["revision"] == 2
    assert service.repository.locked == [(OWNER["gid"], "item_1")]
    assert len(service.repository.audits) == 1
    with pytest.raises(Exception) as caught:
        service.apply_change(actor=OWNER, command={**CHANGE, "idempotency_key": "stale"})
    assert caught.value.code == "revision_conflict"


def test_write_rejects_unknown_keys_and_invisible_or_opaque_attachments(service):
    for command in (
        {**CHANGE, "unknown": True},
        {**CHANGE, "attachments": [{**ATTACHMENT, "token": "secret"}]},
        {**CHANGE, "attachments": [{**ATTACHMENT, "attachment_gid": "att_private"}]},
    ):
        with pytest.raises(Exception) as caught:
            service.apply_change(actor=OWNER, command=command)
        assert caught.value.code in {"invalid_input", "attachment_not_visible"}


def test_attachment_visibility_uses_actor_tenant_registry_and_preserves_exact_existing_reference(service):
    from backend.base.self_annotations import SelfAnnotationService

    repository = FakeAnnotationRepository()
    port = FakeAttachmentVisibilityPort({("user_owner", "tenant_1", "att_1")})
    svc = SelfAnnotationService(repository=repository, visibility_port=port)
    first = svc.apply_change(actor=OWNER, command=CHANGE)
    assert first["annotation"]["attachments"] == [ATTACHMENT]
    assert port.calls == [("user_owner", "tenant_1", "att_1")]

    port.allowed.clear()
    preserved = svc.apply_change(actor=OWNER, command={**CHANGE, "expected_revision": 2, "idempotency_key": "idem-ann-2"})
    assert preserved["annotation"]["attachments"] == [ATTACHMENT]
    with pytest.raises(Exception) as caught:
        svc.apply_change(actor=OTHER, command={**CHANGE, "idempotency_key": "other-denied"})
    assert caught.value.code == "attachment_not_visible"


def test_explicit_empty_deleted_change_is_a_recoverable_tombstone(service):
    service.apply_change(actor=OWNER, command=CHANGE)
    deleted = service.apply_change(actor=OWNER, command={
        "item_gid": "item_1", "expected_revision": 2, "status": "deleted",
        "schedule": None, "note": "", "attachments": [], "idempotency_key": "delete-1",
    })

    assert deleted["annotation"]["deleted"] is True
    assert deleted["annotation"]["restore"]["available"] is True
    assert service.search(actor=OWNER, query={}) == {"items": []}


def test_annotation_state_and_replay_are_tenant_and_command_digest_bound():
    from backend.base.self_annotations import SelfAnnotationService

    repository = FakeAnnotationRepository()
    port = FakeAttachmentVisibilityPort({
        ("user_owner", "tenant_a", "att_1"),
        ("user_owner", "tenant_b", "att_1"),
    })
    service = SelfAnnotationService(repository=repository, visibility_port=port)
    tenant_a = {"gid": "user_owner", "tenant_gid": "tenant_a"}
    tenant_b = {"gid": "user_owner", "tenant_gid": "tenant_b"}

    first = service.apply_change(actor=tenant_a, command=CHANGE)["annotation"]
    second = service.apply_change(actor=tenant_b, command=CHANGE)["annotation"]
    assert first["status"] == second["status"] == "open"
    assert service.get(actor=tenant_a, item_gid="item_1")["annotation"] == first
    assert service.get(actor=tenant_b, item_gid="item_1")["annotation"] == second

    with pytest.raises(Exception) as caught:
        service.apply_change(actor=tenant_a, command={**CHANGE, "note": "different"})
    assert caught.value.code == "idempotency_conflict"


def test_batch_is_one_owner_service_operation_and_suppresses_tombstones(service):
    service.apply_change(actor=OWNER, command=CHANGE)
    service.apply_change(actor=OWNER, command={
        "item_gid": "item_2", "expected_revision": 1, "status": "deleted",
        "schedule": None, "note": "", "attachments": [], "idempotency_key": "delete-item-2",
    })

    assert service.batch(actor=OWNER, item_gids=["item_1", "item_2"]) == {"items": [{
        "item_gid": "item_1", "status": "open", "schedule": "2026-08-28",
        "has_note": True, "attach_count": 1,
    }]}


def test_search_pushes_filters_and_requested_limit_into_repository():
    from backend.base.self_annotations import SelfAnnotationService

    class RecordingRepository(FakeAnnotationRepository):
        def __init__(self):
            super().__init__()
            self.list_query = None

        def list(self, **query):
            self.list_query = query
            return []

    repository = RecordingRepository()
    service = SelfAnnotationService(repository=repository, visibility_port=FakeAttachmentVisibilityPort())
    assert service.search(actor=OWNER, query={"limit": 7, "status": "open", "module": "craft"}) == {"items": []}
    assert repository.list_query == {
        "tenant_gid": "tenant_1", "actor_gid": "user_owner",
        "limit": 7, "status": "open", "module": "craft",
    }


def test_legacy_projection_never_echoes_malformed_attachment_objects():
    from backend.base.self_annotations import _decode

    row = {
        "item_gid": "item_1", "user_gid": "user_owner", "tenant_gid": "tenant_1",
        "self_attachments": [{**ATTACHMENT, "credential": "secret"}],
    }

    assert _decode(row)["attachments"] == []


def test_existing_typed_attachment_is_backfilled_into_registry_before_reuse():
    from backend.base.self_annotations import SelfAnnotationService

    class BackfillingPort(FakeAttachmentVisibilityPort):
        def __init__(self):
            super().__init__()
            self.backfilled = []

        def register_legacy_reference(self, *, actor, reference):
            self.backfilled.append((actor["tenant_gid"], reference["attachment_gid"]))
            self.allowed.add((actor["gid"], actor["tenant_gid"], reference["attachment_gid"]))

    repository = FakeAnnotationRepository()
    repository.rows[(OWNER["tenant_gid"], OWNER["gid"], "item_1")] = {
        "item_gid": "item_1", "actor_gid": OWNER["gid"], "tenant_gid": OWNER["tenant_gid"],
        "module": "", "status": "open", "schedule": None, "note": "", "attachments": [ATTACHMENT],
        "revision": 1, "deleted": False, "restore": None,
    }
    port = BackfillingPort()
    service = SelfAnnotationService(repository=repository, visibility_port=port)
    service.apply_change(actor=OWNER, command={**CHANGE, "schedule": None, "note": "", "idempotency_key": "legacy-reuse"})

    assert port.backfilled == [("tenant_1", "att_1")]


def test_annotation_delete_persists_a_real_deletion_timestamp(service):
    service.apply_change(actor=OWNER, command=CHANGE)
    deleted = service.apply_change(actor=OWNER, command={
        "item_gid": "item_1", "expected_revision": 2, "status": "deleted",
        "schedule": None, "note": "", "attachments": [], "idempotency_key": "delete-timestamp",
    })["annotation"]

    assert deleted["restore"]["deleted_at"] != "transaction"
    assert "T" in deleted["restore"]["deleted_at"]

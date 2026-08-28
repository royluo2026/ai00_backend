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
        self.rows: dict[tuple[str, str], dict] = {}
        self.replays: dict[tuple[str, str, str], dict] = {}
        self.audits: list[dict] = []
        self.locked: list[tuple[str, str]] = []

    @contextmanager
    def transaction(self):
        yield self

    def get(self, *, actor_gid: str, item_gid: str, lock: bool = False) -> dict | None:
        if lock:
            self.locked.append((actor_gid, item_gid))
        row = self.rows.get((actor_gid, item_gid))
        return deepcopy(row) if row else None

    def list(self, *, actor_gid: str) -> list[dict]:
        return [deepcopy(row) for (owner, _), row in self.rows.items() if owner == actor_gid]

    def save(self, row: dict) -> None:
        self.rows[(row["actor_gid"], row["item_gid"])] = deepcopy(row)

    def claim(self, *, actor_gid: str, operation: str, idempotency_key: str) -> dict | None:
        value = self.replays.get((actor_gid, operation, idempotency_key))
        return deepcopy(value) if value else None

    def complete(self, *, actor_gid: str, operation: str, idempotency_key: str, result: dict, item_gid: str) -> None:
        self.replays[(actor_gid, operation, idempotency_key)] = deepcopy(result)

    def audit(self, event: dict) -> None:
        self.audits.append(deepcopy(event))

    def attachment_visible(self, *, actor: dict, attachment_gid: str) -> bool:
        return attachment_gid in actor.get("visible_attachment_gids", [])


@pytest.fixture
def service():
    from backend.base.self_annotations import SelfAnnotationService

    return SelfAnnotationService(repository=FakeAnnotationRepository())


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


def test_explicit_empty_deleted_change_is_a_recoverable_tombstone(service):
    service.apply_change(actor=OWNER, command=CHANGE)
    deleted = service.apply_change(actor=OWNER, command={
        "item_gid": "item_1", "expected_revision": 2, "status": "deleted",
        "schedule": None, "note": "", "attachments": [], "idempotency_key": "delete-1",
    })

    assert deleted["annotation"]["deleted"] is True
    assert deleted["annotation"]["restore"]["available"] is True
    assert service.search(actor=OWNER, query={}) == {"items": []}

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy

import pytest


VALID_CONFIG = {
    "field_gids": ["field_1"],
    "sort": [{"field_gid": "field_1", "direction": "asc"}],
    "filters": [{"field_gid": "field_1", "operator": "eq", "value": "open"}],
    "page_size": 50,
    "presentation": "table",
}
CREATE = {"name": "Open", "config": VALID_CONFIG, "share_scope": "private", "idempotency_key": "idem-1"}
UPDATE = {"expected_revision": 1, "name": "Open items", "config": VALID_CONFIG, "idempotency_key": "idem-2"}
COPY = {"name": "Copy", "idempotency_key": "idem-3"}
DELETE = {"expected_revision": 2, "idempotency_key": "idem-4"}


class FakeTransactionRepository:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}
        self.replays: dict[tuple[str, str, str], dict] = {}
        self.audits: list[dict] = []
        self.transactions = 0
        self.locked: list[str] = []
        self._next = 1

    @contextmanager
    def transaction(self):
        self.transactions += 1
        yield self

    def next_gid(self) -> str:
        value = f"view_{self._next}"
        self._next += 1
        return value

    def get(self, view_gid: str, *, lock: bool = False) -> dict | None:
        if lock:
            self.locked.append(view_gid)
        row = self.rows.get(view_gid)
        return deepcopy(row) if row else None

    def list(self) -> list[dict]:
        return [deepcopy(row) for row in self.rows.values()]

    def save(self, row: dict) -> None:
        self.rows[row["gid"]] = deepcopy(row)

    def replay(self, *, actor_gid: str, operation: str, idempotency_key: str) -> dict | None:
        result = self.replays.get((actor_gid, operation, idempotency_key))
        return deepcopy(result) if result else None

    def remember(self, *, actor_gid: str, operation: str, idempotency_key: str, result: dict, record_gid: str) -> None:
        self.replays[(actor_gid, operation, idempotency_key)] = deepcopy(result)

    def audit(self, event: dict) -> None:
        self.audits.append(deepcopy(event))


@pytest.fixture
def service():
    from backend.base.saved_views import SavedViewService

    return SavedViewService(repository=FakeTransactionRepository())


OWNER = {"gid": "user_owner", "team_gids": ["team_1"]}
TEAM_MEMBER = {"gid": "user_team", "team_gids": ["team_1"]}
OUTSIDER = {"gid": "user_other", "team_gids": ["team_2"]}


def test_create_replays_first_result_and_audits_in_one_transaction(service):
    first = service.create(actor=OWNER, command=CREATE)
    replay = service.create(actor=OWNER, command=CREATE)

    assert replay == first
    assert first["view"]["revision"] == 1
    assert service.repository.transactions == 2
    assert len(service.repository.audits) == 1


def test_search_enforces_owner_team_and_shared_visibility(service):
    private = service.create(actor=OWNER, command=CREATE)["view"]
    team = service.create(actor=OWNER, command={**CREATE, "share_scope": "team", "idempotency_key": "idem-team"})["view"]
    shared = service.create(actor=OWNER, command={**CREATE, "share_scope": "shared", "idempotency_key": "idem-shared"})["view"]

    assert {item["gid"] for item in service.search(actor=OWNER, query={})["views"]} == {private["gid"], team["gid"], shared["gid"]}
    assert {item["gid"] for item in service.search(actor=TEAM_MEMBER, query={})["views"]} == {team["gid"], shared["gid"]}
    assert {item["gid"] for item in service.search(actor=OUTSIDER, query={})["views"]} == {shared["gid"]}


def test_copy_changes_owner_and_resets_grants(service):
    source = service.create(actor=OWNER, command={**CREATE, "share_scope": "shared"})["view"]
    service.repository.rows[source["gid"]]["grants"] = ["team_1"]

    copied = service.copy(actor=TEAM_MEMBER, view_gid=source["gid"], command=COPY)["view"]

    assert copied["owner_gid"] == TEAM_MEMBER["gid"]
    assert copied["gid"] != source["gid"]
    assert copied["grants"] == []
    assert copied["share_scope"] == "private"


def test_update_rejects_stale_revision_and_locks_aggregate(service):
    created = service.create(actor=OWNER, command=CREATE)["view"]

    with pytest.raises(Exception) as caught:
        service.update(actor=OWNER, view_gid=created["gid"], command={**UPDATE, "expected_revision": 2})

    assert caught.value.code == "revision_conflict"
    updated = service.update(actor=OWNER, view_gid=created["gid"], command=UPDATE)
    assert updated["view"]["revision"] == 2
    assert created["gid"] in service.repository.locked


def test_delete_is_a_recoverable_tombstone_with_restore_metadata(service):
    created = service.create(actor=OWNER, command=CREATE)["view"]
    service.update(actor=OWNER, view_gid=created["gid"], command=UPDATE)

    deleted = service.delete(actor=OWNER, view_gid=created["gid"], command=DELETE)

    assert deleted["view"]["deleted"] is True
    assert deleted["view"]["restore"]["available"] is True
    assert deleted["view"]["restore"]["deleted_by"] == OWNER["gid"]
    assert service.search(actor=OWNER, query={}) == {"views": []}


def test_persistence_envelope_preserves_idempotency_and_audit_evidence():
    from backend.base.saved_views import _decode_row, _stored

    stored = _stored({
        "config": VALID_CONFIG, "revision": 1, "deleted": False, "share_scope": "private", "grants": [],
        "team_gids": [], "restore": None, "_replays": {"user:create:idem": {"view": {"gid": "view_1"}}},
        "_audit": [{"operation": "create"}],
    })
    restored = _decode_row({"gid": "view_1", "name": "Open", "module": "", "list_gid": None, "owner_gid": "user", "is_shared": False, "config": stored})

    assert restored["_replays"] == {"user:create:idem": {"view": {"gid": "view_1"}}}
    assert restored["_audit"] == [{"operation": "create"}]


@pytest.mark.parametrize(
    "config",
    [
        {**VALID_CONFIG, "unknown": True},
        {**VALID_CONFIG, "sort": [{"field_gid": "field_1", "direction": "sideways"}]},
        {**VALID_CONFIG, "filters": [{"field_gid": "field_1", "operator": "sql", "value": "open"}]},
        {**VALID_CONFIG, "presentation": "chart"},
        {**VALID_CONFIG, "page_size": 0},
        {**VALID_CONFIG, "page_size": 201},
    ],
)
def test_create_rejects_invalid_closed_config(service, config):
    with pytest.raises(Exception) as caught:
        service.create(actor=OWNER, command={**CREATE, "config": config})

    assert caught.value.code == "invalid_input"


@pytest.mark.parametrize(
    "method,kwargs",
    [
        ("search", {"query": {"unknown": True}}),
        ("create", {"command": {**CREATE, "unknown": True}}),
        ("update", {"view_gid": "view_1", "command": {**UPDATE, "unknown": True}}),
        ("copy", {"view_gid": "view_1", "command": {**COPY, "unknown": True}}),
        ("delete", {"view_gid": "view_1", "command": {**DELETE, "unknown": True}}),
    ],
)
def test_commands_reject_unknown_keys(service, method, kwargs):
    with pytest.raises(Exception) as caught:
        getattr(service, method)(actor=OWNER, **kwargs)

    assert caught.value.code == "invalid_input"

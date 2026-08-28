from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from threading import Barrier, Lock, Thread

import pytest


VALID_CONFIG = {
    "columns": [{"key": "field_1", "visible": True, "order": 0, "width": 120}],
    "filters": [{"id": "filter_1", "field": "field_1", "op": "eq", "value": "open"}],
    "filterMode": "and",
    "sorts": [{"field": "field_1", "dir": "asc"}],
    "groupBy": None,
    "viewType": "grid",
    "treeParentField": None,
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

    def claim(self, *, actor_gid: str, operation: str, idempotency_key: str) -> dict | None:
        return self.replay(actor_gid=actor_gid, operation=operation, idempotency_key=idempotency_key)

    def complete(self, *, actor_gid: str, operation: str, idempotency_key: str, result: dict, record_gid: str) -> None:
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


def test_concurrent_duplicate_create_serializes_on_unique_replay_claim():
    class ConcurrentRepository(FakeTransactionRepository):
        def __init__(self):
            super().__init__()
            self._transaction_lock = Lock()

        @contextmanager
        def transaction(self):
            with self._transaction_lock:
                yield self

    service = __import__("backend.base.saved_views", fromlist=["SavedViewService"]).SavedViewService(
        repository=ConcurrentRepository(),
    )
    barrier = Barrier(3)
    results = []

    def create():
        barrier.wait()
        results.append(service.create(actor=OWNER, command=CREATE))

    threads = [Thread(target=create), Thread(target=create)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    assert results[0] == results[1]
    assert len(service.repository.rows) == 1
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


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_concurrent_duplicate_existing_view_write_replays_before_revision_conflict(operation):
    class ConcurrentRepository(FakeTransactionRepository):
        def __init__(self):
            super().__init__()
            self._transaction_lock = Lock()

        @contextmanager
        def transaction(self):
            with self._transaction_lock:
                yield self

    service = __import__("backend.base.saved_views", fromlist=["SavedViewService"]).SavedViewService(
        repository=ConcurrentRepository(),
    )
    view = service.create(actor=OWNER, command=CREATE)["view"]
    command = (
        {**UPDATE, "idempotency_key": f"idem-{operation}"}
        if operation == "update"
        else {"expected_revision": 1, "idempotency_key": f"idem-{operation}"}
    )
    barrier = Barrier(3)
    results = []

    def write():
        barrier.wait()
        results.append(getattr(service, operation)(
            actor=OWNER, view_gid=view["gid"], command=command,
        ))

    threads = [Thread(target=write), Thread(target=write)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    assert results[0] == results[1]
    assert results[0]["view"]["revision"] == 2
    assert len(service.repository.audits) == 2


def test_delete_is_a_recoverable_tombstone_with_restore_metadata(service):
    created = service.create(actor=OWNER, command=CREATE)["view"]
    service.update(actor=OWNER, view_gid=created["gid"], command=UPDATE)

    deleted = service.delete(actor=OWNER, view_gid=created["gid"], command=DELETE)

    assert deleted["view"]["deleted"] is True
    assert deleted["view"]["restore"]["available"] is True
    assert deleted["view"]["restore"]["deleted_by"] == OWNER["gid"]
    assert service.search(actor=OWNER, query={}) == {"views": []}


def test_legacy_config_is_strictly_normalized_without_metadata_collision():
    from backend.base.saved_views import _decode_row

    safe = _decode_row({"gid": "view_1", "name": "Open", "module": "", "list_gid": None,
                        "owner_gid": "user", "is_shared": False, "config": deepcopy(VALID_CONFIG)})
    unsafe = _decode_row({"gid": "view_2", "name": "Collision", "module": "", "list_gid": None,
                          "owner_gid": "user", "is_shared": False,
                          "config": {"_saved_view": {"config": VALID_CONFIG}}})

    assert safe["config"] == VALID_CONFIG
    assert safe["_legacy_status"] == "migration_needed"
    assert unsafe["_legacy_status"] == "legacy_config_unsupported"
    assert "config" not in unsafe


def test_search_omits_unsafe_legacy_rows_with_auditable_status(service):
    service.repository.rows["legacy"] = {
        "gid": "legacy", "name": "Unsafe", "module": "task", "list_gid": None, "owner_gid": OWNER["gid"],
        "revision": 1, "deleted": False, "share_scope": "private", "grants": [], "restore": None,
        "_legacy_status": "legacy_config_unsupported",
    }

    assert service.search(actor=OWNER, query={"module": "task"}) == {"views": []}
    assert service.repository.audits[-1]["status"] == "legacy_config_unsupported"


def test_copy_rejects_unsafe_legacy_config_without_overwrite(service):
    row = {
        "gid": "legacy", "name": "Unsafe", "module": "task", "list_gid": None, "owner_gid": OWNER["gid"],
        "revision": 1, "deleted": False, "share_scope": "shared", "grants": [], "restore": None,
        "_legacy_status": "legacy_config_unsupported",
    }
    service.repository.rows["legacy"] = deepcopy(row)

    with pytest.raises(Exception) as caught:
        service.copy(actor=OWNER, view_gid="legacy", command=COPY)

    assert caught.value.code == "legacy_config_unsupported"
    assert service.repository.rows["legacy"] == row


def test_scope_search_preserves_global_and_list_semantics(service):
    global_view = service.create(actor=OWNER, command={**CREATE, "module": "task", "idempotency_key": "global"})["view"]
    list_view = service.create(actor=OWNER, command={**CREATE, "module": "task", "list_gid": "list_1", "idempotency_key": "list-1"})["view"]
    service.create(actor=OWNER, command={**CREATE, "module": "task", "list_gid": "list_2", "idempotency_key": "list-2"})

    assert {row["gid"] for row in service.search(actor=OWNER, query={"module": "task"})["views"]} == {global_view["gid"]}
    assert {row["gid"] for row in service.search(actor=OWNER, query={"module": "task", "list_gid": "list_1"})["views"]} == {
        global_view["gid"], list_view["gid"],
    }


@pytest.mark.parametrize(
    "config",
    [
        {**VALID_CONFIG, "unknown": True},
        {**VALID_CONFIG, "columns": [{"key": "field_1", "visible": True, "order": -1, "width": 120}]},
        {**VALID_CONFIG, "columns": [{"key": "field_1", "visible": True, "order": 0, "width": 39}]},
        {**VALID_CONFIG, "columns": [{"key": "field_1", "visible": True, "order": 0, "width": 2001}]},
        {**VALID_CONFIG, "sorts": [{"field": "field_1", "dir": "sideways"}]},
        {**VALID_CONFIG, "filters": [{"id": "f", "field": "field_1", "op": "sql", "value": "open"}]},
        {**VALID_CONFIG, "filters": [{"id": "f", "field": "field_1", "op": "eq", "value": {"unsafe": True}}]},
        {**VALID_CONFIG, "filters": [{"id": "f", "field": "field_1", "op": "eq", "value": [["nested"]]}]},
        {**VALID_CONFIG, "filters": [{"id": "f", "field": "field_1", "op": "eq", "value": float("inf")}]},
        {**VALID_CONFIG, "filterMode": "xor"},
        {**VALID_CONFIG, "viewType": "gantt"},
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

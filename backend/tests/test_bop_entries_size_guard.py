from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi import HTTPException, Response

from plugins.craft.craft_backend.routers._bop import entries
from plugins.craft.craft_backend.routers._bop import _helpers


class _Cursor:
    def __init__(self, entry_count: int):
        self.entry_count = entry_count
        self.executed: list[tuple[object, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return {"entry_count": self.entry_count}

    def fetchall(self):
        return []


class _Connection:
    def __init__(self, cursor: _Cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self._cursor


def _get_conn(cursor: _Cursor):
    @contextmanager
    def factory():
        yield _Connection(cursor)

    return factory


def test_small_legacy_collection_runs_wide_query_and_marks_response_deprecated(monkeypatch):
    """Catches a guard that rejects the configured upper boundary or drops deprecation."""
    cursor = _Cursor(entry_count=25)
    monkeypatch.setattr(entries, "get_conn", _get_conn(cursor))
    monkeypatch.setattr(entries, "_LEGACY_ENTRIES_MAX", 25)
    response = Response()

    result = entries.list_entries("version-1", response=response, _u={})

    assert result == {"data": []}
    assert response.headers["Deprecation"] == "true"
    assert cursor.executed[0][1] == ("version-1",)
    assert cursor.executed[1] == (entries._ENTRY_LIST_SQL, ("version-1", "version-1"))


def test_large_legacy_collection_is_rejected_before_wide_query(monkeypatch):
    """Catches regression to materializing the wide entry query before size rejection."""
    cursor = _Cursor(entry_count=26)
    monkeypatch.setattr(entries, "get_conn", _get_conn(cursor))
    monkeypatch.setattr(entries, "_LEGACY_ENTRIES_MAX", 25)

    with pytest.raises(HTTPException) as raised:
        entries.list_entries("version-2", response=Response(), _u={})

    assert raised.value.status_code == 409
    assert raised.value.detail == {
        "code": "dataset_too_large_use_paged_capability",
        "details": {
            "entry_count": 26,
            "configured_limit": 25,
            "replacement_capabilities": [
                "craft.bop.structure.outline.get@1",
                "craft.bop.work_package.get@2",
                "craft.bop.entry.detail.get@1",
            ],
        },
    }
    assert len(cursor.executed) == 1
    assert cursor.executed[0][1] == ("version-2",)


def test_unset_legacy_limit_uses_conservative_default():
    """Catches an unset deployment accidentally restoring an unbounded collection."""
    assert _helpers.legacy_entries_max_from_env({}) == 2_000


@pytest.mark.parametrize("value", ["", "0", "-1", "1.5", "many"])
def test_invalid_legacy_limit_fails_configuration_validation(value):
    """Catches malformed startup configuration being ignored or coerced."""
    with pytest.raises(RuntimeError, match="AI00_CRAFT_LEGACY_ENTRIES_MAX"):
        _helpers.legacy_entries_max_from_env({"AI00_CRAFT_LEGACY_ENTRIES_MAX": value})


def test_legacy_usage_counter_aggregates_without_request_payload(monkeypatch):
    """Catches loss of the aggregate migration signal or accidental high-cardinality labels."""
    monkeypatch.setattr(entries, "_LEGACY_ENTRIES_USAGE", {"served": 0, "rejected": 0})
    small = _Cursor(entry_count=1)
    monkeypatch.setattr(entries, "get_conn", _get_conn(small))
    monkeypatch.setattr(entries, "_LEGACY_ENTRIES_MAX", 2)
    entries.list_entries("secret-version-a", response=Response(), _u={})

    large = _Cursor(entry_count=3)
    monkeypatch.setattr(entries, "get_conn", _get_conn(large))
    with pytest.raises(HTTPException):
        entries.list_entries("secret-version-b", response=Response(), _u={})

    assert entries.legacy_entries_usage_snapshot() == {"served": 1, "rejected": 1}

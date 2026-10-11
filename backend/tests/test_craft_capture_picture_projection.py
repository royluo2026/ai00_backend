import json
from contextlib import contextmanager
from urllib.parse import unquote

from backend.capability_v2.provider_contracts import CapabilityContext
from plugins.craft.craft_backend.capabilities import bop_line_operation_catia, process_screenshot
from plugins.craft.craft_backend.routers._bop.entries import _normalize_bop_pic_items
from plugins.craft.craft_backend.services.bop_picture_refs import normalize_bop_pictures


ARTIFACT = {
    "artifact_id": "artifact_" + "1" * 32, "media_type": "image/png",
    "sha256": "a" * 64, "byte_size": 2048, "version": 1,
}


def reference(picture):
    return json.loads(unquote(picture["url"][9:].split("/", 1)[0]))


def test_old_screenshot_rows_and_legacy_pictures_survive_read_and_save():
    pictures = [{"screenshot_gid": "shot", "artifact_ref": ARTIFACT}, "legacy.png"]
    normalized = _normalize_bop_pic_items(json.dumps(pictures))
    assert reference(normalized[0]) == ARTIFACT
    assert normalized[1]["url"] == "legacy.png"
    assert _normalize_bop_pic_items(normalized) == normalized
    assert normalize_bop_pictures(json.dumps(normalized)) == normalized


class Cursor:
    def __init__(self, rows=(), one=()):
        self.rows = rows
        self.one = iter(one)
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, sql, params):
        self.calls.append((sql, params))

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return next(self.one)


class Connection:
    def __init__(self, cursor):
        self.current = cursor
        self.committed = False

    def cursor(self):
        return self.current

    def commit(self):
        self.committed = True

    def rollback(self):
        raise AssertionError("unexpected rollback")


def connection_factory(connection):
    @contextmanager
    def factory():
        yield connection
    return factory


def test_attach_writes_the_exact_process_and_version_with_a_renderable_reference(monkeypatch):
    cursor = Cursor(one=[{"gid": "version"}, {"gid": "process"}, None])
    connection = Connection(cursor)
    monkeypatch.setattr(process_screenshot, "get_craft_conn", connection_factory(connection))
    result = process_screenshot.ProcessScreenshotRepository().attach(
        bop_version_gid="version", operation_id="process", capture_run_id="run",
        artifact_ref=ARTIFACT, actor_gid="user",
    )
    update, params = cursor.calls[-1]
    assert "UPDATE workmanship_bop_bop_entries SET process_flow_pic=%s" in update
    assert params[1:] == ("process", "version")
    assert reference(json.loads(params[0])[0]) == ARTIFACT
    assert result["operation_id"] == "process"
    assert connection.committed


def test_line_picture_read_includes_processes_without_direct_part_links(monkeypatch):
    cursor = Cursor(rows=[{
        "bop_entry_gid": "process", "title": "Process", "node_type": "process",
        "parent_gid": "station", "sort_order": 10, "catia_names": "[null]",
        "process_flow_pic": json.dumps([{"artifact_ref": ARTIFACT}]),
    }])
    monkeypatch.setattr(bop_line_operation_catia, "get_craft_conn", connection_factory(Connection(cursor)))
    output = bop_line_operation_catia.read_bop_line_operation_catia(
        {"line_entry_gid": "line"}, CapabilityContext(user_gid="user", team_gid="team"),
    )
    row = output.data["data"][0]
    assert row["bop_entry_gid"] == "process"
    assert row["catia_names"] == []
    assert reference(row["process_flow_pic"][0]) == ARTIFACT
    sql, params = cursor.calls[0]
    assert "LEFT JOIN workmanship_bop_bop_entry_links" in sql
    assert "'process','bop_process','operation'" in sql
    assert "b.version_gid=d.version_gid" in sql
    assert params == ("line",)

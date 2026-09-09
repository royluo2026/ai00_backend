from craft_backend.capabilities import bop_active_line


class _Cursor:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql, _params):
        if "e.node_type='line_process'" in sql:
            self.rows = [{
                "gid": "line-1", "parent_gid": None, "node_type": "line_process",
                "title": "焊装线", "version_gid": "version-1", "version_tag": "V1",
            }]
        else:
            self.rows = [{"gid": f"node-{index}"} for index in range(5001)]

    def fetchall(self):
        return self.rows


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def cursor(self):
        return _Cursor()


def test_search_pages_line_nodes_without_scanning_the_whole_active_bop(monkeypatch) -> None:
    monkeypatch.setattr(bop_active_line, "get_craft_conn", lambda: _Connection())

    result = bop_active_line.search_active_lines(
        {"project_gid": "project-1", "page_size": 10}, None
    )

    assert result == {"data": {"items": [{
        "gid": "line-1", "version_gid": "version-1", "version_tag": "V1",
        "title": "焊装线", "path": "V1 / 焊装线",
    }], "next_cursor": None}}

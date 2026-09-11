from plugins.craft.craft_backend.data.bop_repository_mysql import MysqlBopRepositoryStore


class Cursor:
    def __init__(self):
        self.rows = []
        self.executed = []
        self.rowcount = 1

    def execute(self, sql, args=()):
        self.executed.append((sql, args))
        if "operation_ledger WHERE" in sql:
            self.rows = []
        elif "SELECT h.gid" in sql:
            self.rows = [] if "h.tenant_gid=%s" in sql else [{
                "gid": "20", "row_version": 1, "content_hash": "sha256:empty",
                "repository_gid": "30", "tenant_gid": "source-partition",
            }]
        elif "space_head_members WHERE" in sql:
            self.rows = []
        elif "FROM workmanship_craft_bop_space_versions WHERE" in sql:
            self.rows = [] if "tenant_gid=%s" in sql else [{
                "version_gid": "40", "space_gid": "10", "version_kind": "saved",
                "parent_version_gid": None, "manifest_hash": "sha256:manifest",
                "created_by": "50", "created_at": "2026-09-10",
            }]
        else:
            self.rows = []
        return self.rowcount

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def test_project_space_versions_are_readable_across_storage_partitions():
    cursor = Cursor()
    store = MysqlBopRepositoryStore(lambda: Connection(cursor))
    result = store.search_space_versions(
        space_gid="10", tenant_gid="current-partition", actor_gid="50", offset=0, page_size=10,
    )
    assert [item["version_gid"] for item in result["items"]] == ["40"]


def test_project_space_snapshot_keeps_the_source_storage_partition():
    cursor = Cursor()
    store = MysqlBopRepositoryStore(lambda: Connection(cursor))
    result = store.save_space_version(
        space_gid="10", tenant_gid="current-partition", actor_gid="50",
        expected_head_version=1, version_kind="saved", source_refs=[],
        algorithm_versions={}, idempotency_key="save-cross-partition",
    )
    version_insert = next(
        args for sql, args in cursor.executed
        if sql.startswith("INSERT INTO workmanship_craft_bop_space_versions")
    )
    assert result["space_gid"] == "10"
    assert version_insert[2] == "source-partition"

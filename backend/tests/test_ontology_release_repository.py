from pathlib import Path

import pytest

from backend.ontology.canonical import canonicalize_release
from backend.ontology.repository import OntologyReleaseRepository, StaleActiveRelease


def _concept(gid: str, name: str) -> dict:
    return {"kind": "concept", "stable_gid": gid, "name": name, "aliases": []}


def test_canonical_hash_ignores_input_order_and_dict_order():
    first = [_concept("c2", "工位"), _concept("c1", "线体")]
    second = [
        {"name": "线体", "stable_gid": "c1", "aliases": [], "kind": "concept"},
        {"aliases": [], "kind": "concept", "name": "工位", "stable_gid": "c2"},
    ]
    assert canonicalize_release(first) == canonicalize_release(second)


def test_canonical_release_rejects_duplicate_stable_identity():
    with pytest.raises(ValueError, match="duplicate"):
        canonicalize_release([_concept("c1", "A"), _concept("c1", "B")])


def test_migration_is_base_owned_oceanbase_mysql_and_defines_governance_tables():
    root = Path(__file__).resolve().parents[2]
    migration = root / "backend/db/migrations/202608060003_base_ontology_release_governance.sql"
    sql = migration.read_text(encoding="utf-8")
    for suffix in (
        "releases", "release_objects", "change_proposals",
        "proposal_revisions", "proposal_reviews", "active_refs",
    ):
        assert f"workmanship_base_ontology_{suffix}" in sql
    upper = sql.upper()
    assert "JSONB" not in upper
    assert "RETURNING" not in upper
    assert "CREATE SCHEMA" not in upper


class Cursor:
    def __init__(self, rows):
        self.rows = iter(rows)
        self.executed = []

    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def execute(self, sql, params=None): self.executed.append((sql, params))
    def fetchone(self): return next(self.rows, None)


class Connection:
    def __init__(self, rows):
        self.cursor_value = Cursor(rows)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self): return self.cursor_value
    def commit(self): self.commits += 1
    def rollback(self): self.rollbacks += 1


def test_active_ref_compare_and_swap_locks_and_rejects_stale_expected_release():
    conn = Connection([{"release_gid": "r2"}])
    repository = OntologyReleaseRepository(lambda: conn)
    with pytest.raises(StaleActiveRelease):
        repository.activate(
            ref_name="default", release_gid="r3", expected_release_gid="r1",
            release_sha256="a" * 64, actor_gid="u1",
        )
    sql = "\n".join(item[0] for item in conn.cursor_value.executed)
    assert "FOR UPDATE" in sql
    assert conn.commits == 0
    assert conn.rollbacks == 1


def test_active_ref_compare_and_swap_verifies_target_hash_before_commit():
    conn = Connection([
        {"release_gid": "r1", "release_sha256": "a" * 64},
        {"content_sha256": "b" * 64},
    ])
    repository = OntologyReleaseRepository(lambda: conn)
    result = repository.activate(
        ref_name="default", release_gid="r2", expected_release_gid="r1",
        release_sha256="b" * 64, actor_gid="u1",
    )
    assert result["release_gid"] == "r2"
    sql = "\n".join(item[0] for item in conn.cursor_value.executed)
    assert "UPDATE workmanship_base_ontology_active_refs" in sql
    assert conn.commits == 1
    assert conn.rollbacks == 0

def test_release_insert_is_append_only_and_stores_canonical_objects():
    conn = Connection([])
    repository = OntologyReleaseRepository(lambda: conn)
    result = repository.create_release(
        release_gid="r1", parent_release_gid=None, objects=[_concept("c1", "线体")],
        ois_object_key="ontology/releases/r1.json", actor_gid="u1", source="bootstrap",
    )
    sql = "\n".join(item[0] for item in conn.cursor_value.executed)
    assert "INSERT INTO workmanship_base_ontology_releases" in sql
    assert "INSERT INTO workmanship_base_ontology_release_objects" in sql
    assert "UPDATE workmanship_base_ontology_releases" not in sql
    assert result["object_count"] == 1
    assert len(result["content_sha256"]) == 64
    assert conn.commits == 1

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest

from plugins.ontology.ontology_backend.read_index import ReleaseReadIndex, ReadIndexCache
from plugins.ontology.ontology_backend.concepts import project_concept


OBJECTS = [
    {"kind": "concept", "stable_gid": "a", "name": "A", "description": "large text"},
    {"kind": "concept", "stable_gid": "b", "name": "B", "parent_gid": "a"},
    {"kind": "concept", "stable_gid": "c", "name": "C"},
    {"kind": "property", "stable_gid": "p", "name": "P", "class_gid": "a"},
    {"kind": "relation", "stable_gid": "r", "name": "R", "domain_class_gid": "c", "range_class_gid": "b"},
]


def test_index_preserves_inheritance_and_does_not_expose_mutable_storage():
    source = deepcopy(OBJECTS)
    index = ReleaseReadIndex(source)
    source[0]["name"] = "changed"
    item = index.get("concept", "b")
    assert project_concept(item, "schema", index.schema_objects("b")) == project_concept(item, "schema", OBJECTS)
    index.get("concept", "a")["name"] = "poison"
    assert index.get("concept", "a")["name"] == "A"


def test_neighbour_pages_include_reverse_relations_and_parent_names():
    index = ReleaseReadIndex(OBJECTS)
    rows, total = index.graph_page({"concept", "relation"}, limit=100, offset=0, around_gid="b")
    assert {row["stable_gid"] for row in rows} == {"a", "b", "c", "r"}
    assert total == 4
    assert "description" not in rows[0]
    page, total = index.graph_page({"concept", "relation"}, limit=1, offset=3, around_gid="b")
    assert len(page) == 1 and total == 4
    with pytest.raises(LookupError):
        index.graph_page({"concept"}, limit=100, offset=0, around_gid="missing")


def test_cache_coalesces_builds_isolates_keys_and_evicts():
    cache = ReadIndexCache(max_entries=2, max_bytes=100000)
    calls = []
    def build():
        calls.append(1)
        return ReleaseReadIndex(OBJECTS)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: cache.get(("test", "gid", "hash"), build), range(20)))
    assert len(calls) == 1 and all(result is results[0] for result in results)
    cache.get(("production", "gid", "hash"), build)
    cache.get(("test", "gid", "new-hash"), build)
    cache.get(("test", "gid", "hash"), build)
    assert len(calls) == 4


def test_cache_retries_failures_and_does_not_retain_oversize_indexes():
    cache = ReadIndexCache(max_entries=2, max_bytes=1)
    with pytest.raises(RuntimeError):
        cache.get("failed", lambda: (_ for _ in ()).throw(RuntimeError("unavailable")))
    first = cache.get("failed", lambda: ReleaseReadIndex(OBJECTS))
    second = cache.get("failed", lambda: ReleaseReadIndex(OBJECTS))
    assert first is not second


def test_cycle_and_missing_parent_preserve_projection():
    for parent in ("b", "missing"):
        objects = deepcopy(OBJECTS)
        objects[0]["parent_gid"] = parent
        index = ReleaseReadIndex(objects)
        assert project_concept(objects[1], "schema", index.schema_objects("b")) == project_concept(objects[1], "schema", objects)


def test_repository_cache_checks_hash_and_isolates_database_prefix_and_factory(monkeypatch):
    from plugins.ontology.ontology_backend import read_index
    from plugins.ontology.ontology_backend.repository import OntologyReleaseRepository, ReleaseIntegrityError
    from plugins.ontology.ontology_backend.canonical import canonicalize_release
    from backend.db import table_prefix
    monkeypatch.setattr(read_index, "READ_INDEX_CACHE", ReadIndexCache())
    prefix = ["test_"]
    monkeypatch.setattr(table_prefix, "current_table_prefix", lambda: prefix[0])
    calls = []
    class Repository(OntologyReleaseRepository):
        def list_objects(self, release_gid):
            calls.append(release_gid)
            return deepcopy(OBJECTS)
    factory = lambda: None
    repository = Repository(factory)
    release = {"release_gid": "release", "content_sha256": canonicalize_release(OBJECTS)[1], "object_count": len(OBJECTS)}
    first = repository.get_read_index(release)
    assert Repository(factory).get_read_index(release) is first and len(calls) == 1
    prefix[0] = "pp_"
    assert repository.get_read_index(release) is not first
    monkeypatch.setenv("AI00_ONTOLOGY_DB_URL", "different-database")
    repository.get_read_index(release)
    Repository(lambda: None).get_read_index(release)
    assert len(calls) == 4
    with pytest.raises(ReleaseIntegrityError):
        repository.get_read_index({**release, "content_sha256": "0" * 64})


def test_graph_domain_projection_preserves_existing_classification():
    objects = deepcopy(OBJECTS)
    objects[0]["domain"] = {"code": "craft"}
    rows, _ = ReleaseReadIndex(objects).graph_page({"concept"}, limit=1, offset=0)
    assert rows[0]["domain_code"] == "craft"


def test_graph_search_keeps_alias_support():
    index = ReleaseReadIndex([{"kind": "concept", "stable_gid": "a", "name": "Canonical", "aliases": ["Alternate"]}])
    rows, total = index.graph_page({"concept"}, limit=100, offset=0, query="alternate")
    assert total == 1 and rows[0]["stable_gid"] == "a"

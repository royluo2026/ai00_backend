"""Bounded process-local indexes of immutable ontology releases."""
from __future__ import annotations

from collections import OrderedDict, defaultdict
from concurrent.futures import Future
from copy import deepcopy
import json
from threading import Lock


GRAPH_FIELDS = frozenset((
    "kind", "stable_gid", "name", "label_zh", "label_en", "external_id",
    "node_type_binding", "parent_gid", "domain_class_gid", "range_class_gid",
    "link_type_binding", "deprecated", "display_layer", "domain_code",
))


class ReleaseReadIndex:
    def __init__(self, objects):
        self._objects = {(row["kind"], str(row["stable_gid"])): deepcopy(row) for row in objects}
        self.estimated_bytes = len(json.dumps(objects, ensure_ascii=False).encode("utf-8")) * 4
        self._members = defaultdict(list)
        self._neighbours = defaultdict(set)
        self._relations = defaultdict(set)
        self._pages = defaultdict(list)
        for key, row in sorted(self._objects.items()):
            kind, gid = key
            self._pages[kind].append(key)
            if kind in {"property", "relation"}:
                owner = row.get("class_gid" if kind == "property" else "domain_class_gid")
                if owner:
                    self._members[str(owner)].append(key)
            if kind == "concept" and row.get("parent_gid"):
                parent = str(row["parent_gid"])
                self._neighbours[gid].add(parent)
                self._neighbours[parent].add(gid)
            if kind == "relation":
                source, target = row.get("domain_class_gid"), row.get("range_class_gid")
                if source and target:
                    source, target = str(source), str(target)
                    self._neighbours[source].add(target)
                    self._neighbours[target].add(source)
                    self._relations[source].add(key)
                    self._relations[target].add(key)

    def get(self, kind, gid):
        return deepcopy(self._objects.get((kind, str(gid))))

    def schema_objects(self, gid):
        keys, visited = [], set()
        while gid and gid not in visited:
            visited.add(gid)
            key = ("concept", gid)
            row = self._objects.get(key)
            if row is None:
                break
            keys.append(key)
            keys.extend(self._members.get(gid, ()))
            gid = str(row.get("parent_gid") or "")
        return [deepcopy(self._objects[key]) for key in keys]

    def graph_page(self, kinds, *, limit, offset, query=None, around_gid=None):
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("invalid page bounds")
        if around_gid:
            gid = str(around_gid)
            if ("concept", gid) not in self._objects:
                raise LookupError("ontology concept not found in the resolved release")
            keys = {( "concept", neighbour) for neighbour in self._neighbours.get(gid, ())}
            keys.add(("concept", gid))
            keys.update(self._relations.get(gid, ()))
            keys = sorted(key for key in keys if key in self._objects and key[0] in kinds)
        else:
            keys = [key for kind in sorted(kinds) for key in self._pages.get(kind, ())]
        if query:
            needle = query.casefold()
            def matches(key):
                row = self._objects[key]
                values = [row.get(field) for field in ("stable_gid", "name", "label_zh", "label_en", "external_id")]
                values.extend(row.get("aliases") or [])
                return any(needle in str(value or "").casefold() for value in values)
            keys = [key for key in keys if matches(key)]
        total = len(keys)
        rows = []
        for key in keys[offset:offset + limit]:
            source = self._objects[key]
            row = deepcopy({field: value for field, value in source.items() if field in GRAPH_FIELDS})
            if not row.get("domain_code"):
                domain = source.get("domain") or source.get("category")
                if isinstance(domain, dict):
                    domain = domain.get("code") or domain.get("name")
                if isinstance(domain, str):
                    row["domain_code"] = domain
            rows.append(row)
        return rows, total


class ReadIndexCache:
    def __init__(self, max_entries=4, max_bytes=64 * 1024 * 1024):
        self._max_entries, self._max_bytes = max_entries, max_bytes
        self._entries, self._pending = OrderedDict(), {}
        self._bytes = 0
        self._lock = Lock()

    def get(self, key, build):
        with self._lock:
            if key in self._entries:
                self._entries.move_to_end(key)
                return self._entries[key]
            future = self._pending.get(key)
            owner = future is None
            if owner:
                future = self._pending[key] = Future()
        if not owner:
            return future.result()
        try:
            index = build()
            with self._lock:
                if self._max_entries > 0 and index.estimated_bytes <= self._max_bytes:
                    self._entries[key] = index
                    self._bytes += index.estimated_bytes
                    while len(self._entries) > self._max_entries or self._bytes > self._max_bytes:
                        _, removed = self._entries.popitem(last=False)
                        self._bytes -= removed.estimated_bytes
                self._pending.pop(key)
                future.set_result(index)
            return index
        except BaseException as error:
            with self._lock:
                self._pending.pop(key, None)
                future.set_exception(error)
            raise


READ_INDEX_CACHE = ReadIndexCache()

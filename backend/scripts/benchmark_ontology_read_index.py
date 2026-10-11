"""Synthetic index benchmark; excludes network and real database latency."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
from time import perf_counter

from plugins.ontology.ontology_backend.canonical import canonicalize_release
from plugins.ontology.ontology_backend.concepts import project_concept
from plugins.ontology.ontology_backend.repository import OntologyReleaseRepository
from plugins.ontology.ontology_backend import read_index


def measure(count):
    objects = []
    for number in range(count):
        gid = str(1000000000000000000 + number)
        parent = str(1000000000000000000 + number // 10 * 10) if number % 10 else None
        objects.append({"kind": "concept", "stable_gid": gid, "name": f"Entity {number}",
                        "parent_gid": parent, "description": "Definition " * 50, "domain_code": "craft"})
        objects.append({"kind": "property", "stable_gid": "p" + gid, "class_gid": gid, "name": "Property"})
        objects.append({"kind": "relation", "stable_gid": "r" + gid, "name": "Related",
                        "domain_class_gid": gid, "range_class_gid": str(1000000000000000000 + (number + 1) % count)})
    release = {"release_gid": "benchmark-release", "content_sha256": canonicalize_release(objects)[1], "object_count": len(objects)}
    read_index.READ_INDEX_CACHE = read_index.ReadIndexCache()
    scans = []
    class Repository(OntologyReleaseRepository):
        def list_objects(self, release_gid):
            scans.append(release_gid)
            return objects
    repository = Repository(lambda: None)
    started = perf_counter()
    index = repository.get_read_index(release)
    cold_ms = (perf_counter() - started) * 1000
    timings = []
    for _ in range(100):
        started = perf_counter()
        warm = repository.get_read_index(release)
        gid = str(1000000000000000000 + count - 1)
        project_concept(warm.get("concept", gid), "schema", warm.schema_objects(gid))
        warm.graph_page({"concept", "relation"}, limit=100, offset=0, around_gid=gid)
        timings.append((perf_counter() - started) * 1000)
    rows, _ = index.graph_page({"concept"}, limit=100, offset=0)
    full = [row for row in objects if row["kind"] == "concept"][:100]
    return {"entities": count, "objects": len(objects), "cold_build_ms": round(cold_ms, 3),
            "warm_detail_and_neighbours_median_ms": round(median(timings), 3),
            "whole_release_reads_for_cold_and_100_warm_queries": len(scans),
            "estimated_index_bytes": index.estimated_bytes,
            "summary_100_items_bytes": len(json.dumps(rows).encode()),
            "full_100_concepts_bytes": len(json.dumps(full).encode())}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = {"scope": "Synthetic Python in-memory data; excludes DB, HTTP, gateway, rendering and reference envelopes.",
              "cache_budget": "4 releases / 64 MiB estimated retained size; cold index construction has additional transient memory.",
              "measurements": [measure(count) for count in (1000, 5000, 10000)]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))

#!/usr/bin/env python3
"""Bootstrap immutable shared ontology state from the legacy Craft editor tables."""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable, Mapping, Sequence

from backend.ontology.canonical import canonicalize_release
from backend.ontology.repository import OntologyReleaseRepository
from backend.platform_sdk.ids import next_gid

LEGACY_TABLES = {
    "concept": "workmanship_onto_classes",
    "property": "workmanship_onto_properties",
    "relation": "workmanship_onto_relations",
    "constraint": "workmanship_onto_axioms",
}


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    return value


def load_legacy_objects(conn: Any) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    with conn.cursor() as cursor:
        for kind, table in LEGACY_TABLES.items():
            cursor.execute(f"SELECT * FROM {table} ORDER BY gid")
            for row in cursor.fetchall():
                item = _json_safe(dict(row))
                stable_gid = str(item.get("gid") or item.get("id") or "").strip()
                if not stable_gid:
                    raise RuntimeError(f"legacy ontology row in {table} has no stable identity")
                item["kind"] = kind
                item["stable_gid"] = stable_gid
                objects.append(item)
    return objects


def bootstrap_ontology_release(
    *,
    repository: OntologyReleaseRepository,
    objects: Sequence[Mapping[str, Any]],
    actor_gid: str,
    dry_run: bool,
    snapshot_writer: Callable[..., dict[str, Any] | None],
    gid_factory: Callable[[], Any] = next_gid,
) -> dict[str, Any]:
    data, digest = canonicalize_release(objects)
    summary = {"object_count": len(objects), "content_sha256": digest}
    if dry_run:
        return {**summary, "dry_run": True}
    existing = repository.find_by_source("bootstrap", "legacy-editor")
    if existing:
        return {**existing, "existing": True, "dry_run": False}

    release_gid = str(gid_factory())
    object_key = f"ontology/releases/{release_gid}/release.{digest}.json"
    stored = snapshot_writer(object_key, data, "application/json; charset=utf-8")
    if not stored or stored.get("object_key") != object_key or stored.get("sha256") != digest:
        raise RuntimeError("ontology OIS snapshot verification failed")
    created = repository.create_release(
        release_gid=release_gid,
        parent_release_gid=None,
        objects=objects,
        ois_object_key=object_key,
        actor_gid=actor_gid,
        source="bootstrap",
        source_gid="legacy-editor",
    )
    if created["content_sha256"] != digest or int(created["object_count"]) != len(objects):
        raise RuntimeError("ontology release metadata verification failed")
    active = repository.get_active("default")
    if active is None:
        repository.activate(
            ref_name="default", release_gid=release_gid, expected_release_gid=None,
            release_sha256=digest, actor_gid=actor_gid,
        )
    return {**created, "existing": False, "dry_run": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actor-gid", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    from plugins.ontology.ontology_backend.infrastructure.storage import put_immutable
    from plugins.ontology.ontology_backend.infrastructure.connection import get_ontology_conn
    with get_ontology_conn() as source_conn:
        objects = load_legacy_objects(source_conn)
    result = bootstrap_ontology_release(
        repository=OntologyReleaseRepository(), objects=objects, actor_gid=args.actor_gid,
        dry_run=args.dry_run, snapshot_writer=put_immutable,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

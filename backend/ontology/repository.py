"""Append-only repository for governed ontology releases."""
from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Callable, Iterator, Mapping, Sequence

from .canonical import canonical_json_bytes, canonicalize_release, normalize_release_objects

if TYPE_CHECKING:
    from backend.capability_v2.revision.models import CommitRef


class StaleActiveRelease(RuntimeError):
    pass


class ReleaseIntegrityError(RuntimeError):
    pass


@contextmanager
def _open_connection(factory: Callable[[], Any]) -> Iterator[Any]:
    candidate = factory()
    if hasattr(candidate, "__enter__"):
        with candidate as conn:
            yield conn
    else:
        yield candidate


class OntologyReleaseRepository:
    def __init__(self, connection_factory: Callable[[], Any] | None = None):
        if connection_factory is None:
            from plugins.ontology.ontology_backend.infrastructure.connection import get_ontology_conn
            connection_factory = get_ontology_conn
        self._connection_factory = connection_factory

    def create_release(
        self,
        *,
        release_gid: str,
        parent_release_gid: str | None,
        objects: Sequence[Mapping[str, Any]],
        ois_object_key: str,
        actor_gid: str,
        source: str,
        source_gid: str | None = None,
    ) -> dict[str, Any]:
        normalized = normalize_release_objects(objects)
        _data, digest = canonicalize_release(normalized)
        if not release_gid or not actor_gid or not ois_object_key:
            raise ValueError("release_gid, actor_gid and ois_object_key are required")
        with _open_connection(self._connection_factory) as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO workmanship_base_ontology_releases "
                        "(gid,parent_release_gid,source,source_gid,content_sha256,object_count,ois_object_key,created_by) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (release_gid, parent_release_gid, source, source_gid, digest, len(normalized), ois_object_key, actor_gid),
                    )
                    for item in normalized:
                        object_data = canonical_json_bytes(item)
                        cursor.execute(
                            "INSERT INTO workmanship_base_ontology_release_objects "
                            "(release_gid,object_kind,stable_object_gid,object_sha256,object_json) "
                            "VALUES (%s,%s,%s,%s,%s)",
                            (
                                release_gid, item["kind"], item["stable_gid"],
                                hashlib.sha256(object_data).hexdigest(), object_data.decode("utf-8").rstrip("\n"),
                            ),
                        )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return {
            "release_gid": release_gid,
            "parent_release_gid": parent_release_gid,
            "content_sha256": digest,
            "object_count": len(normalized),
            "ois_object_key": ois_object_key,
            "source": source,
            "source_gid": source_gid,
            "revision_commit_id": None,
        }

    def bind_revision(self, release_gid: str, content_sha256: str, revision_ref: CommitRef) -> None:
        if revision_ref.repository.owner_domain != "ontology":
            raise ValueError("ontology release requires an ontology-owned RevisionRef")
        with _open_connection(self._connection_factory) as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE workmanship_base_ontology_releases SET revision_commit_id=%s "
                        "WHERE gid=%s AND content_sha256=%s "
                        "AND (revision_commit_id IS NULL OR revision_commit_id=%s)",
                        (revision_ref.commit_id, release_gid, content_sha256, revision_ref.commit_id),
                    )
                    if cursor.rowcount != 1:
                        cursor.execute(
                            "SELECT revision_commit_id,content_sha256 "
                            "FROM workmanship_base_ontology_releases WHERE gid=%s",
                            (release_gid,),
                        )
                        current = cursor.fetchone()
                        if (
                            not current
                            or str(current.get("revision_commit_id") or "") != revision_ref.commit_id
                            or str(current.get("content_sha256") or "") != content_sha256
                        ):
                            raise ReleaseIntegrityError("ontology release RevisionRef binding conflict")
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def find_by_source(self, source: str, source_gid: str | None = None) -> dict[str, Any] | None:
        with _open_connection(self._connection_factory) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT gid AS release_gid,parent_release_gid,content_sha256,object_count,ois_object_key,source,source_gid,revision_commit_id "
                    "FROM workmanship_base_ontology_releases WHERE source=%s AND source_gid <=> %s",
                    (source, source_gid),
                )
                row = cursor.fetchone()
        return dict(row) if row else None

    def get_active(self, ref_name: str = "default") -> dict[str, Any] | None:
        with _open_connection(self._connection_factory) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT ref_name,release_gid,release_sha256,updated_by,updated_at "
                    "FROM workmanship_base_ontology_active_refs WHERE ref_name=%s",
                    (ref_name,),
                )
                row = cursor.fetchone()
        return dict(row) if row else None

    def resolve_release(self, release_gid: str | None = None) -> dict[str, Any]:
        with _open_connection(self._connection_factory) as conn:
            with conn.cursor() as cursor:
                if release_gid:
                    cursor.execute(
                        "SELECT gid AS release_gid,parent_release_gid,content_sha256,object_count,ois_object_key,source,source_gid,revision_commit_id "
                        "FROM workmanship_base_ontology_releases WHERE gid=%s",
                        (release_gid,),
                    )
                else:
                    cursor.execute(
                        "SELECT r.gid AS release_gid,r.parent_release_gid,r.content_sha256,r.object_count,r.ois_object_key,r.source,r.source_gid,r.revision_commit_id "
                        "FROM workmanship_base_ontology_active_refs a "
                        "JOIN workmanship_base_ontology_releases r ON r.gid=a.release_gid WHERE a.ref_name='default'",
                    )
                row = cursor.fetchone()
        if not row:
            raise LookupError("ontology release not found or no active release is configured")
        return dict(row)

    def search_releases(self, limit: int = 50) -> list[dict[str, Any]]:
        with _open_connection(self._connection_factory) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT gid AS release_gid,parent_release_gid,content_sha256,object_count,ois_object_key,source,source_gid,revision_commit_id,created_by,created_at "
                    "FROM workmanship_base_ontology_releases ORDER BY created_at DESC LIMIT %s",
                    (max(1, min(limit, 100)),),
                )
                return [dict(row) for row in cursor.fetchall()]
    def list_objects(self, release_gid: str, kinds: set[str] | None = None) -> list[dict[str, Any]]:
        params: list[Any] = [release_gid]
        where = "release_gid=%s"
        if kinds:
            ordered = sorted(kinds)
            where += " AND object_kind IN (" + ",".join(["%s"] * len(ordered)) + ")"
            params.extend(ordered)
        with _open_connection(self._connection_factory) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT object_kind,stable_object_gid,object_sha256,object_json "
                    f"FROM workmanship_base_ontology_release_objects WHERE {where} "
                    "ORDER BY object_kind,stable_object_gid",
                    tuple(params),
                )
                rows = cursor.fetchall()
        result = []
        for row in rows:
            raw = row["object_json"]
            item = json.loads(raw) if isinstance(raw, str) else dict(raw)
            item.setdefault("kind", row["object_kind"])
            item.setdefault("stable_gid", row["stable_object_gid"])
            item["object_sha256"] = row["object_sha256"]
            result.append(item)
        return result

    def list_objects_page(
        self,
        release_gid: str,
        *,
        kinds: set[str] | None = None,
        limit: int = 100,
        offset: int = 0,
        query: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Read a deterministic, bounded page from an immutable release."""
        limit = max(1, min(int(limit), 100))
        offset = max(0, int(offset))
        params: list[Any] = [release_gid]
        where = ["release_gid=%s"]
        if kinds:
            ordered = sorted(kinds)
            where.append("object_kind IN (" + ",".join(["%s"] * len(ordered)) + ")")
            params.extend(ordered)
        if query:
            where.append("LOWER(object_json) LIKE %s")
            params.append(f"%{query.strip().lower()}%")
        clause = " AND ".join(where)
        with _open_connection(self._connection_factory) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT COUNT(*) AS total FROM workmanship_base_ontology_release_objects WHERE {clause}",
                    tuple(params),
                )
                total_row = cursor.fetchone() or {"total": 0}
                cursor.execute(
                    "SELECT object_kind,stable_object_gid,object_sha256,object_json "
                    f"FROM workmanship_base_ontology_release_objects WHERE {clause} "
                    "ORDER BY object_kind,stable_object_gid LIMIT %s OFFSET %s",
                    tuple(params + [limit, offset]),
                )
                rows = cursor.fetchall()
        result = []
        for row in rows:
            raw = row["object_json"]
            item = json.loads(raw) if isinstance(raw, str) else dict(raw)
            item.setdefault("kind", row["object_kind"])
            item.setdefault("stable_gid", row["stable_object_gid"])
            item["object_sha256"] = row["object_sha256"]
            result.append(item)
        return result, int(total_row.get("total") or 0)

    def get_object(self, release_gid: str, kind: str, stable_gid: str) -> dict[str, Any] | None:
        with _open_connection(self._connection_factory) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT object_kind,stable_object_gid,object_sha256,object_json "
                    "FROM workmanship_base_ontology_release_objects "
                    "WHERE release_gid=%s AND object_kind=%s AND stable_object_gid=%s",
                    (release_gid, kind, stable_gid),
                )
                row = cursor.fetchone()
        if not row:
            return None
        raw = row["object_json"]
        item = json.loads(raw) if isinstance(raw, str) else dict(raw)
        item.setdefault("kind", row["object_kind"])
        item.setdefault("stable_gid", row["stable_object_gid"])
        item["object_sha256"] = row["object_sha256"]
        return item

    def activate(
        self,
        *,
        ref_name: str,
        release_gid: str,
        expected_release_gid: str | None,
        release_sha256: str,
        actor_gid: str,
    ) -> dict[str, Any]:
        with _open_connection(self._connection_factory) as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT release_gid,release_sha256 FROM workmanship_base_ontology_active_refs "
                        "WHERE ref_name=%s FOR UPDATE",
                        (ref_name,),
                    )
                    current = cursor.fetchone()
                    current_gid = str(current["release_gid"]) if current else None
                    if current_gid != expected_release_gid:
                        raise StaleActiveRelease(
                            f"active ontology release changed: expected {expected_release_gid!r}, current {current_gid!r}"
                        )
                    cursor.execute(
                        "SELECT content_sha256 FROM workmanship_base_ontology_releases WHERE gid=%s",
                        (release_gid,),
                    )
                    target = cursor.fetchone()
                    if not target or str(target["content_sha256"]) != release_sha256:
                        raise ReleaseIntegrityError("target ontology release hash does not match immutable storage")
                    if current:
                        cursor.execute(
                            "UPDATE workmanship_base_ontology_active_refs SET release_gid=%s,release_sha256=%s,updated_by=%s,updated_at=NOW() "
                            "WHERE ref_name=%s",
                            (release_gid, release_sha256, actor_gid, ref_name),
                        )
                    else:
                        cursor.execute(
                            "INSERT INTO workmanship_base_ontology_active_refs "
                            "(ref_name,release_gid,release_sha256,updated_by) VALUES (%s,%s,%s,%s)",
                            (ref_name, release_gid, release_sha256, actor_gid),
                        )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return {"ref_name": ref_name, "release_gid": release_gid, "release_sha256": release_sha256}

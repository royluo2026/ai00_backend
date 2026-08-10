"""Insert-only persistence adapters for immutable Catalog Releases."""
from __future__ import annotations

import json
from typing import Callable

from .catalog import CatalogRelease


class InMemoryCatalogStore:
    """Test/development store; formal environments must use persistent storage."""

    def __init__(self) -> None:
        self._releases: dict[str, CatalogRelease] = {}

    def publish(self, release: CatalogRelease) -> None:
        if release.release_id in self._releases:
            raise ValueError("catalog_release_exists")
        self._releases[release.release_id] = release

    def get(self, release_id: str) -> CatalogRelease | None:
        return self._releases.get(release_id)


class SqlCatalogStore:
    """OceanBase repository exposing only INSERT and SELECT operations."""

    TABLE = "workmanship_base_capability_catalog_releases"

    def __init__(self, connection_factory: Callable):
        self._connection_factory = connection_factory

    def publish(self, release: CatalogRelease) -> None:
        conn = self._connection_factory()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"INSERT INTO {self.TABLE} "
                    "(release_id, catalog_hash, descriptors_json, provider_artifacts_json, created_at) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (
                        release.release_id,
                        release.catalog_hash,
                        json.dumps([item.model_dump(mode="json") for item in release.descriptors], ensure_ascii=False),
                        json.dumps([item.model_dump(mode="json") for item in release.provider_artifacts], ensure_ascii=False),
                        release.created_at,
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get(self, release_id: str) -> CatalogRelease | None:
        conn = self._connection_factory()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT release_id, catalog_hash, descriptors_json, provider_artifacts_json, created_at "
                    f"FROM {self.TABLE} WHERE release_id=%s",
                    (release_id,),
                )
                row = cursor.fetchone()
            if row is None:
                return None
            if not isinstance(row, dict):
                row = dict(zip(
                    ("release_id", "catalog_hash", "descriptors_json", "provider_artifacts_json", "created_at"),
                    row,
                ))
            return CatalogRelease.model_validate({
                "release_id": row["release_id"],
                "catalog_hash": row["catalog_hash"],
                "descriptors": _json_value(row["descriptors_json"]),
                "provider_artifacts": _json_value(row["provider_artifacts_json"]),
                "created_at": row["created_at"],
            })
        finally:
            conn.close()


def _json_value(value):
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    return json.loads(value) if isinstance(value, str) else value


__all__ = ["InMemoryCatalogStore", "SqlCatalogStore"]

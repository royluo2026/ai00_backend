"""Tenant-scoped Integration target bindings backed by the immutable Catalog."""
from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

from backend.capability_v2.catalog import CatalogResolutionError, CatalogResolver
from backend.capability_v2.catalog_lineage import CatalogLineage
from backend.capability_v2.contracts import CapabilityDescriptorV2, LifecycleStatus
from backend.capability_v2.schema_validation import validate_payload

from ..data.connection import get_integration_conn


_PUBLIC_FIELDS = (
    "binding_id", "ontology_object_gid", "target_domain", "target_capability_id",
    "target_major_version", "minimum_catalog_release", "input_contract",
    "resource_gid", "expected_version",
)
_TARGET_CONTRACTS = {
    "knowledge.reference_dataset.publish.v1": (
        "knowledge.reference_dataset.publish", 1,
    ),
}


class IntegrationTargetCatalog:
    """Resolve finite executable targets without reading another domain's tables."""

    def __init__(
        self,
        connection_factory: Callable[[], Any] = get_integration_conn,
        *,
        catalog_resolver: CatalogResolver,
        active_release_id: str,
        release_lineage: CatalogLineage,
    ) -> None:
        self._connection_factory = connection_factory
        self._catalog_resolver = catalog_resolver
        self._active_release_id = str(active_release_id)
        self._release_lineage = release_lineage

    @staticmethod
    def _scope(actor_gid: str, team_gid: str) -> tuple[str, str]:
        actor = str(actor_gid or "").strip()
        team = str(team_gid or "").strip()
        if not actor or not team:
            raise ValueError("authenticated_scope_required")
        return actor, team

    def project_mapping_targets_for_ontology_objects(
        self, ontology_object_gids: Iterable[str], *, actor_gid: str, team_gid: str,
    ) -> list[dict[str, Any]]:
        actor, team = self._scope(actor_gid, team_gid)
        gids = tuple(dict.fromkeys(str(value).strip() for value in ontology_object_gids if str(value).strip()))
        if not 1 <= len(gids) <= 200:
            raise ValueError("ontology_object_scope_invalid")
        placeholders = ",".join("%s" for _ in gids)
        sql = (
            "SELECT " + ",".join(_PUBLIC_FIELDS) + " "
            "FROM workmanship_int_mapping_target_bindings "
            f"WHERE ontology_object_gid IN ({placeholders}) AND active=1 "
            "AND owner_gid=%s AND team_gid=%s ORDER BY ontology_object_gid,binding_id"
        )
        rows = self._query(sql, (*gids, actor, team), many=True)
        return [self._validated(row) for row in rows]

    def resolve_mapping_target(
        self, binding_id: str, *, actor_gid: str, team_gid: str,
    ) -> dict[str, Any] | None:
        actor, team = self._scope(actor_gid, team_gid)
        binding = str(binding_id or "").strip()
        if not binding:
            return None
        sql = (
            "SELECT " + ",".join(_PUBLIC_FIELDS) + " "
            "FROM workmanship_int_mapping_target_bindings "
            "WHERE binding_id=%s AND active=1 AND owner_gid=%s AND team_gid=%s LIMIT 1"
        )
        row = self._query(sql, (binding, actor, team), many=False)
        if row is None:
            return None
        value = self._validated(row)
        value.pop("ontology_object_gid", None)
        return value

    def require_stable(
        self, capability_id: str, major_version: int, minimum_release: str,
    ) -> None:
        try:
            descriptor = self._catalog_resolver.descriptor(
                self._active_release_id, capability_id, major_version
            )
        except CatalogResolutionError as exc:
            raise ValueError("catalog_release_unavailable") from exc
        if (
            descriptor.lifecycle_status is not LifecycleStatus.STABLE
            or not capability_id.startswith(descriptor.owner_domain + ".")
        ):
            raise ValueError("target_capability_unavailable")
        self._release_lineage.require_floor(
            minimum_release_id=minimum_release,
            active_release_id=self._active_release_id,
            capability_id=capability_id,
            major_version=major_version,
            active_schema_hash=descriptor.schema_hash,
        )

    def _query(self, sql: str, params: tuple[Any, ...], *, many: bool):
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchall() if many else cursor.fetchone()

    def _validated(self, row: Mapping[str, Any]) -> dict[str, Any]:
        value = {field: row[field] for field in _PUBLIC_FIELDS}
        contract = _TARGET_CONTRACTS.get(str(value["input_contract"]))
        if contract != (
            str(value["target_capability_id"]), int(value["target_major_version"]),
        ):
            raise ValueError("target_binding_incompatible")
        self.require_stable(
            str(value["target_capability_id"]), int(value["target_major_version"]),
            str(value["minimum_catalog_release"]),
        )
        descriptor = self._catalog_resolver.descriptor(
            self._active_release_id,
            str(value["target_capability_id"]),
            int(value["target_major_version"]),
        )
        self._validate_contract(descriptor, value)
        value["target_major_version"] = int(value["target_major_version"])
        value["expected_version"] = int(value["expected_version"])
        return value

    @staticmethod
    def _validate_contract(
        descriptor: CapabilityDescriptorV2, binding: Mapping[str, Any]
    ) -> None:
        try:
            validate_payload(dict(descriptor.input_schema), {
                "dataset_gid": str(binding["resource_gid"]),
                "expected_version": int(binding["expected_version"]),
                "schema": {"fields": []},
                "rows": [],
            })
        except (TypeError, ValueError) as exc:
            raise ValueError("target_binding_incompatible") from exc


__all__ = ["IntegrationTargetCatalog"]

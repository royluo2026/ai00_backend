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

    def upsert_mapping_target(
        self, *, binding_id: str, ontology_object_gid: str, target_domain: str,
        target_capability_id: str, target_major_version: int, minimum_catalog_release: str,
        input_contract: str, resource_gid: str, target_expected_version: int,
        actor_gid: str, team_gid: str, expected_revision: int | None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        actor, team = self._scope(actor_gid, team_gid)
        candidate = {
            "binding_id": str(binding_id), "ontology_object_gid": str(ontology_object_gid),
            "target_domain": str(target_domain), "target_capability_id": str(target_capability_id),
            "target_major_version": int(target_major_version),
            "minimum_catalog_release": str(minimum_catalog_release),
            "input_contract": str(input_contract), "resource_gid": str(resource_gid),
            "expected_version": int(target_expected_version),
        }
        self._validated(candidate)
        key = str(idempotency_key or "").strip()
        if not key:
            raise ValueError("idempotency_key_required")
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT revision,last_idempotency_key FROM workmanship_int_mapping_target_bindings "
                    "WHERE binding_id=%s AND owner_gid=%s AND team_gid=%s FOR UPDATE",
                    (candidate["binding_id"], actor, team),
                )
                existing = cursor.fetchone()
                if existing and str(existing.get("last_idempotency_key") or "") == key:
                    revision = int(existing["revision"])
                elif existing:
                    if expected_revision is None or int(existing["revision"]) != int(expected_revision):
                        raise ValueError("target_binding_revision_conflict")
                    revision = int(existing["revision"]) + 1
                    cursor.execute(
                        "UPDATE workmanship_int_mapping_target_bindings SET ontology_object_gid=%s,"
                        "target_domain=%s,target_capability_id=%s,target_major_version=%s,"
                        "minimum_catalog_release=%s,input_contract=%s,resource_gid=%s,expected_version=%s,"
                        "active=1,revision=%s,last_idempotency_key=%s WHERE binding_id=%s AND owner_gid=%s AND team_gid=%s",
                        (
                            candidate["ontology_object_gid"], candidate["target_domain"], candidate["target_capability_id"],
                            candidate["target_major_version"], candidate["minimum_catalog_release"], candidate["input_contract"],
                            candidate["resource_gid"], candidate["expected_version"], revision, key,
                            candidate["binding_id"], actor, team,
                        ),
                    )
                else:
                    if expected_revision is not None:
                        raise ValueError("target_binding_revision_conflict")
                    revision = 1
                    cursor.execute(
                        "INSERT INTO workmanship_int_mapping_target_bindings "
                        "(binding_id,ontology_object_gid,target_domain,target_capability_id,target_major_version,"
                        "minimum_catalog_release,input_contract,resource_gid,expected_version,owner_gid,team_gid,"
                        "active,revision,last_idempotency_key) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,1,%s)",
                        (
                            candidate["binding_id"], candidate["ontology_object_gid"], candidate["target_domain"],
                            candidate["target_capability_id"], candidate["target_major_version"],
                            candidate["minimum_catalog_release"], candidate["input_contract"], candidate["resource_gid"],
                            candidate["expected_version"], actor, team, key,
                        ),
                    )
        return {
            key: candidate[key]
            for key in (
                "binding_id", "ontology_object_gid", "target_domain", "target_capability_id",
                "target_major_version", "minimum_catalog_release", "resource_gid", "expected_version",
            )
        } | {"revision": revision}

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

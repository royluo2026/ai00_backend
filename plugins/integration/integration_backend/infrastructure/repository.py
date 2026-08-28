"""Integration-owned persistence. No target-domain table is reachable here."""
from __future__ import annotations

import json
from datetime import UTC
from typing import Any, Mapping

from backend.platform_sdk.ids import next_gid

from ..application.operations import IntegrationOperation
from ..application.ports import ResourceNotFound, RevisionConflict
from ..data.connection import get_integration_conn


class IntegrationRepository:
    def create_connector(self, data: dict) -> dict:
        gid = str(next_gid())
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO workmanship_int_ext_datasources "
                    "(gid,name,connector_type,host,port,database_name,username,credential_ref,owner_gid,team_gid) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        gid, data["name"], data["connector_type"], data["host"], data["port"],
                        data["database_name"], data["username"], data["credential_ref"],
                        data["owner_gid"], data.get("team_gid"),
                    ),
                )
        return {**data, "gid": gid, "revision": 1, "status": "untested"}

    def get_connector(self, data: dict) -> dict | None:
        rows = self._search("workmanship_int_ext_datasources", {**data, "gid": data["gid"], "limit": 1})
        return rows[0] if rows else None

    def update_connector(self, data: dict) -> dict:
        fields = ("name", "connector_type", "host", "port", "database_name", "username", "credential_ref")
        assignments = [f"{field}=COALESCE(%s,{field})" for field in fields]
        values = [data.get(field) for field in fields]
        scope, scope_values = self._scope(data)
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE workmanship_int_ext_datasources SET {','.join(assignments)},revision=revision+1 "
                    f"WHERE gid=%s AND revision=%s AND {scope} AND archived_at IS NULL",
                    (*values, data["gid"], data["expected_revision"], *scope_values),
                )
                if cur.rowcount != 1:
                    self._raise_miss(cur, "workmanship_int_ext_datasources", data)
        updated = self.get_connector(data)
        if updated is None:
            raise ResourceNotFound("connector")
        return updated

    def archive_connector(self, data: dict) -> dict:
        return self._archive("workmanship_int_ext_datasources", data)

    def search_connectors(self, data: dict) -> list[dict]:
        return self._search("workmanship_int_ext_datasources", data)

    def create_mapping(self, data: dict) -> dict:
        gid = str(next_gid())
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO workmanship_int_ext_mappings "
                    "(gid,datasource_gid,name,source_object,target_domain,target_capability_id,target_major_version,"
                    "minimum_catalog_release,field_mappings_json,owner_gid,team_gid) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        gid, data["datasource_gid"], data["name"], data["source_object"],
                        data["target_domain"], data["target_capability_id"], data["target_major_version"],
                        data["minimum_catalog_release"], json.dumps(data.get("field_mappings", [])),
                        data["owner_gid"], data.get("team_gid"),
                    ),
                )
                for order, item in enumerate(data.get("field_mappings", ())):
                    cur.execute(
                        "INSERT INTO workmanship_int_ext_field_mappings "
                        "(gid,mapping_gid,revision,source_field,target_field,transform_expression,sort_order) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (
                            item.get("gid") or str(next_gid()), gid, 1, item["source_field"],
                            item["target_field"], item.get("transform_expression"), order,
                        ),
                    )
        return {**data, "gid": gid, "revision": 1, "status": "active"}

    def get_mapping(self, data: dict) -> dict | None:
        rows = self._search("workmanship_int_ext_mappings", {**data, "gid": data["gid"], "limit": 1})
        if not rows:
            return None
        row = rows[0]
        value = row.get("field_mappings_json") or []
        if isinstance(value, (bytes, bytearray)):
            value = value.decode("utf-8")
        row["field_mappings"] = json.loads(value) if isinstance(value, str) else list(value)
        return row

    def update_mapping(self, data: dict) -> dict:
        scope, scope_values = self._scope(data)
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE workmanship_int_ext_mappings SET field_mappings_json=COALESCE(%s,field_mappings_json),"
                    f"revision=revision+1 WHERE gid=%s AND revision=%s AND {scope} AND archived_at IS NULL",
                    (
                        json.dumps(data["field_mappings"]) if "field_mappings" in data else None,
                        data["gid"], data["expected_revision"], *scope_values,
                    ),
                )
                if cur.rowcount != 1:
                    self._raise_miss(cur, "workmanship_int_ext_mappings", data)
        return {"gid": data["gid"], "revision": data["expected_revision"] + 1, "changed": True}

    def archive_mapping(self, data: dict) -> dict:
        return self._archive("workmanship_int_ext_mappings", data)

    def search_mappings(self, data: dict) -> list[dict]:
        return self._search("workmanship_int_ext_mappings", data)

    def search_field_mappings(self, data: dict) -> list[dict] | None:
        if self.get_mapping({**data, "gid": data["mapping_gid"]}) is None:
            return None
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT gid,revision,source_field,target_field,transform_expression "
                    "FROM workmanship_int_ext_field_mappings WHERE mapping_gid=%s "
                    "ORDER BY sort_order LIMIT %s",
                    (data["mapping_gid"], min(int(data.get("limit", 100)), 200)),
                )
                return [dict(row) for row in cur.fetchall()]

    def replace_field_mappings(self, data: dict) -> dict:
        scope, scope_values = self._scope(data)
        revision = int(data["expected_revision"]) + 1
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE workmanship_int_ext_mappings SET field_mappings_json=%s,revision=revision+1 "
                    f"WHERE gid=%s AND revision=%s AND {scope} AND archived_at IS NULL",
                    (json.dumps(data["items"]), data["mapping_gid"], data["expected_revision"], *scope_values),
                )
                if cur.rowcount != 1:
                    self._raise_miss(cur, "workmanship_int_ext_mappings", {**data, "gid": data["mapping_gid"]})
                cur.execute(
                    "DELETE FROM workmanship_int_ext_field_mappings WHERE mapping_gid=%s",
                    (data["mapping_gid"],),
                )
                for order, item in enumerate(data["items"]):
                    cur.execute(
                        "INSERT INTO workmanship_int_ext_field_mappings "
                        "(gid,mapping_gid,revision,source_field,target_field,transform_expression,sort_order) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (
                            item["gid"], data["mapping_gid"], revision, item["source_field"],
                            item["target_field"], item.get("transform_expression"), order,
                        ),
                    )
        return {
            "mapping_gid": data["mapping_gid"],
            "revision": revision,
            "updated_count": len(data["items"]),
            "items": [dict(item, revision=revision) for item in data["items"]],
        }

    def create_import_run(self, data: dict) -> None:
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO workmanship_int_sync_runs "
                    "(run_id,mapping_gid,operation_id,status,target_capability_id,target_major_version,"
                    "catalog_release,owner_gid,team_gid,idempotency_key) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        data["run_id"], data["mapping_gid"], data["operation_id"], data["status"],
                        data["target_capability_id"], data["target_major_version"], data["catalog_release"],
                        data["owner_gid"], data.get("team_gid"), data["idempotency_key"],
                    ),
                )

    def find_operation(
        self, owner_gid: str, capability_id: str, idempotency_key: str
    ) -> IntegrationOperation | None:
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM workmanship_int_operations "
                    "WHERE owner_gid=%s AND capability_id=%s AND idempotency_key=%s",
                    (owner_gid, capability_id, idempotency_key),
                )
                row = cur.fetchone()
        return self._operation(row) if row else None

    def get_operation(self, operation_id: str) -> IntegrationOperation | None:
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM workmanship_int_operations WHERE operation_id=%s",
                    (operation_id,),
                )
                row = cur.fetchone()
        return self._operation(row) if row else None

    def create_operation(self, record: IntegrationOperation) -> IntegrationOperation:
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO workmanship_int_operations "
                    "(operation_id,owner_gid,team_gid,capability_id,idempotency_key,payload_hash,status,"
                    "operation_version,result_json,error_code,created_at,updated_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        record.operation_id, record.owner_gid, record.team_gid, record.capability_id,
                        record.idempotency_key, record.payload_hash, record.status, record.version,
                        json.dumps(record.result) if record.result is not None else None,
                        record.error_code, record.created_at, record.updated_at,
                    ),
                )
                self._audit(cur, record)
        return record

    def transition_operation(
        self, operation_id: str, expected_version: int, replacement: IntegrationOperation
    ) -> IntegrationOperation:
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE workmanship_int_operations SET status=%s,operation_version=%s,result_json=%s,"
                    "error_code=%s,updated_at=%s WHERE operation_id=%s AND operation_version=%s",
                    (
                        replacement.status, replacement.version,
                        json.dumps(replacement.result) if replacement.result is not None else None,
                        replacement.error_code, replacement.updated_at, operation_id, expected_version,
                    ),
                )
                if cur.rowcount != 1:
                    raise RevisionConflict("operation")
                self._audit(cur, replacement)
        return replacement

    @staticmethod
    def _audit(cur, record: IntegrationOperation) -> None:
        cur.execute(
            "INSERT INTO workmanship_int_audit_events "
            "(event_id,operation_id,owner_gid,team_gid,capability_id,status,operation_version,error_code,created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                str(next_gid()), record.operation_id, record.owner_gid, record.team_gid,
                record.capability_id, record.status, record.version, record.error_code, record.updated_at,
            ),
        )

    def _archive(self, table: str, data: dict) -> dict:
        scope, scope_values = self._scope(data)
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE {table} SET archived_at=NOW(6),revision=revision+1 "
                    f"WHERE gid=%s AND revision=%s AND {scope} AND archived_at IS NULL",
                    (data["gid"], data["expected_revision"], *scope_values),
                )
                if cur.rowcount != 1:
                    self._raise_miss(cur, table, data)
        return {"gid": data["gid"], "archived": True}

    def _search(self, table: str, data: dict) -> list[dict]:
        scope, params = self._scope(data)
        clauses = [scope, "archived_at IS NULL"]
        params = list(params)
        if data.get("gid"):
            clauses.append("gid=%s")
            params.append(data["gid"])
        if table == "workmanship_int_ext_mappings" and data.get("datasource_gid"):
            clauses.append("datasource_gid=%s")
            params.append(data["datasource_gid"])
        if data.get("query"):
            clauses.append("name LIKE %s")
            params.append(f"%{data['query']}%")
        limit = min(max(int(data.get("limit", 100)), 1), 200)
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT * FROM {table} WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC LIMIT %s",
                    (*params, limit),
                )
                return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def _scope(data: Mapping[str, Any]) -> tuple[str, tuple[Any, ...]]:
        if data.get("team_gid") is None:
            return "owner_gid=%s AND team_gid IS NULL", (data["owner_gid"],)
        return "owner_gid=%s AND team_gid=%s", (data["owner_gid"], data["team_gid"])

    @classmethod
    def _raise_miss(cls, cur, table: str, data: Mapping[str, Any]) -> None:
        scope, scope_values = cls._scope(data)
        cur.execute(
            f"SELECT revision FROM {table} WHERE gid=%s AND {scope} AND archived_at IS NULL",
            (data["gid"], *scope_values),
        )
        if cur.fetchone() is None:
            raise ResourceNotFound(data["gid"])
        raise RevisionConflict(data["gid"])

    @staticmethod
    def _operation(row: Mapping[str, Any]) -> IntegrationOperation:
        result = row.get("result_json")
        if isinstance(result, (bytes, bytearray)):
            result = result.decode("utf-8")
        if isinstance(result, str):
            result = json.loads(result)
        created_at, updated_at = row["created_at"], row["updated_at"]
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        return IntegrationOperation(
            operation_id=row["operation_id"], owner_gid=row["owner_gid"], team_gid=row.get("team_gid"),
            capability_id=row["capability_id"], idempotency_key=row["idempotency_key"],
            payload_hash=row["payload_hash"], status=row["status"], version=int(row["operation_version"]),
            result=result, error_code=row.get("error_code"), created_at=created_at, updated_at=updated_at,
        )


__all__ = ["IntegrationRepository"]

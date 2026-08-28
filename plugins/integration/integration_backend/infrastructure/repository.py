"""Integration-owned persistence. No target-domain table is reachable here."""
from __future__ import annotations

import json
from datetime import UTC
from typing import Any, Mapping

from backend.platform_sdk.ids import next_gid

from ..application.operations import IntegrationOperation
from ..application.ports import IncompleteOperation, ResourceNotFound, RevisionConflict
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
        gid = str(data.get("gid") or next_gid())
        field_mappings = [dict(item, revision=1) for item in data.get("field_mappings", ())]
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                self._insert_mapping(cur, {**data, "gid": gid, "field_mappings": field_mappings})
        return {**data, "gid": gid, "field_mappings": field_mappings, "revision": 1, "status": "active"}

    def execute_mapping_command(
        self, record: IntegrationOperation, completed: IntegrationOperation,
        command: str, data: Mapping[str, Any],
    ) -> tuple[IntegrationOperation, bool]:
        try:
            with get_integration_conn() as conn:
                with conn.cursor() as cur:
                    self._insert_operation(cur, record)
                    self._audit(cur, record)
                    if command == "create":
                        self._insert_mapping(cur, data)
                    elif command == "replace_fields":
                        self._replace_field_mappings(cur, data)
                    else:
                        raise ValueError(f"Unsupported Integration mapping command: {command}")
                    self._complete_operation(cur, record, completed)
                    self._audit(cur, completed)
        except Exception as exc:
            if not self._is_duplicate_key(exc):
                raise
            winner = self.find_operation(record.owner_gid, record.capability_id, record.idempotency_key)
            if winner is None:
                raise RuntimeError("Integration idempotency winner could not be reloaded") from exc
            return winner, True
        return completed, False

    @classmethod
    def _insert_mapping(cls, cur, data: Mapping[str, Any]) -> None:
        field_mappings = [dict(item, revision=1) for item in data.get("field_mappings", ())]
        cur.execute(
            "INSERT INTO workmanship_int_ext_mappings "
            "(gid,datasource_gid,name,source_object,target_domain,target_capability_id,target_major_version,"
            "minimum_catalog_release,target_binding_id,target_input_contract,target_resource_gid,"
            "target_expected_version,field_mappings_json,owner_gid,team_gid) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                data["gid"], data["datasource_gid"], data["name"], data["source_object"],
                data["target_domain"], data["target_capability_id"], data["target_major_version"],
                data["minimum_catalog_release"], data["target_binding_id"],
                data["target_input_contract"], data["target_resource_gid"],
                data["target_expected_version"], json.dumps(field_mappings),
                data["owner_gid"], data.get("team_gid"),
            ),
        )
        cls._insert_field_mappings(cur, str(data["gid"]), field_mappings, 1)

    @classmethod
    def _replace_field_mappings(cls, cur, data: Mapping[str, Any]) -> None:
        scope, scope_values = cls._scope(data)
        revision = int(data["expected_revision"]) + 1
        cur.execute(
            "UPDATE workmanship_int_ext_mappings SET field_mappings_json=%s,revision=revision+1 "
            f"WHERE gid=%s AND revision=%s AND {scope} AND archived_at IS NULL",
            (json.dumps(data["items"]), data["mapping_gid"], data["expected_revision"], *scope_values),
        )
        if cur.rowcount != 1:
            cls._raise_miss(cur, "workmanship_int_ext_mappings", {**data, "gid": data["mapping_gid"]})
        cur.execute(
            "DELETE FROM workmanship_int_ext_field_mappings WHERE mapping_gid=%s",
            (data["mapping_gid"],),
        )
        cls._insert_field_mappings(cur, str(data["mapping_gid"]), list(data["items"]), revision)

    @staticmethod
    def _complete_operation(cur, record: IntegrationOperation, completed: IntegrationOperation) -> None:
        cur.execute(
            "UPDATE workmanship_int_operations SET status=%s,operation_version=%s,result_json=%s,"
            "error_code=%s,updated_at=%s WHERE operation_id=%s AND operation_version=%s",
            (
                completed.status, completed.version, json.dumps(completed.result), completed.error_code,
                completed.updated_at, record.operation_id, record.version,
            ),
        )
        if cur.rowcount != 1:
            raise RevisionConflict("operation")

    def get_mapping(self, data: dict) -> dict | None:
        scope, scope_values = self._scope(data)
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM workmanship_int_ext_mappings "
                    f"WHERE gid=%s AND {scope} AND archived_at IS NULL LIMIT 1",
                    (data["gid"], *scope_values),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                result = dict(row)
                result["field_mappings"] = self._field_rows(cur, data["gid"], 200)
                return result

    def update_mapping(self, data: dict) -> dict:
        scope, scope_values = self._scope(data)
        revision = int(data["expected_revision"]) + 1
        items = [dict(item, revision=revision) for item in data.get("field_mappings", ())]
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE workmanship_int_ext_mappings SET field_mappings_json=%s,"
                    f"revision=revision+1 WHERE gid=%s AND revision=%s AND {scope} AND archived_at IS NULL",
                    (
                        json.dumps(items),
                        data["gid"], data["expected_revision"], *scope_values,
                    ),
                )
                if cur.rowcount != 1:
                    self._raise_miss(cur, "workmanship_int_ext_mappings", data)
                cur.execute(
                    "DELETE FROM workmanship_int_ext_field_mappings WHERE mapping_gid=%s",
                    (data["gid"],),
                )
                self._insert_field_mappings(cur, data["gid"], items, revision)
        return {"gid": data["gid"], "revision": revision, "changed": True}

    def archive_mapping(self, data: dict) -> dict:
        return self._archive("workmanship_int_ext_mappings", data)

    def search_mappings(self, data: dict) -> list[dict]:
        scope, scope_values = self._scope(data)
        clauses = [scope, "archived_at IS NULL", "datasource_gid=%s"]
        params = [*scope_values, data["datasource_gid"]]
        if data.get("query"):
            clauses.append("name LIKE %s")
            params.append(f"%{data['query']}%")
        limit = min(max(int(data.get("limit", 100)), 1), 200)
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT gid,revision,datasource_gid,name,source_object,target_domain,target_capability_id,"
                    "target_major_version,minimum_catalog_release,status "
                    f"FROM workmanship_int_ext_mappings WHERE {' AND '.join(clauses)} "
                    "ORDER BY updated_at DESC LIMIT %s",
                    (*params, limit),
                )
                return [dict(row) for row in cur.fetchall()]

    def search_field_mappings(self, data: dict) -> list[dict] | None:
        if data.get("team_gid") is None:
            scope, scope_values = "m.owner_gid=%s AND m.team_gid IS NULL", (data["owner_gid"],)
        else:
            scope, scope_values = "m.owner_gid=%s AND m.team_gid=%s", (data["owner_gid"], data["team_gid"])
        limit = min(max(int(data.get("limit", 100)), 1), 200)
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT f.gid,f.revision,f.source_field,f.target_field,f.transform_expression,"
                    "m.revision AS mapping_revision FROM workmanship_int_ext_mappings m "
                    "LEFT JOIN workmanship_int_ext_field_mappings f ON f.mapping_gid=m.gid "
                    f"WHERE m.gid=%s AND {scope} AND m.archived_at IS NULL "
                    "ORDER BY f.sort_order LIMIT %s",
                    (data["mapping_gid"], *scope_values, limit),
                )
                rows = [dict(row) for row in cur.fetchall()]
        if not rows:
            return None
        return [] if rows[0]["gid"] is None else rows

    def replace_field_mappings(self, data: dict) -> dict:
        revision = int(data["expected_revision"]) + 1
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                self._replace_field_mappings(cur, data)
        return {
            "mapping_gid": data["mapping_gid"],
            "revision": revision,
            "updated_count": len(data["items"]),
            "items": [dict(item, revision=revision) for item in data["items"]],
        }

    @staticmethod
    def _insert_field_mappings(cur, mapping_gid: str, items: list[dict], revision: int) -> None:
        for order, item in enumerate(items):
            cur.execute(
                "INSERT INTO workmanship_int_ext_field_mappings "
                "(gid,mapping_gid,revision,source_field,target_field,transform_expression,sort_order) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    item.get("gid") or str(next_gid()), mapping_gid, revision, item["source_field"],
                    item["target_field"], item.get("transform_expression"), order,
                ),
            )

    @staticmethod
    def _field_rows(cur, mapping_gid: str, limit: int) -> list[dict]:
        cur.execute(
            "SELECT gid,revision,source_field,target_field,transform_expression "
            "FROM workmanship_int_ext_field_mappings WHERE mapping_gid=%s "
            "ORDER BY sort_order LIMIT %s",
            (mapping_gid, min(max(int(limit), 1), 200)),
        )
        return [dict(row) for row in cur.fetchall()]

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

    def find_import_operation(
        self, owner_gid: str, capability_id: str, idempotency_key: str
    ) -> IntegrationOperation | None:
        winner = self.find_operation(owner_gid, capability_id, idempotency_key)
        if winner is None:
            return None
        persisted_run = self._find_import_run(winner.operation_id, winner.owner_gid, winner.team_gid)
        winner_run_id = str((winner.result or {}).get("run_id") or "")
        if persisted_run is None or str(persisted_run.get("run_id") or "") != winner_run_id:
            raise IncompleteOperation(winner.operation_id)
        return winner

    def get_operation(
        self, operation_id: str, owner_gid: str, team_gid: str | None
    ) -> IntegrationOperation | None:
        scope, scope_values = self._principal_scope(owner_gid, team_gid)
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT * FROM workmanship_int_operations WHERE operation_id=%s AND {scope}",
                    (operation_id, *scope_values),
                )
                row = cur.fetchone()
        return self._operation(row) if row else None

    def claim_operation(self, record: IntegrationOperation) -> tuple[IntegrationOperation, bool]:
        try:
            with get_integration_conn() as conn:
                with conn.cursor() as cur:
                    self._insert_operation(cur, record)
                    self._audit(cur, record)
        except Exception as exc:
            if not self._is_duplicate_key(exc):
                raise
            winner = self.find_operation(record.owner_gid, record.capability_id, record.idempotency_key)
            if winner is None:
                raise RuntimeError("Integration idempotency winner could not be reloaded") from exc
            return winner, True
        return record, False

    def claim_import_operation(
        self, record: IntegrationOperation, run: Mapping[str, Any]
    ) -> tuple[IntegrationOperation, bool]:
        try:
            with get_integration_conn() as conn:
                with conn.cursor() as cur:
                    self._insert_operation(cur, record)
                    self._audit(cur, record)
                    self._insert_import_run(cur, run)
        except Exception as exc:
            if not self._is_duplicate_key(exc):
                raise
            winner = self.find_operation(record.owner_gid, record.capability_id, record.idempotency_key)
            if winner is None:
                raise RuntimeError("Integration import idempotency winner could not be reloaded") from exc
            persisted_run = self._find_import_run(
                winner.operation_id, winner.owner_gid, winner.team_gid
            )
            winner_run_id = str((winner.result or {}).get("run_id") or "")
            if persisted_run is None or str(persisted_run.get("run_id") or "") != winner_run_id:
                raise IncompleteOperation(winner.operation_id) from exc
            return winner, True
        return record, False

    @staticmethod
    def _insert_operation(cur, record: IntegrationOperation) -> None:
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

    @staticmethod
    def _insert_import_run(cur, data: Mapping[str, Any]) -> None:
        cur.execute(
            "INSERT INTO workmanship_int_sync_runs "
            "(run_id,mapping_gid,operation_id,status,target_capability_id,target_major_version,"
            "catalog_release,target_invocation_json,owner_gid,team_gid,idempotency_key) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                data["run_id"], data["mapping_gid"], data["operation_id"], data["status"],
                data["target_capability_id"], data["target_major_version"], data["catalog_release"],
                json.dumps(data["target_invocation"]), data["owner_gid"], data.get("team_gid"),
                data["idempotency_key"],
            ),
        )

    def _find_import_run(
        self, operation_id: str, owner_gid: str, team_gid: str | None
    ) -> dict[str, Any] | None:
        scope, scope_values = self._principal_scope(owner_gid, team_gid)
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT run_id FROM workmanship_int_sync_runs WHERE operation_id=%s AND {scope}",
                    (operation_id, *scope_values),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def transition_operation(
        self, operation_id: str, expected_version: int, replacement: IntegrationOperation,
        owner_gid: str, team_gid: str | None,
    ) -> IntegrationOperation:
        scope, scope_values = self._principal_scope(owner_gid, team_gid)
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE workmanship_int_operations SET status=%s,operation_version=%s,result_json=%s,"
                    f"error_code=%s,updated_at=%s WHERE operation_id=%s AND operation_version=%s AND {scope}",
                    (
                        replacement.status, replacement.version,
                        json.dumps(replacement.result) if replacement.result is not None else None,
                        replacement.error_code, replacement.updated_at, operation_id, expected_version,
                        *scope_values,
                    ),
                )
                if cur.rowcount != 1:
                    raise RevisionConflict("operation")
                self._audit(cur, replacement)
        return replacement

    @staticmethod
    def _is_duplicate_key(exc: Exception) -> bool:
        return bool(exc.args and exc.args[0] == 1062) or "duplicate" in str(exc).casefold()

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
        return IntegrationRepository._principal_scope(data["owner_gid"], data.get("team_gid"))

    @staticmethod
    def _principal_scope(owner_gid: str, team_gid: str | None) -> tuple[str, tuple[Any, ...]]:
        if team_gid is None:
            return "owner_gid=%s AND team_gid IS NULL", (owner_gid,)
        return "owner_gid=%s AND team_gid=%s", (owner_gid, team_gid)

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

"""Persistence boundary for private, owner-scoped Simulation workspaces."""
from __future__ import annotations

import json
import hashlib
from typing import Any, Mapping

from backend.platform_sdk.ids import next_gid

from .connection import get_simulation_conn


class WorkspaceRepositoryError(RuntimeError):
    pass


def _gid(value: object, field: str) -> str:
    text = str(value or "")
    if not text.isdecimal() or int(text) <= 0:
        raise WorkspaceRepositoryError(f"{field}_invalid")
    return text


class WorkspaceRepository:
    def get_saved_version(self, *, workspace_gid: str, version_gid: str,
                          tenant_gid: str, owner_gid: str) -> dict[str, Any]:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT w.gid workspace_gid,v.gid version_gid,v.status,v.content_hash,"
                "v.manifest_artifact_ref_json manifest_artifact_ref "
                "FROM workmanship_sim_workspaces w JOIN workmanship_sim_workspace_versions v "
                "ON v.workspace_gid=w.gid WHERE w.gid=%s AND v.gid=%s AND w.tenant_gid=%s "
                "AND w.owner_gid=%s AND w.removed_at IS NULL AND v.removed_at IS NULL",
                (_gid(workspace_gid,"workspace_gid"),_gid(version_gid,"version_gid"),
                 _gid(tenant_gid,"tenant_gid"),_gid(owner_gid,"owner_gid")),
            )
            row=cursor.fetchone()
        if not row: raise WorkspaceRepositoryError("workspace_version_not_found")
        result=dict(row)
        result["workspace_gid"],result["version_gid"]=str(result["workspace_gid"]),str(result["version_gid"])
        value=result.get("manifest_artifact_ref")
        if isinstance(value,str): result["manifest_artifact_ref"]=json.loads(value)
        return result

    def record_export_ref(self, *, export_gid: str, workspace_gid: str, version_gid: str,
                          tenant_gid: str, owner_gid: str, target_personal_space_gid: str,
                          target_repository_gid: str, consumer_capability_id: str,
                          consumer_major_version: int, content_hash: str, token_digest: str,
                          idempotency_key: str, expires_at) -> None:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO workmanship_sim_workspace_export_refs "
                "(gid,workspace_gid,workspace_version_gid,tenant_gid,owner_gid,target_personal_space_gid,"
                "target_repository_gid,consumer_capability_id,consumer_major_version,content_hash,token_digest,"
                "idempotency_key,expires_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (export_gid,workspace_gid,version_gid,tenant_gid,owner_gid,target_personal_space_gid,
                 target_repository_gid,consumer_capability_id,consumer_major_version,content_hash,
                 token_digest,idempotency_key,expires_at),
            )

    def create(self, *, name: str, tenant_gid: str, owner_gid: str) -> dict[str, Any]:
        workspace_gid, version_gid = str(next_gid()), str(next_gid())
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO workmanship_sim_workspaces "
                "(gid,tenant_gid,owner_gid,name,status,row_version) VALUES (%s,%s,%s,%s,'active',1)",
                (workspace_gid, _gid(tenant_gid, "tenant_gid"), _gid(owner_gid, "owner_gid"), name),
            )
            cursor.execute(
                "INSERT INTO workmanship_sim_workspace_versions "
                "(gid,workspace_gid,tenant_gid,owner_gid,sequence,status,row_version) "
                "VALUES (%s,%s,%s,%s,1,'draft',1)",
                (version_gid, workspace_gid, tenant_gid, owner_gid),
            )
            cursor.execute(
                "INSERT INTO workmanship_sim_workspace_heads (workspace_gid,version_gid,row_version) VALUES (%s,%s,1)",
                (workspace_gid, version_gid),
            )
        return {"workspace_gid": workspace_gid, "version_gid": version_gid, "name": name,
                "status": "active", "row_version": 1, "nodes": [], "bindings": []}

    def search(self, *, tenant_gid: str, owner_gid: str, offset: int, page_size: int) -> dict[str, Any]:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT w.gid AS workspace_gid,h.version_gid,w.name,w.status,w.row_version,w.updated_at "
                "FROM workmanship_sim_workspaces w JOIN workmanship_sim_workspace_heads h ON h.workspace_gid=w.gid "
                "WHERE w.tenant_gid=%s AND w.owner_gid=%s AND w.removed_at IS NULL "
                "ORDER BY w.updated_at DESC,w.gid DESC LIMIT %s OFFSET %s",
                (_gid(tenant_gid, "tenant_gid"), _gid(owner_gid, "owner_gid"), page_size + 1, offset),
            )
            rows = [dict(row) for row in cursor.fetchall()]
        more = len(rows) > page_size
        rows = rows[:page_size]
        for row in rows:
            row["workspace_gid"], row["version_gid"] = str(row["workspace_gid"]), str(row["version_gid"])
            if row.get("updated_at") is not None:
                row["updated_at"] = row["updated_at"].isoformat()
        return {"items": rows, "next_cursor": str(offset + page_size) if more else None}

    def get(self, workspace_gid: str, *, tenant_gid: str, owner_gid: str, lock: bool = False) -> dict[str, Any] | None:
        suffix = " FOR UPDATE" if lock else ""
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT w.gid AS workspace_gid,h.version_gid,w.name,w.status,w.row_version "
                "FROM workmanship_sim_workspaces w JOIN workmanship_sim_workspace_heads h ON h.workspace_gid=w.gid "
                "WHERE w.gid=%s AND w.tenant_gid=%s AND w.owner_gid=%s AND w.removed_at IS NULL" + suffix,
                (_gid(workspace_gid, "workspace_gid"), _gid(tenant_gid, "tenant_gid"), _gid(owner_gid, "owner_gid")),
            )
            workspace = cursor.fetchone()
            if not workspace:
                return None
            cursor.execute(
                "SELECT gid AS node_gid,parent_gid,node_type,name,sort_order AS position,row_version "
                "FROM workmanship_sim_workspace_nodes WHERE workspace_gid=%s AND tenant_gid=%s "
                "AND owner_gid=%s AND removed_at IS NULL ORDER BY parent_gid,sort_order,gid",
                (workspace_gid, tenant_gid, owner_gid),
            )
            nodes = [dict(row) for row in cursor.fetchall()]
            cursor.execute(
                "SELECT gid AS binding_gid,node_gid,occurrence_gid,binding_role AS role,row_version "
                "FROM workmanship_sim_workspace_bindings WHERE workspace_gid=%s AND tenant_gid=%s "
                "AND owner_gid=%s AND removed_at IS NULL ORDER BY node_gid,gid",
                (workspace_gid, tenant_gid, owner_gid),
            )
            bindings = [dict(row) for row in cursor.fetchall()]
        data = dict(workspace)
        for key in ("workspace_gid", "version_gid"):
            data[key] = str(data[key])
        for row in nodes:
            row["node_gid"] = str(row["node_gid"])
            row["parent_gid"] = str(row["parent_gid"]) if row.get("parent_gid") is not None else None
        for row in bindings:
            for key in ("binding_gid", "node_gid", "occurrence_gid"):
                row[key] = str(row[key])
        data.update(nodes=nodes, bindings=bindings)
        return data

    def mutate(
        self, *, workspace_gid: str, tenant_gid: str, owner_gid: str,
        expected_row_version: int, idempotency_key: str, operation: str,
        values: Mapping[str, Any],
    ) -> dict[str, Any]:
        workspace_gid = _gid(workspace_gid, "workspace_gid")
        tenant_gid, owner_gid = _gid(tenant_gid, "tenant_gid"), _gid(owner_gid, "owner_gid")
        canonical = json.dumps({"operation": operation, "values": dict(values)}, ensure_ascii=False,
                               sort_keys=True, separators=(",", ":"))
        request_hash = hashlib.sha256(canonical.encode()).hexdigest()
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT row_version FROM workmanship_sim_workspaces WHERE gid=%s AND tenant_gid=%s "
                "AND owner_gid=%s AND removed_at IS NULL FOR UPDATE",
                (workspace_gid, tenant_gid, owner_gid),
            )
            current = cursor.fetchone()
            if not current:
                raise WorkspaceRepositoryError("workspace_not_found")
            cursor.execute(
                "SELECT request_hash,response_json FROM workmanship_sim_workspace_idempotency "
                "WHERE workspace_gid=%s AND idempotency_key=%s AND expires_at>NOW(6)",
                (workspace_gid, idempotency_key),
            )
            replay = cursor.fetchone()
            if replay:
                if replay["request_hash"] != request_hash:
                    raise WorkspaceRepositoryError("idempotency_conflict")
                value = replay["response_json"]
                return json.loads(value) if isinstance(value, str) else dict(value)
            if int(current["row_version"]) != expected_row_version:
                raise WorkspaceRepositoryError("version_conflict")

            if operation == "create_node":
                parent_gid = values.get("parent_gid")
                if parent_gid is not None:
                    parent_gid = _gid(parent_gid, "parent_gid")
                    cursor.execute(
                        "SELECT 1 FROM workmanship_sim_workspace_nodes WHERE gid=%s AND workspace_gid=%s "
                        "AND tenant_gid=%s AND owner_gid=%s AND removed_at IS NULL",
                        (parent_gid, workspace_gid, tenant_gid, owner_gid),
                    )
                    if not cursor.fetchone():
                        raise WorkspaceRepositoryError("parent_not_found")
                node_type, name = str(values.get("node_type") or ""), str(values.get("name") or "").strip()
                if node_type not in {"line", "station", "process", "operation"} or not name:
                    raise WorkspaceRepositoryError("invalid_structure_node")
                cursor.execute(
                    "SELECT COALESCE(MAX(sort_order),-1)+1 AS position FROM workmanship_sim_workspace_nodes "
                    "WHERE workspace_gid=%s AND parent_gid<=>%s AND removed_at IS NULL",
                    (workspace_gid, parent_gid),
                )
                position = int(cursor.fetchone()["position"])
                entity_gid = str(next_gid())
                cursor.execute(
                    "INSERT INTO workmanship_sim_workspace_nodes "
                    "(gid,workspace_gid,tenant_gid,owner_gid,parent_gid,node_type,name,sort_order,row_version) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,1)",
                    (entity_gid, workspace_gid, tenant_gid, owner_gid, parent_gid, node_type, name, position),
                )
                patch = {"op": "create", "node_gid": entity_gid, "parent_gid": parent_gid,
                         "node_type": node_type, "name": name, "position": position}
            elif operation == "move_node":
                node_gid = _gid(values.get("node_gid"), "node_gid")
                new_parent = values.get("parent_gid")
                new_parent = _gid(new_parent, "parent_gid") if new_parent is not None else None
                cursor.execute(
                    "SELECT gid,parent_gid FROM workmanship_sim_workspace_nodes WHERE workspace_gid=%s "
                    "AND tenant_gid=%s AND owner_gid=%s AND removed_at IS NULL",
                    (workspace_gid, tenant_gid, owner_gid),
                )
                nodes = {str(row["gid"]): str(row["parent_gid"]) if row["parent_gid"] is not None else None
                         for row in cursor.fetchall()}
                if node_gid not in nodes:
                    raise WorkspaceRepositoryError("structure_node_not_found")
                if new_parent is not None and new_parent not in nodes:
                    raise WorkspaceRepositoryError("parent_not_found")
                cursor_gid = new_parent
                while cursor_gid is not None:
                    if cursor_gid == node_gid:
                        raise WorkspaceRepositoryError("structure_cycle")
                    cursor_gid = nodes[cursor_gid]
                cursor.execute(
                    "SELECT COALESCE(MAX(sort_order),-1)+1 AS position FROM workmanship_sim_workspace_nodes "
                    "WHERE workspace_gid=%s AND parent_gid<=>%s AND removed_at IS NULL AND gid<>%s",
                    (workspace_gid, new_parent, node_gid),
                )
                position = int(cursor.fetchone()["position"])
                cursor.execute(
                    "UPDATE workmanship_sim_workspace_nodes SET parent_gid=%s,sort_order=%s,row_version=row_version+1,"
                    "updated_at=NOW(6) WHERE gid=%s", (new_parent, position, node_gid),
                )
                entity_gid = node_gid
                patch = {"op": "move", "node_gid": node_gid, "parent_gid": new_parent, "position": position}
            elif operation == "remove_node":
                node_gid = _gid(values.get("node_gid"), "node_gid")
                cursor.execute(
                    "SELECT gid,parent_gid FROM workmanship_sim_workspace_nodes WHERE workspace_gid=%s "
                    "AND tenant_gid=%s AND owner_gid=%s AND removed_at IS NULL",
                    (workspace_gid, tenant_gid, owner_gid),
                )
                rows = [dict(row) for row in cursor.fetchall()]
                if node_gid not in {str(row["gid"]) for row in rows}:
                    raise WorkspaceRepositoryError("structure_node_not_found")
                removed = {node_gid}
                while True:
                    found = {str(row["gid"]) for row in rows if row["parent_gid"] is not None and str(row["parent_gid"]) in removed}
                    if found <= removed:
                        break
                    removed.update(found)
                marks = ",".join(["%s"] * len(removed))
                ordered = sorted(removed, key=int)
                cursor.execute(
                    f"UPDATE workmanship_sim_workspace_nodes SET removed_at=NOW(6),row_version=row_version+1 "
                    f"WHERE gid IN ({marks})", ordered,
                )
                cursor.execute(
                    f"UPDATE workmanship_sim_workspace_bindings SET removed_at=NOW(6),row_version=row_version+1 "
                    f"WHERE node_gid IN ({marks}) AND removed_at IS NULL", ordered,
                )
                cursor.execute(
                    "DELETE c FROM workmanship_sim_workspace_load_claims c "
                    "JOIN workmanship_sim_workspace_bindings b ON b.gid=c.binding_gid WHERE b.workspace_gid=%s AND b.removed_at IS NOT NULL",
                    (workspace_gid,),
                )
                entity_gid = node_gid
                patch = {"op": "remove", "removed_node_gids": ordered}
            elif operation == "create_binding":
                node_gid = _gid(values.get("node_gid"), "node_gid")
                occurrence_gid = _gid(values.get("occurrence_gid"), "occurrence_gid")
                role = str(values.get("role") or "")
                if role not in {"load", "operate"}:
                    raise WorkspaceRepositoryError("invalid_binding_role")
                cursor.execute(
                    "SELECT 1 FROM workmanship_sim_workspace_nodes WHERE gid=%s AND workspace_gid=%s "
                    "AND tenant_gid=%s AND owner_gid=%s AND removed_at IS NULL", (node_gid, workspace_gid, tenant_gid, owner_gid),
                )
                if not cursor.fetchone():
                    raise WorkspaceRepositoryError("structure_node_not_found")
                entity_gid = str(next_gid())
                cursor.execute(
                    "INSERT INTO workmanship_sim_workspace_bindings "
                    "(gid,workspace_gid,tenant_gid,owner_gid,node_gid,occurrence_gid,binding_role,row_version) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,1)",
                    (entity_gid, workspace_gid, tenant_gid, owner_gid, node_gid, occurrence_gid, role),
                )
                if role == "load":
                    try:
                        cursor.execute(
                            "INSERT INTO workmanship_sim_workspace_load_claims (workspace_gid,occurrence_gid,binding_gid) VALUES (%s,%s,%s)",
                            (workspace_gid, occurrence_gid, entity_gid),
                        )
                    except Exception as exc:
                        raise WorkspaceRepositoryError("load_binding_exists") from exc
                patch = {"op": "bind", "binding_gid": entity_gid, "node_gid": node_gid,
                         "occurrence_gid": occurrence_gid, "role": role}
            elif operation == "remove_binding":
                entity_gid = _gid(values.get("binding_gid"), "binding_gid")
                cursor.execute(
                    "UPDATE workmanship_sim_workspace_bindings SET removed_at=NOW(6),row_version=row_version+1 "
                    "WHERE gid=%s AND workspace_gid=%s AND tenant_gid=%s AND owner_gid=%s AND removed_at IS NULL",
                    (entity_gid, workspace_gid, tenant_gid, owner_gid),
                )
                if cursor.rowcount != 1:
                    raise WorkspaceRepositoryError("binding_not_found")
                cursor.execute("DELETE FROM workmanship_sim_workspace_load_claims WHERE binding_gid=%s", (entity_gid,))
                patch = {"op": "unbind", "binding_gid": entity_gid}
            else:
                raise WorkspaceRepositoryError("operation_invalid")

            next_version = expected_row_version + 1
            cursor.execute(
                "UPDATE workmanship_sim_workspaces SET row_version=%s,updated_at=NOW(6) WHERE gid=%s AND row_version=%s",
                (next_version, workspace_gid, expected_row_version),
            )
            if cursor.rowcount != 1:
                raise WorkspaceRepositoryError("version_conflict")
            result = {"entity_gid": entity_gid, "row_version": next_version, "patch": patch}
            cursor.execute(
                "INSERT INTO workmanship_sim_workspace_idempotency "
                "(workspace_gid,idempotency_key,request_hash,response_json,expires_at) "
                "VALUES (%s,%s,%s,%s,DATE_ADD(NOW(6),INTERVAL 24 HOUR))",
                (workspace_gid, idempotency_key, request_hash, json.dumps(result, ensure_ascii=False, separators=(",", ":"))),
            )
        return result

    def load_freeze_source(self, *, workspace_gid: str, tenant_gid: str, owner_gid: str) -> dict[str, Any]:
        workspace_gid = _gid(workspace_gid, "workspace_gid")
        tenant_gid, owner_gid = _gid(tenant_gid, "tenant_gid"), _gid(owner_gid, "owner_gid")
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT w.gid AS workspace_gid,h.version_gid,w.row_version,v.status AS version_status "
                "FROM workmanship_sim_workspaces w JOIN workmanship_sim_workspace_heads h ON h.workspace_gid=w.gid "
                "JOIN workmanship_sim_workspace_versions v ON v.gid=h.version_gid "
                "WHERE w.gid=%s AND w.tenant_gid=%s AND w.owner_gid=%s AND w.removed_at IS NULL",
                (workspace_gid, tenant_gid, owner_gid),
            )
            source = cursor.fetchone()
            if not source:
                raise WorkspaceRepositoryError("workspace_not_found")
            cursor.execute(
                "SELECT gid AS node_gid,parent_gid,node_type,name,sort_order AS position,source_bop_node_gid "
                "FROM workmanship_sim_workspace_nodes WHERE workspace_gid=%s AND tenant_gid=%s AND owner_gid=%s "
                "AND removed_at IS NULL ORDER BY parent_gid,sort_order,gid",
                (workspace_gid, tenant_gid, owner_gid),
            )
            nodes = [dict(row) for row in cursor.fetchall()]
            cursor.execute(
                "SELECT gid AS binding_gid,node_gid,occurrence_gid,binding_role AS role "
                "FROM workmanship_sim_workspace_bindings WHERE workspace_gid=%s AND tenant_gid=%s AND owner_gid=%s "
                "AND removed_at IS NULL ORDER BY node_gid,gid",
                (workspace_gid, tenant_gid, owner_gid),
            )
            bindings = [dict(row) for row in cursor.fetchall()]
        result = dict(source)
        for key in ("workspace_gid", "version_gid"):
            result[key] = str(result[key])
        for row in nodes:
            for key in ("node_gid", "parent_gid", "source_bop_node_gid"):
                if row.get(key) is not None:
                    row[key] = str(row[key])
        for row in bindings:
            for key in ("binding_gid", "node_gid", "occurrence_gid"):
                row[key] = str(row[key])
        result.update(nodes=nodes, bindings=bindings)
        return result

    def find_freeze_result(self, *, workspace_gid: str, idempotency_key: str,
                           request_hash: str) -> dict[str, Any] | None:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT version_gid,content_hash,artifact_ref_json,status FROM workmanship_sim_workspace_freeze_outbox "
                "WHERE workspace_gid=%s AND idempotency_key=%s",
                (_gid(workspace_gid, "workspace_gid"), idempotency_key),
            )
            row = cursor.fetchone()
        if not row:
            return None
        if row["content_hash"] != request_hash:
            raise WorkspaceRepositoryError("idempotency_conflict")
        if row["status"] != "completed":
            return None
        artifact = row["artifact_ref_json"]
        if isinstance(artifact, str):
            artifact = json.loads(artifact)
        return {"workspace_gid": str(workspace_gid), "version_gid": str(row["version_gid"]),
                "status": "frozen", "content_hash": request_hash, "artifact_ref": artifact}

    def complete_freeze(
        self, *, workspace_gid: str, tenant_gid: str, owner_gid: str, version_gid: str,
        expected_row_version: int, idempotency_key: str, content_hash: str,
        artifact_ref: Mapping[str, Any], algorithms: Mapping[str, str],
    ) -> dict[str, Any]:
        outbox_gid = str(next_gid())
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT w.row_version,v.status FROM workmanship_sim_workspaces w "
                "JOIN workmanship_sim_workspace_versions v ON v.gid=%s AND v.workspace_gid=w.gid "
                "WHERE w.gid=%s AND w.tenant_gid=%s AND w.owner_gid=%s FOR UPDATE",
                (version_gid, workspace_gid, tenant_gid, owner_gid),
            )
            current = cursor.fetchone()
            if not current:
                raise WorkspaceRepositoryError("workspace_not_found")
            if int(current["row_version"]) != int(expected_row_version):
                raise WorkspaceRepositoryError("version_conflict")
            if current["status"] != "draft":
                raise WorkspaceRepositoryError("workspace_version_not_draft")
            cursor.execute(
                "INSERT INTO workmanship_sim_workspace_freeze_outbox "
                "(gid,workspace_gid,version_gid,tenant_gid,owner_gid,idempotency_key,content_hash,artifact_ref_json,status) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'completed')",
                (outbox_gid, workspace_gid, version_gid, tenant_gid, owner_gid, idempotency_key,
                 content_hash, json.dumps(dict(artifact_ref), sort_keys=True)),
            )
            cursor.execute(
                "UPDATE workmanship_sim_workspace_versions SET status='frozen',content_hash=%s,"
                "manifest_artifact_ref_json=%s,algorithm_versions_json=%s,row_version=row_version+1,updated_at=NOW(6) "
                "WHERE gid=%s AND status='draft'",
                (content_hash, json.dumps(dict(artifact_ref), sort_keys=True),
                 json.dumps(dict(algorithms), sort_keys=True), version_gid),
            )
            if cursor.rowcount != 1:
                raise WorkspaceRepositoryError("workspace_version_not_draft")
            cursor.execute(
                "UPDATE workmanship_sim_workspaces SET row_version=row_version+1,updated_at=NOW(6) "
                "WHERE gid=%s AND row_version=%s", (workspace_gid, expected_row_version),
            )
            if cursor.rowcount != 1:
                raise WorkspaceRepositoryError("version_conflict")
        return {"workspace_gid": str(workspace_gid), "version_gid": str(version_gid), "status": "frozen",
                "content_hash": content_hash, "artifact_ref": dict(artifact_ref)}

    def record_orphan(
        self, *, workspace_gid: str, version_gid: str, tenant_gid: str, owner_gid: str,
        idempotency_key: str, content_hash: str, artifact_ref: Mapping[str, Any], status: str,
    ) -> None:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO workmanship_sim_workspace_freeze_outbox "
                "(gid,workspace_gid,version_gid,tenant_gid,owner_gid,idempotency_key,content_hash,artifact_ref_json,status) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                "content_hash=VALUES(content_hash),artifact_ref_json=VALUES(artifact_ref_json),status=VALUES(status),updated_at=NOW(6)",
                (str(next_gid()), workspace_gid, version_gid, tenant_gid, owner_gid, idempotency_key,
                 content_hash, json.dumps(dict(artifact_ref), sort_keys=True), status),
            )

    def record_unavailable(
        self, *, workspace_gid: str, version_gid: str, tenant_gid: str, owner_gid: str,
        idempotency_key: str, content_hash: str, status: str,
    ) -> None:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO workmanship_sim_workspace_freeze_outbox "
                "(gid,workspace_gid,version_gid,tenant_gid,owner_gid,idempotency_key,content_hash,artifact_ref_json,status) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,'{}',%s) ON DUPLICATE KEY UPDATE "
                "content_hash=VALUES(content_hash),status=VALUES(status),updated_at=NOW(6)",
                (str(next_gid()), workspace_gid, version_gid, tenant_gid, owner_gid,
                 idempotency_key, content_hash, status),
            )


__all__ = ["WorkspaceRepository", "WorkspaceRepositoryError"]

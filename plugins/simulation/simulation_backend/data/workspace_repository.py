"""Persistence boundary for private, owner-scoped Simulation workspaces."""
from __future__ import annotations

import json
import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from backend.platform_sdk.ids import next_gid

from .connection import get_simulation_conn


class WorkspaceRepositoryError(RuntimeError):
    pass


_EMPTY_CACHE_REVISION_HASH = "sha256:" + "0" * 64


def next_cache_revision_hash(
    previous: str, patch: Mapping[str, Any], next_row_version: int,
) -> str:
    if not isinstance(previous, str) or not previous.startswith("sha256:") or len(previous) != 71:
        raise WorkspaceRepositoryError("cache_revision_hash_invalid")
    canonical = json.dumps(patch, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload = f"{previous}|{canonical}|{next_row_version}".encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


_FORK_DEPTH_RANK = {"station": 1, "role": 2, "process": 3, "operation": 4}
_NODE_DEPTH_RANK = {
    "line": 0, "line_process": 0,
    "station": 1, "station_process": 1,
    "role": 2, "operator_process": 2,
    "process": 3, "operation": 4,
}


def project_manifest_for_fork(manifest: Mapping[str, Any], fork_depth: str) -> dict[str, list[dict[str, Any]]]:
    """Select the instance boundary fixed by a private workspace Fork plan."""
    if fork_depth not in {"all", *_FORK_DEPTH_RANK}:
        raise WorkspaceRepositoryError("fork_depth_invalid")
    source_nodes = [dict(row) for row in manifest.get("nodes", [])]
    if fork_depth == "all":
        return {"nodes": source_nodes, "bindings": [dict(row) for row in manifest.get("bindings", [])]}
    limit = _FORK_DEPTH_RANK[fork_depth]
    candidates = {str(row["node_gid"]): row for row in source_nodes
                  if _NODE_DEPTH_RANK.get(str(row.get("node_type") or ""), limit + 1) <= limit}
    included: set[str] = set()
    pending = dict(candidates)
    while pending:
        progressed = False
        for gid, row in list(pending.items()):
            parent = row.get("parent_gid")
            if parent is None or str(parent) in included:
                included.add(gid)
                pending.pop(gid)
                progressed = True
        if not progressed:
            break
    return {"nodes": [row for row in source_nodes if str(row["node_gid"]) in included], "bindings": []}


def _gid(value: object, field: str) -> str:
    text = str(value or "")
    if not text.isdecimal() or int(text) <= 0:
        raise WorkspaceRepositoryError(f"{field}_invalid")
    return text


def _sha256_body(value: object, field: str) -> str:
    text = str(value or "")
    if text.startswith("sha256:"):
        text = text[7:]
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text.casefold()):
        raise WorkspaceRepositoryError(f"{field}_invalid")
    return text.casefold()


def _dependency_source_identity(parent_artifact_hash: str, location: str) -> str:
    normalized = str(location or "").replace("\\", "/").casefold()
    return hashlib.sha256(f"{parent_artifact_hash}\0{normalized}".encode("utf-8")).hexdigest()


class WorkspaceRepository:
    @staticmethod
    def _idempotency_begin(cursor, *, workspace_gid: str, idempotency_key: str,
                           request: Mapping[str, Any]) -> tuple[str, dict[str, Any] | None]:
        if not idempotency_key:
            return "", None
        if len(idempotency_key) > 191:
            raise WorkspaceRepositoryError("idempotency_key_invalid")
        request_hash = hashlib.sha256(json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        cursor.execute("SELECT request_hash,response_json FROM workmanship_sim_workspace_idempotency WHERE workspace_gid=%s AND idempotency_key=%s FOR UPDATE", (workspace_gid, idempotency_key))
        row = cursor.fetchone()
        if not row:
            return request_hash, None
        if str(row["request_hash"]) != request_hash:
            raise WorkspaceRepositoryError("idempotency_conflict")
        value = row["response_json"]
        return request_hash, json.loads(value) if isinstance(value, str) else dict(value)

    @staticmethod
    def _idempotency_finish(cursor, *, workspace_gid: str, idempotency_key: str,
                            request_hash: str, response: Mapping[str, Any]) -> None:
        if not idempotency_key:
            return
        cursor.execute("INSERT INTO workmanship_sim_workspace_idempotency (workspace_gid,idempotency_key,request_hash,response_json,expires_at) VALUES (%s,%s,%s,%s,DATE_ADD(NOW(6),INTERVAL 24 HOUR))", (workspace_gid, idempotency_key, request_hash, json.dumps(dict(response), ensure_ascii=False, sort_keys=True, separators=(",", ":"))))

    @staticmethod
    def _decorate(row: dict[str, Any], *, owner_gid: str, project_gids: list[str]) -> dict[str, Any]:
        result = dict(row)
        for key in ("workspace_gid", "version_gid", "owner_gid", "primary_project_gid"):
            if result.get(key) is not None:
                result[key] = str(result[key])
        result["is_owner"] = result.get("owner_gid") == str(owner_gid)
        result["project_gids"] = project_gids
        if result.get("updated_at") is not None and not isinstance(result["updated_at"], str):
            result["updated_at"] = result["updated_at"].isoformat()
        return result

    @staticmethod
    def _replace_projects(cursor, workspace_gid: str, project_gids: list[str]) -> None:
        cursor.execute("DELETE FROM workmanship_sim_workspace_projects WHERE workspace_gid=%s", (workspace_gid,))
        for position, project_gid in enumerate(project_gids):
            cursor.execute(
                "INSERT INTO workmanship_sim_workspace_projects (workspace_gid,project_gid,sort_order) VALUES (%s,%s,%s)",
                (workspace_gid, _gid(project_gid, "project_gid"), position),
            )

    @staticmethod
    def _lock_owned_workspace(cursor, *, workspace_gid: str, tenant_gid: str,
                              actor_gid: str, expected_row_version: int) -> dict[str, Any]:
        cursor.execute(
            "SELECT row_version,cache_revision_hash,status FROM workmanship_sim_workspaces "
            "WHERE gid=%s AND tenant_gid=%s AND owner_gid=%s AND removed_at IS NULL FOR UPDATE",
            (workspace_gid, tenant_gid, actor_gid),
        )
        row = cursor.fetchone()
        if not row:
            raise WorkspaceRepositoryError("workspace_not_found")
        if int(row["row_version"]) != expected_row_version:
            raise WorkspaceRepositoryError("version_conflict")
        if str(row.get("status") or "") == "frozen":
            raise WorkspaceRepositoryError("workspace_frozen")
        return dict(row)

    def load_frozen_environment_runtime_model(self, *, workspace_gid: str, version_gid: str,
                                              tenant_gid: str, actor_gid: str) -> dict[str, Any]:
        workspace_gid,version_gid=_gid(workspace_gid,"workspace_gid"),_gid(version_gid,"version_gid")
        with get_simulation_conn() as conn,conn.cursor() as cursor:
            cursor.execute("SELECT w.gid FROM workmanship_sim_workspaces w JOIN workmanship_sim_workspace_heads h ON h.workspace_gid=w.gid JOIN workmanship_sim_workspace_versions v ON v.gid=h.version_gid WHERE w.gid=%s AND h.version_gid=%s AND w.tenant_gid=%s AND (w.owner_gid=%s OR w.visibility='shared') AND w.status='frozen' AND v.status='frozen' AND w.removed_at IS NULL AND v.removed_at IS NULL",(workspace_gid,version_gid,_gid(tenant_gid,"tenant_gid"),_gid(actor_gid,"actor_gid")))
            if not cursor.fetchone(): raise WorkspaceRepositoryError("frozen_workspace_version_not_found")
        return {"runtime_model":self.load_environment_runtime_model(workspace_gid=workspace_gid,tenant_gid=tenant_gid,actor_gid=actor_gid),"version_gid":version_gid,"connector_device_id":None}

    @staticmethod
    def _advance_workspace_revision(cursor, *, workspace_gid: str, current: Mapping[str, Any],
                                    patch: Mapping[str, Any]) -> tuple[int, str]:
        next_version = int(current["row_version"]) + 1
        previous_hash = str(current.get("cache_revision_hash") or _EMPTY_CACHE_REVISION_HASH)
        cache_hash = next_cache_revision_hash(previous_hash, patch, next_version)
        cursor.execute(
            "UPDATE workmanship_sim_workspaces SET cache_revision_hash=%s,row_version=%s,updated_at=NOW(6) "
            "WHERE gid=%s AND row_version=%s",
            (cache_hash, next_version, workspace_gid, int(current["row_version"])),
        )
        if cursor.rowcount != 1:
            raise WorkspaceRepositoryError("version_conflict")
        cursor.execute(
            "UPDATE workmanship_sim_materialization_verifications SET state='stale',updated_at=NOW(6) "
            "WHERE workspace_gid=%s AND state='verified'",
            (workspace_gid,),
        )
        return next_version, cache_hash

    def add_model_document(self, *, workspace_gid: str, expected_workspace_version: int,
                           document: Mapping[str, Any], actor_gid: str,
                           tenant_gid: str, idempotency_key: str = "") -> dict[str, Any]:
        workspace_gid = _gid(workspace_gid, "workspace_gid")
        tenant_gid, actor_gid = _gid(tenant_gid, "tenant_gid"), _gid(actor_gid, "actor_gid")
        role = str(document.get("role") or "")
        media_type = str(document.get("media_type") or "")
        portability = str(document.get("portability") or "")
        if role not in {"primary", "inserted"}:
            raise WorkspaceRepositoryError("document_role_invalid")
        if media_type not in {"application/plmxml+xml", "model/vnd.jt"}:
            raise WorkspaceRepositoryError("document_media_type_invalid")
        if portability not in {"portable", "device_bound"}:
            raise WorkspaceRepositoryError("document_portability_invalid")
        source_hash = _sha256_body(document.get("source_identity_hash"), "source_identity_hash")
        content_hash = _sha256_body(document.get("content_sha256"), "content_sha256")
        document_gid = str(next_gid())
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            workspace = self._lock_owned_workspace(
                cursor, workspace_gid=workspace_gid, tenant_gid=tenant_gid,
                actor_gid=actor_gid, expected_row_version=expected_workspace_version,
            )
            request_hash, replay = self._idempotency_begin(cursor, workspace_gid=workspace_gid,
                idempotency_key=idempotency_key, request={"op": "add_model_document", "document": dict(document)})
            if replay is not None:
                return replay
            if role == "primary":
                cursor.execute(
                    "SELECT gid FROM workmanship_sim_vm_documents WHERE workspace_gid=%s "
                    "AND primary_slot=1 AND removed_at IS NULL FOR UPDATE",
                    (workspace_gid,),
                )
                if cursor.fetchone():
                    raise WorkspaceRepositoryError("primary_model_document_exists")
            cursor.execute(
                "SELECT COALESCE(MAX(sort_order),-1)+1 AS position FROM workmanship_sim_vm_documents "
                "WHERE workspace_gid=%s AND removed_at IS NULL",
                (workspace_gid,),
            )
            position_row = cursor.fetchone() or {"position": 0}
            cursor.execute(
                "INSERT INTO workmanship_sim_vm_documents "
                "(gid,workspace_gid,tenant_gid,owner_gid,document_role,primary_slot,display_name,media_type,"
                "artifact_ref_json,content_sha256,portability,connector_device_id,sort_order,source_kind,source_identity_hash,status,row_version) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'active',1)",
                (document_gid, workspace_gid, tenant_gid, actor_gid, role, 1 if role == "primary" else None,
                 str(document.get("display_name") or ""), media_type,
                 json.dumps(document.get("artifact_ref"), ensure_ascii=False, sort_keys=True, separators=(",", ":")) if document.get("artifact_ref") else None,
                 content_hash, portability, str(document.get("connector_device_id") or "") or None,
                 int(position_row.get("position") or 0),
                 str(document.get("source_kind") or "artifact"), source_hash),
            )
            next_version, cache_hash = self._advance_workspace_revision(
                cursor, workspace_gid=workspace_gid, current=workspace,
                patch={"op": "add_model_document", "document_gid": document_gid, "role": role,
                       "content_sha256": content_hash},
            )
            result = {"document_gid": document_gid, "workspace_gid": workspace_gid, "role": role,
                "row_version": 1, "workspace_row_version": next_version,
                "cache_revision_hash": cache_hash}
            self._idempotency_finish(cursor, workspace_gid=workspace_gid, idempotency_key=idempotency_key,
                                     request_hash=request_hash, response=result)
        return result

    def search_model_documents(self, *, workspace_gid: str, tenant_gid: str,
                               actor_gid: str) -> dict[str, Any]:
        workspace_gid = _gid(workspace_gid, "workspace_gid")
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT d.gid AS document_gid,d.workspace_gid,d.document_role AS role,d.display_name,d.media_type,"
                "d.artifact_ref_json,d.source_kind,d.source_identity_hash,d.content_sha256,d.portability,d.connector_device_id,d.sort_order,d.row_version "
                "FROM workmanship_sim_vm_documents d JOIN workmanship_sim_workspaces w ON w.gid=d.workspace_gid "
                "WHERE d.workspace_gid=%s AND d.tenant_gid=%s AND (w.owner_gid=%s OR w.visibility='shared') "
                "AND d.removed_at IS NULL AND w.removed_at IS NULL ORDER BY d.sort_order,d.gid",
                (workspace_gid, _gid(tenant_gid, "tenant_gid"), _gid(actor_gid, "actor_gid")),
            )
            rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            for key in ("document_gid", "workspace_gid"):
                if row.get(key) is not None:
                    row[key] = str(row[key])
            artifact = row.pop("artifact_ref_json", None)
            row["artifact_ref"] = json.loads(artifact) if isinstance(artifact, str) else artifact
            row["source_identity_hash"] = "sha256:" + str(row["source_identity_hash"])
            row["content_sha256"] = ("sha256:" + str(row["content_sha256"])) if row.get("content_sha256") else None
        return {"items": rows}

    def remove_model_document(self, *, workspace_gid: str, document_gid: str,
                              expected_workspace_version: int, actor_gid: str,
                              tenant_gid: str, idempotency_key: str = "") -> dict[str, Any]:
        workspace_gid, document_gid = _gid(workspace_gid, "workspace_gid"), _gid(document_gid, "document_gid")
        tenant_gid, actor_gid = _gid(tenant_gid, "tenant_gid"), _gid(actor_gid, "actor_gid")
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            workspace = self._lock_owned_workspace(cursor, workspace_gid=workspace_gid, tenant_gid=tenant_gid,
                                                   actor_gid=actor_gid, expected_row_version=expected_workspace_version)
            request_hash, replay = self._idempotency_begin(cursor, workspace_gid=workspace_gid,
                idempotency_key=idempotency_key, request={"op": "remove_model_document", "document_gid": document_gid})
            if replay is not None:
                return replay
            cursor.execute(
                "UPDATE workmanship_sim_vm_documents SET removed_at=NOW(6),primary_slot=NULL,row_version=row_version+1,updated_at=NOW(6) "
                "WHERE gid=%s AND workspace_gid=%s AND tenant_gid=%s AND removed_at IS NULL",
                (document_gid, workspace_gid, tenant_gid),
            )
            if cursor.rowcount != 1:
                raise WorkspaceRepositoryError("model_document_not_found")
            next_version, cache_hash = self._advance_workspace_revision(
                cursor, workspace_gid=workspace_gid, current=workspace,
                patch={"op": "remove_model_document", "document_gid": document_gid},
            )
            result = {"document_gid": document_gid, "workspace_gid": workspace_gid, "removed": True,
                "workspace_row_version": next_version, "cache_revision_hash": cache_hash}
            self._idempotency_finish(cursor, workspace_gid=workspace_gid, idempotency_key=idempotency_key,
                                     request_hash=request_hash, response=result)
        return result

    def create_alternate_hierarchy(self, *, workspace_gid: str, name: str,
                                   source_bop_version_gid: str | None,
                                   expected_workspace_version: int, actor_gid: str,
                                   tenant_gid: str, idempotency_key: str = "") -> dict[str, Any]:
        workspace_gid = _gid(workspace_gid, "workspace_gid")
        tenant_gid, actor_gid = _gid(tenant_gid, "tenant_gid"), _gid(actor_gid, "actor_gid")
        name = str(name or "").strip()
        if not name or len(name) > 255:
            raise WorkspaceRepositoryError("hierarchy_name_invalid")
        hierarchy_gid = str(next_gid())
        root_node_gid = str(next_gid())
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            workspace = self._lock_owned_workspace(
                cursor, workspace_gid=workspace_gid, tenant_gid=tenant_gid,
                actor_gid=actor_gid, expected_row_version=expected_workspace_version,
            )
            request_hash, replay = self._idempotency_begin(cursor, workspace_gid=workspace_gid,
                idempotency_key=idempotency_key, request={"op": "create_alternate_hierarchy", "name": name,
                                                          "source_bop_version_gid": source_bop_version_gid})
            if replay is not None:
                return replay
            cursor.execute(
                "SELECT COALESCE(MAX(sort_order),-1)+1 AS position FROM workmanship_sim_workspace_hierarchies "
                "WHERE workspace_gid=%s AND removed_at IS NULL",
                (workspace_gid,),
            )
            position_row = cursor.fetchone() or {"position": 0}
            cursor.execute(
                "INSERT INTO workmanship_sim_workspace_hierarchies "
                "(gid,workspace_gid,tenant_gid,owner_gid,name,source_bop_version_gid,projection_identity,status,sort_order,row_version) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,'active',%s,1)",
                (hierarchy_gid, workspace_gid, tenant_gid, actor_gid, name,
                 _gid(source_bop_version_gid, "source_bop_version_gid") if source_bop_version_gid else None,
                 f"ai00-hierarchy-{hierarchy_gid}", int(position_row.get("position") or 0)),
            )
            cursor.execute(
                "INSERT INTO workmanship_sim_workspace_nodes "
                "(gid,workspace_gid,tenant_gid,owner_gid,hierarchy_gid,parent_gid,node_type,name,sort_order,source_bop_node_gid,row_version) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,1)",
                (root_node_gid, workspace_gid, tenant_gid, actor_gid, hierarchy_gid, None,
                 "alternate_hierarchy", name, 0),
            )
            self._advance_workspace_revision(
                cursor, workspace_gid=workspace_gid, current=workspace,
                patch={"op": "create_alternate_hierarchy", "hierarchy_gid": hierarchy_gid, "name": name},
            )
            result = {"hierarchy_gid": hierarchy_gid, "root_node_gid": root_node_gid,
                      "workspace_gid": workspace_gid, "name": name, "row_version": 1}
            self._idempotency_finish(cursor, workspace_gid=workspace_gid, idempotency_key=idempotency_key,
                                     request_hash=request_hash, response=result)
        return result

    def bootstrap_alternate_hierarchy(self, *, workspace_gid: str, name: str,
                                      projection: Mapping[str, Any], expected_workspace_version: int,
                                      actor_gid: str, tenant_gid: str,
                                      idempotency_key: str) -> dict[str, Any]:
        workspace_gid = _gid(workspace_gid, "workspace_gid")
        tenant_gid, actor_gid = _gid(tenant_gid, "tenant_gid"), _gid(actor_gid, "actor_gid")
        name = str(name or "").strip()
        if not name or len(name) > 255:
            raise WorkspaceRepositoryError("hierarchy_name_invalid")
        fork_run_gid = _gid(projection.get("fork_operation_gid"), "fork_operation_gid")
        source_repository_gid = _gid(projection.get("source_repository_gid"), "source_repository_gid")
        source_version_gid = _gid(projection.get("source_version_gid"), "source_version_gid")
        source_hash = str(projection.get("source_content_hash") or "")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", source_hash):
            raise WorkspaceRepositoryError("bop_projection_hash_invalid")
        source_nodes = list(projection.get("nodes") or [])
        if len(source_nodes) > 10000:
            raise WorkspaceRepositoryError("bop_projection_too_large")
        normalized = {}
        for item in source_nodes:
            source_gid = _gid(item.get("node_gid"), "source_bop_node_gid")
            parent = item.get("parent_gid")
            normalized[source_gid] = {"source_gid": source_gid,
                "parent_source_gid": _gid(parent, "source_bop_parent_gid") if parent is not None else None,
                "node_type": str(item.get("node_type") or "")[:32],
                "name": str(item.get("name") or "").strip()[:255],
                "position": int(item.get("position") or 0)}
            if not normalized[source_gid]["node_type"] or not normalized[source_gid]["name"]:
                raise WorkspaceRepositoryError("bop_projection_node_invalid")
        if any(item["parent_source_gid"] not in normalized for item in normalized.values() if item["parent_source_gid"]):
            raise WorkspaceRepositoryError("bop_projection_parent_missing")
        ordered=[]; pending=dict(normalized)
        while pending:
            ready=[item for item in pending.values() if item["parent_source_gid"] is None or item["parent_source_gid"] in {row["source_gid"] for row in ordered}]
            if not ready: raise WorkspaceRepositoryError("bop_projection_cycle")
            ready.sort(key=lambda item:(item["parent_source_gid"] or "",item["position"],int(item["source_gid"])))
            for item in ready: ordered.append(item); pending.pop(item["source_gid"])
        hierarchy_gid = str(next_gid())
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            workspace = self._lock_owned_workspace(cursor, workspace_gid=workspace_gid, tenant_gid=tenant_gid,
                                                   actor_gid=actor_gid, expected_row_version=expected_workspace_version)
            request_hash, replay = self._idempotency_begin(cursor, workspace_gid=workspace_gid,
                idempotency_key=idempotency_key, request={"op":"bootstrap_alternate_hierarchy","name":name,
                    "fork_run_gid":fork_run_gid,"source_repository_gid":source_repository_gid,
                    "source_version_gid":source_version_gid,"source_content_hash":source_hash,
                    "nodes":source_nodes})
            if replay is not None: return replay
            cursor.execute("SELECT gid FROM workmanship_sim_workspace_hierarchies WHERE workspace_gid=%s AND source_bop_fork_run_gid=%s AND removed_at IS NULL",(workspace_gid,fork_run_gid))
            if cursor.fetchone(): raise WorkspaceRepositoryError("bop_fork_already_bootstrapped")
            cursor.execute("SELECT COALESCE(MAX(sort_order),-1)+1 AS position FROM workmanship_sim_workspace_hierarchies WHERE workspace_gid=%s AND removed_at IS NULL",(workspace_gid,))
            hierarchy_position=int((cursor.fetchone() or {"position":0})["position"])
            cursor.execute("INSERT INTO workmanship_sim_workspace_hierarchies (gid,workspace_gid,tenant_gid,owner_gid,name,source_bop_repository_gid,source_bop_version_gid,source_bop_fork_run_gid,source_bop_content_hash,projection_identity,status,sort_order,row_version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'bootstrap_pending',%s,1)",(hierarchy_gid,workspace_gid,tenant_gid,actor_gid,name,source_repository_gid,source_version_gid,fork_run_gid,source_hash,f"craft-fork:{fork_run_gid}",hierarchy_position))
            node_map={item["source_gid"]:str(next_gid()) for item in ordered}
            sibling_positions={}
            for item in ordered:
                parent_source=item["parent_source_gid"]
                position=sibling_positions.get(parent_source,0); sibling_positions[parent_source]=position+1
                cursor.execute("INSERT INTO workmanship_sim_workspace_nodes (gid,workspace_gid,tenant_gid,owner_gid,hierarchy_gid,parent_gid,node_type,name,sort_order,source_bop_node_gid,row_version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1)",(node_map[item["source_gid"]],workspace_gid,tenant_gid,actor_gid,hierarchy_gid,node_map.get(parent_source),item["node_type"],item["name"],position,item["source_gid"]))
            cursor.execute("UPDATE workmanship_sim_workspace_hierarchies SET status='active',updated_at=NOW(6) WHERE gid=%s",(hierarchy_gid,))
            next_version, cache_hash = self._advance_workspace_revision(cursor, workspace_gid=workspace_gid, current=workspace,
                patch={"op":"bootstrap_alternate_hierarchy","hierarchy_gid":hierarchy_gid,"fork_run_gid":fork_run_gid,
                       "source_content_hash":source_hash,"node_count":len(ordered)})
            result={"hierarchy_gid":hierarchy_gid,"workspace_gid":workspace_gid,"name":name,"row_version":1,
                    "workspace_row_version":next_version,"status":"active","node_count":len(ordered)}
            self._idempotency_finish(cursor, workspace_gid=workspace_gid, idempotency_key=idempotency_key,
                                     request_hash=request_hash, response=result)
        return result

    def insert_bop_projection(self, *, workspace_gid: str, plan: Mapping[str, Any],
                              expected_workspace_version: int, actor_gid: str,
                              tenant_gid: str, idempotency_key: str) -> dict[str, Any]:
        """Persist one exact Craft-owned BOP skeleton without inventing a fork identity."""
        workspace_gid = _gid(workspace_gid, "workspace_gid")
        tenant_gid, actor_gid = _gid(tenant_gid, "tenant_gid"), _gid(actor_gid, "actor_gid")
        source_version_gid = _gid(plan.get("source_version_gid"), "source_version_gid")
        source_hash = str(plan.get("source_content_hash") or "")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", source_hash):
            raise WorkspaceRepositoryError("bop_projection_hash_invalid")
        hierarchy_name = str(plan.get("hierarchy_name") or "").strip()
        if not hierarchy_name or len(hierarchy_name) > 255:
            raise WorkspaceRepositoryError("hierarchy_name_invalid")
        plan_hash = str(plan.get("plan_hash") or "")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", plan_hash):
            raise WorkspaceRepositoryError("bop_projection_plan_invalid")
        raw_nodes = [dict(item) for item in plan.get("nodes") or []]
        if not raw_nodes or len(raw_nodes) > 10000:
            raise WorkspaceRepositoryError("bop_projection_node_invalid")
        normalized: dict[str, dict[str, Any]] = {}
        for item in raw_nodes:
            source_gid = _gid(item.get("source_gid"), "source_bop_node_gid")
            parent = item.get("parent_source_gid")
            normalized[source_gid] = {"source_gid": source_gid,
                "parent_source_gid": _gid(parent, "source_bop_parent_gid") if parent is not None else None,
                "node_type": str(item.get("node_type") or "")[:32],
                "name": str(item.get("name") or "").strip()[:255],
                "position": int(item.get("position") or 0)}
            if not normalized[source_gid]["node_type"] or not normalized[source_gid]["name"]:
                raise WorkspaceRepositoryError("bop_projection_node_invalid")
        if any(item["parent_source_gid"] not in normalized for item in normalized.values() if item["parent_source_gid"]):
            raise WorkspaceRepositoryError("bop_projection_parent_missing")
        ordered: list[dict[str, Any]] = []
        pending = dict(normalized)
        while pending:
            done = {row["source_gid"] for row in ordered}
            ready = [row for row in pending.values() if row["parent_source_gid"] is None or row["parent_source_gid"] in done]
            if not ready:
                raise WorkspaceRepositoryError("bop_projection_cycle")
            ready.sort(key=lambda row: (row["parent_source_gid"] or "", row["position"], int(row["source_gid"])))
            for item in ready:
                ordered.append(item); pending.pop(item["source_gid"])
        projection_identity = f"craft-bop:{source_version_gid}:{plan.get('line_gid') or 'all'}:{plan.get('fork_depth')}:{source_hash}"
        source_refs = {"model_references": list(plan.get("model_references") or []),
                       "resource_references": list(plan.get("resource_references") or [])}
        hierarchy_gid = str(next_gid())
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            conn.begin()
            workspace = self._lock_owned_workspace(cursor, workspace_gid=workspace_gid,
                tenant_gid=tenant_gid, actor_gid=actor_gid, expected_row_version=expected_workspace_version)
            request_hash, replay = self._idempotency_begin(cursor, workspace_gid=workspace_gid,
                idempotency_key=idempotency_key, request={"op": "insert_bop_projection", "plan_hash": plan_hash})
            if replay is not None:
                return replay
            cursor.execute("SELECT gid FROM workmanship_sim_workspace_hierarchies WHERE workspace_gid=%s AND projection_identity=%s AND removed_at IS NULL FOR UPDATE", (workspace_gid, projection_identity))
            if cursor.fetchone():
                raise WorkspaceRepositoryError("bop_projection_already_inserted")
            cursor.execute("SELECT COALESCE(MAX(sort_order),-1)+1 AS position FROM workmanship_sim_workspace_hierarchies WHERE workspace_gid=%s AND removed_at IS NULL", (workspace_gid,))
            hierarchy_position = int((cursor.fetchone() or {"position": 0})["position"])
            cursor.execute("INSERT INTO workmanship_sim_workspace_hierarchies (gid,workspace_gid,tenant_gid,owner_gid,name,source_bop_version_gid,source_bop_content_hash,source_refs_json,projection_identity,status,sort_order,row_version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'active',%s,1)",
                (hierarchy_gid, workspace_gid, tenant_gid, actor_gid, hierarchy_name,
                 source_version_gid, source_hash, json.dumps(source_refs, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                 projection_identity, hierarchy_position))
            node_map = {item["source_gid"]: str(next_gid()) for item in ordered}
            sibling_positions: dict[str | None, int] = {}
            node_rows = []
            for item in ordered:
                parent_source = item["parent_source_gid"]
                position = sibling_positions.get(parent_source, 0); sibling_positions[parent_source] = position + 1
                node_rows.append((node_map[item["source_gid"]], workspace_gid, tenant_gid, actor_gid,
                                  hierarchy_gid, node_map.get(parent_source), item["node_type"],
                                  item["name"], position, item["source_gid"]))
            node_insert = "INSERT INTO workmanship_sim_workspace_nodes (gid,workspace_gid,tenant_gid,owner_gid,hierarchy_gid,parent_gid,node_type,name,sort_order,source_bop_node_gid,row_version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1)"
            for offset in range(0, len(node_rows), 500):
                cursor.executemany(node_insert, node_rows[offset:offset + 500])
            next_version, cache_hash = self._advance_workspace_revision(cursor, workspace_gid=workspace_gid,
                current=workspace, patch={"op":"insert_bop_projection","hierarchy_gid":hierarchy_gid,
                    "source_version_gid":source_version_gid,"source_content_hash":source_hash,"plan_hash":plan_hash})
            result = {"hierarchy_gid": hierarchy_gid, "workspace_gid": workspace_gid,
                "name": hierarchy_name, "row_version": 1, "workspace_row_version": next_version,
                "status": "active", "node_count": len(ordered)}
            self._idempotency_finish(cursor, workspace_gid=workspace_gid, idempotency_key=idempotency_key,
                                     request_hash=request_hash, response=result)
        return result

    def search_alternate_hierarchies(self, *, workspace_gid: str, tenant_gid: str,
                                     actor_gid: str) -> dict[str, Any]:
        workspace_gid = _gid(workspace_gid, "workspace_gid")
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT h.gid AS hierarchy_gid,h.workspace_gid,h.name,h.source_bop_repository_gid,h.source_bop_version_gid,"
                "h.source_bop_fork_run_gid,h.source_bop_content_hash,h.projection_identity,h.status,h.sort_order,h.row_version "
                "FROM workmanship_sim_workspace_hierarchies h JOIN workmanship_sim_workspaces w ON w.gid=h.workspace_gid "
                "WHERE h.workspace_gid=%s AND h.tenant_gid=%s AND (w.owner_gid=%s OR w.visibility='shared') "
                "AND h.removed_at IS NULL AND w.removed_at IS NULL ORDER BY h.sort_order,h.gid",
                (workspace_gid, _gid(tenant_gid, "tenant_gid"), _gid(actor_gid, "actor_gid")),
            )
            rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            for key in ("hierarchy_gid", "workspace_gid", "source_bop_repository_gid", "source_bop_version_gid", "source_bop_fork_run_gid"):
                if row.get(key) is not None:
                    row[key] = str(row[key])
        return {"items": rows}

    def get_alternate_hierarchy(self, *, hierarchy_gid: str, tenant_gid: str,
                                actor_gid: str) -> dict[str, Any] | None:
        hierarchy_gid = _gid(hierarchy_gid, "hierarchy_gid")
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT h.gid AS hierarchy_gid,h.workspace_gid,h.name,h.status,h.projection_identity,h.source_refs_json,h.row_version "
                "FROM workmanship_sim_workspace_hierarchies h JOIN workmanship_sim_workspaces w ON w.gid=h.workspace_gid "
                "WHERE h.gid=%s AND h.tenant_gid=%s AND (w.owner_gid=%s OR w.visibility='shared') "
                "AND h.removed_at IS NULL AND w.removed_at IS NULL",
                (hierarchy_gid, _gid(tenant_gid, "tenant_gid"), _gid(actor_gid, "actor_gid")),
            )
            hierarchy = cursor.fetchone()
            if not hierarchy:
                return None
            cursor.execute(
                "SELECT gid AS node_gid,workspace_gid,hierarchy_gid,parent_gid,node_type,name,sort_order,"
                "source_bop_node_gid,row_version FROM workmanship_sim_workspace_nodes "
                "WHERE hierarchy_gid=%s AND tenant_gid=%s AND removed_at IS NULL "
                "ORDER BY parent_gid,sort_order,gid",
                (hierarchy_gid, _gid(tenant_gid, "tenant_gid")),
            )
            nodes = [dict(row) for row in cursor.fetchall()]
            cursor.execute(
                "SELECT gid AS placement_gid,hierarchy_gid,workspace_gid,target_node_gid,parent_placement_gid,source_kind,"
                "source_ref_json,transform_json,display_name,sort_order,row_version FROM workmanship_sim_workspace_placements "
                "WHERE hierarchy_gid=%s AND tenant_gid=%s AND removed_at IS NULL ORDER BY parent_placement_gid,sort_order,gid",
                (hierarchy_gid, _gid(tenant_gid, "tenant_gid")),
            )
            placements = [dict(row) for row in cursor.fetchall()]
        result = dict(hierarchy)
        for key in ("hierarchy_gid", "workspace_gid"):
            result[key] = str(result[key])
        raw_refs = result.pop("source_refs_json", None)
        result["source_refs"] = (json.loads(raw_refs) if isinstance(raw_refs, str) else dict(raw_refs or {}))
        result["source_refs"].setdefault("model_references", [])
        result["source_refs"].setdefault("resource_references", [])
        for row in nodes:
            for key in ("node_gid", "workspace_gid", "hierarchy_gid", "parent_gid", "source_bop_node_gid"):
                if row.get(key) is not None:
                    row[key] = str(row[key])
        for row in placements:
            for key in ("placement_gid", "hierarchy_gid", "workspace_gid", "target_node_gid", "parent_placement_gid"):
                if row.get(key) is not None:
                    row[key] = str(row[key])
            for key in ("source_ref_json", "transform_json"):
                if isinstance(row.get(key), str):
                    row[key.removesuffix("_json")] = json.loads(row.pop(key))
                else:
                    row[key.removesuffix("_json")] = row.pop(key)
        result["nodes"] = nodes
        result["placements"] = placements
        return result

    def can_read_placement(self, placement_gid: str, *, tenant_gid: str, actor_gid: str) -> bool:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT 1 FROM workmanship_sim_workspace_placements p JOIN workmanship_sim_workspaces w ON w.gid=p.workspace_gid WHERE p.gid=%s AND p.tenant_gid=%s AND (w.owner_gid=%s OR w.visibility='shared') AND p.removed_at IS NULL AND w.removed_at IS NULL", (_gid(placement_gid,"placement_gid"),_gid(tenant_gid,"tenant_gid"),_gid(actor_gid,"actor_gid")))
            return cursor.fetchone() is not None

    def add_placement(self, *, hierarchy_gid: str, target_node_gid: str,
                      parent_placement_gid: str | None, source_kind: str,
                      source_ref: Mapping[str, str], transform: list[float],
                      expected_hierarchy_version: int, actor_gid: str,
                      tenant_gid: str, display_name: str = "", idempotency_key: str = "") -> dict[str, Any]:
        hierarchy_gid = _gid(hierarchy_gid, "hierarchy_gid")
        target_node_gid = _gid(target_node_gid, "target_node_gid")
        tenant_gid, actor_gid = _gid(tenant_gid, "tenant_gid"), _gid(actor_gid, "actor_gid")
        if len(transform) != 16 or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in transform):
            raise WorkspaceRepositoryError("placement_transform_invalid")
        placement_gid = str(next_gid())
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT h.row_version,h.workspace_gid,w.row_version AS workspace_row_version,w.cache_revision_hash "
                "FROM workmanship_sim_workspace_hierarchies h JOIN workmanship_sim_workspaces w ON w.gid=h.workspace_gid "
                "WHERE h.gid=%s AND h.tenant_gid=%s AND h.owner_gid=%s AND h.removed_at IS NULL "
                "AND w.removed_at IS NULL FOR UPDATE",
                (hierarchy_gid, tenant_gid, actor_gid),
            )
            hierarchy = cursor.fetchone()
            if not hierarchy:
                raise WorkspaceRepositoryError("hierarchy_not_found")
            if int(hierarchy["row_version"]) != expected_hierarchy_version:
                raise WorkspaceRepositoryError("version_conflict")
            workspace_gid = str(hierarchy["workspace_gid"])
            request_hash, replay = self._idempotency_begin(cursor, workspace_gid=workspace_gid,
                idempotency_key=idempotency_key, request={"op": "add_placement", "hierarchy_gid": hierarchy_gid,
                    "target_node_gid": target_node_gid, "parent_placement_gid": parent_placement_gid,
                    "source_kind": source_kind, "source_ref": dict(source_ref), "transform": transform,
                    "display_name": display_name})
            if replay is not None:
                return replay
            cursor.execute(
                "SELECT 1 FROM workmanship_sim_workspace_nodes "
                "WHERE gid=%s AND hierarchy_gid=%s AND workspace_gid=%s AND tenant_gid=%s "
                "AND removed_at IS NULL FOR UPDATE",
                (target_node_gid, hierarchy_gid, workspace_gid, tenant_gid),
            )
            if not cursor.fetchone():
                raise WorkspaceRepositoryError("target_node_not_found")
            canonical_source_ref = dict(source_ref)
            if source_kind in {"jt", "plmxml", "vm_occurrence"}:
                document_gid = _gid(source_ref.get("document_gid"), "document_gid")
                cursor.execute(
                    "SELECT gid AS document_gid,artifact_ref_json,content_sha256,source_identity_hash,"
                    "connector_device_id,portability FROM workmanship_sim_vm_documents "
                    "WHERE gid=%s AND workspace_gid=%s AND tenant_gid=%s AND status='active' "
                    "AND removed_at IS NULL FOR UPDATE",
                    (document_gid, workspace_gid, tenant_gid),
                )
                document = cursor.fetchone()
                if not document:
                    raise WorkspaceRepositoryError("source_document_not_found")
                artifact_ref = document.get("artifact_ref_json") or {}
                if isinstance(artifact_ref, str):
                    artifact_ref = json.loads(artifact_ref)
                canonical_source_ref = {
                    "document_gid": str(document["document_gid"]),
                    "content_sha256": "sha256:" + str(document["content_sha256"]).removeprefix("sha256:"),
                    "source_identity_hash": "sha256:" + str(document["source_identity_hash"]).removeprefix("sha256:"),
                }
                if artifact_ref.get("artifact_id"):
                    canonical_source_ref["artifact_id"] = str(artifact_ref["artifact_id"])
                if artifact_ref.get("version") is not None:
                    canonical_source_ref["artifact_version"] = str(artifact_ref["version"])
                if document.get("connector_device_id"):
                    canonical_source_ref["connector_device_id"] = str(document["connector_device_id"])
                if source_ref.get("node_key"):
                    node_key = str(source_ref["node_key"])
                    if len(node_key) > 255:
                        raise WorkspaceRepositoryError("model_node_key_invalid")
                    canonical_source_ref["node_key"] = node_key
                    if source_ref.get("occurrence_id"):
                        canonical_source_ref["occurrence_id"] = str(source_ref["occurrence_id"])
                if source_kind == "vm_occurrence":
                    occurrence_gid = _gid(source_ref.get("occurrence_gid"), "occurrence_gid")
                    canonical_source_ref["occurrence_gid"] = occurrence_gid
            parent_gid = _gid(parent_placement_gid, "parent_placement_gid") if parent_placement_gid else None
            if parent_gid is not None:
                cursor.execute(
                    "SELECT 1 FROM workmanship_sim_workspace_placements "
                    "WHERE gid=%s AND hierarchy_gid=%s AND workspace_gid=%s AND tenant_gid=%s "
                    "AND removed_at IS NULL FOR UPDATE",
                    (parent_gid, hierarchy_gid, workspace_gid, tenant_gid),
                )
                if not cursor.fetchone():
                    raise WorkspaceRepositoryError("parent_placement_not_found")
            cursor.execute(
                "SELECT COALESCE(MAX(sort_order),-1)+1 AS position FROM workmanship_sim_workspace_placements "
                "WHERE hierarchy_gid=%s AND parent_placement_gid<=>%s AND removed_at IS NULL",
                (hierarchy_gid, parent_gid),
            )
            position_row = cursor.fetchone() or {"position": 0}
            cursor.execute(
                "INSERT INTO workmanship_sim_workspace_placements "
                "(gid,hierarchy_gid,workspace_gid,tenant_gid,owner_gid,target_node_gid,parent_placement_gid,source_kind,"
                "source_ref_json,transform_json,display_name,sort_order,row_version) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1)",
                (placement_gid, hierarchy_gid, workspace_gid, tenant_gid, actor_gid, target_node_gid,
                 parent_gid,
                 str(source_kind), json.dumps(canonical_source_ref, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                 json.dumps(transform, separators=(",", ":")), str(display_name or ""),
                 int(position_row.get("position") or 0)),
            )
            cursor.execute(
                "UPDATE workmanship_sim_workspace_hierarchies SET row_version=row_version+1,updated_at=NOW(6) "
                "WHERE gid=%s AND row_version=%s",
                (hierarchy_gid, expected_hierarchy_version),
            )
            self._advance_workspace_revision(
                cursor, workspace_gid=workspace_gid,
                current={"row_version": hierarchy["workspace_row_version"],
                         "cache_revision_hash": hierarchy.get("cache_revision_hash") or _EMPTY_CACHE_REVISION_HASH},
                patch={"op": "add_placement", "placement_gid": placement_gid, "hierarchy_gid": hierarchy_gid,
                       "source_kind": str(source_kind), "source_ref": dict(source_ref)},
            )
            result = {"placement_gid": placement_gid, "hierarchy_gid": hierarchy_gid,
                "workspace_gid": workspace_gid, "row_version": 1,
                "hierarchy_row_version": expected_hierarchy_version + 1}
            self._idempotency_finish(cursor, workspace_gid=workspace_gid, idempotency_key=idempotency_key,
                                     request_hash=request_hash, response=result)
        return result

    def mutate_alternate_hierarchy(self, *, hierarchy_gid: str, expected_hierarchy_version: int,
                                   operation: str, values: Mapping[str, Any], actor_gid: str,
                                   tenant_gid: str, idempotency_key: str) -> dict[str, Any]:
        if operation not in {"update", "archive"}: raise WorkspaceRepositoryError("hierarchy_operation_invalid")
        hierarchy_gid = _gid(hierarchy_gid, "hierarchy_gid"); tenant_gid = _gid(tenant_gid, "tenant_gid"); actor_gid = _gid(actor_gid, "actor_gid")
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT h.row_version,h.workspace_gid,w.row_version AS workspace_row_version,w.cache_revision_hash FROM workmanship_sim_workspace_hierarchies h JOIN workmanship_sim_workspaces w ON w.gid=h.workspace_gid WHERE h.gid=%s AND h.tenant_gid=%s AND h.owner_gid=%s AND h.removed_at IS NULL AND w.removed_at IS NULL FOR UPDATE", (hierarchy_gid, tenant_gid, actor_gid))
            row = cursor.fetchone()
            if not row: raise WorkspaceRepositoryError("hierarchy_not_found")
            if int(row["row_version"]) != expected_hierarchy_version: raise WorkspaceRepositoryError("version_conflict")
            workspace_gid = str(row["workspace_gid"])
            request_hash, replay = self._idempotency_begin(cursor, workspace_gid=workspace_gid, idempotency_key=idempotency_key,
                request={"op": operation, "hierarchy_gid": hierarchy_gid, "values": dict(values)})
            if replay is not None: return replay
            if operation == "update":
                name = str(values.get("name") or "").strip()
                if not name or len(name) > 255: raise WorkspaceRepositoryError("hierarchy_name_invalid")
                cursor.execute("UPDATE workmanship_sim_workspace_hierarchies SET name=%s,row_version=row_version+1,updated_at=NOW(6) WHERE gid=%s AND row_version=%s", (name, hierarchy_gid, expected_hierarchy_version))
            else:
                cursor.execute("UPDATE workmanship_sim_workspace_hierarchies SET status='archived',removed_at=NOW(6),row_version=row_version+1,updated_at=NOW(6) WHERE gid=%s AND row_version=%s", (hierarchy_gid, expected_hierarchy_version))
            next_workspace, cache_hash = self._advance_workspace_revision(cursor, workspace_gid=workspace_gid,
                current={"row_version": row["workspace_row_version"], "cache_revision_hash": row.get("cache_revision_hash") or _EMPTY_CACHE_REVISION_HASH},
                patch={"op": f"{operation}_alternate_hierarchy", "hierarchy_gid": hierarchy_gid, **dict(values)})
            result={"hierarchy_gid":hierarchy_gid,"workspace_gid":workspace_gid,"row_version":expected_hierarchy_version+1,"workspace_row_version":next_workspace,"cache_revision_hash":cache_hash,"operation":operation}
            self._idempotency_finish(cursor,workspace_gid=workspace_gid,idempotency_key=idempotency_key,request_hash=request_hash,response=result)
        return result

    def mutate_placement(self, *, placement_gid: str, expected_hierarchy_version: int,
                         operation: str, values: Mapping[str, Any], actor_gid: str,
                         tenant_gid: str, idempotency_key: str) -> dict[str, Any]:
        if operation not in {"move", "remove"}: raise WorkspaceRepositoryError("placement_operation_invalid")
        placement_gid=_gid(placement_gid,"placement_gid");tenant_gid=_gid(tenant_gid,"tenant_gid");actor_gid=_gid(actor_gid,"actor_gid")
        with get_simulation_conn() as conn,conn.cursor() as cursor:
            cursor.execute("SELECT p.hierarchy_gid,p.workspace_gid,h.row_version,w.row_version AS workspace_row_version,w.cache_revision_hash FROM workmanship_sim_workspace_placements p JOIN workmanship_sim_workspace_hierarchies h ON h.gid=p.hierarchy_gid JOIN workmanship_sim_workspaces w ON w.gid=p.workspace_gid WHERE p.gid=%s AND p.tenant_gid=%s AND p.owner_gid=%s AND p.removed_at IS NULL AND h.removed_at IS NULL AND w.removed_at IS NULL FOR UPDATE",(placement_gid,tenant_gid,actor_gid));row=cursor.fetchone()
            if not row: raise WorkspaceRepositoryError("placement_not_found")
            if int(row["row_version"])!=expected_hierarchy_version: raise WorkspaceRepositoryError("version_conflict")
            hierarchy_gid,workspace_gid=str(row["hierarchy_gid"]),str(row["workspace_gid"])
            request_hash,replay=self._idempotency_begin(cursor,workspace_gid=workspace_gid,idempotency_key=idempotency_key,request={"op":operation,"placement_gid":placement_gid,"values":dict(values)})
            if replay is not None:return replay
            cursor.execute("SELECT gid,parent_placement_gid FROM workmanship_sim_workspace_placements WHERE hierarchy_gid=%s AND workspace_gid=%s AND tenant_gid=%s AND removed_at IS NULL FOR UPDATE",(hierarchy_gid,workspace_gid,tenant_gid));tree=[dict(item) for item in cursor.fetchall()]
            if operation=="move":
                parent=values.get("parent_placement_gid");parent_gid=_gid(parent,"parent_placement_gid") if parent else None
                parents={str(item["gid"]):str(item["parent_placement_gid"]) if item.get("parent_placement_gid") is not None else None for item in tree}
                cursor_id=parent_gid
                while cursor_id is not None:
                    if cursor_id==placement_gid:raise WorkspaceRepositoryError("placement_cycle")
                    cursor_id=parents.get(cursor_id)
                if parent_gid is not None and parent_gid not in parents:raise WorkspaceRepositoryError("parent_placement_not_found")
                cursor.execute("SELECT COALESCE(MAX(sort_order),-1)+1 AS position FROM workmanship_sim_workspace_placements WHERE hierarchy_gid=%s AND parent_placement_gid<=>%s AND removed_at IS NULL",(hierarchy_gid,parent_gid));position=int((cursor.fetchone() or {"position":0})["position"] or 0)
                cursor.execute("UPDATE workmanship_sim_workspace_placements SET parent_placement_gid=%s,sort_order=%s,row_version=row_version+1,updated_at=NOW(6) WHERE gid=%s AND removed_at IS NULL",(parent_gid,position,placement_gid))
            else:
                removed={placement_gid};changed=True
                while changed:
                    before=len(removed);removed.update(str(item["gid"]) for item in tree if item.get("parent_placement_gid") is not None and str(item["parent_placement_gid"]) in removed);changed=len(removed)!=before
                marks=",".join(["%s"]*len(removed));cursor.execute(f"UPDATE workmanship_sim_workspace_placements SET removed_at=NOW(6),row_version=row_version+1,updated_at=NOW(6) WHERE gid IN ({marks})",tuple(sorted(removed)))
            cursor.execute("UPDATE workmanship_sim_workspace_hierarchies SET row_version=row_version+1,updated_at=NOW(6) WHERE gid=%s AND row_version=%s",(hierarchy_gid,expected_hierarchy_version))
            next_workspace,cache_hash=self._advance_workspace_revision(cursor,workspace_gid=workspace_gid,current={"row_version":row["workspace_row_version"],"cache_revision_hash":row.get("cache_revision_hash") or _EMPTY_CACHE_REVISION_HASH},patch={"op":f"{operation}_placement","placement_gid":placement_gid,**dict(values)})
            result={"placement_gid":placement_gid,"hierarchy_gid":hierarchy_gid,"workspace_gid":workspace_gid,"hierarchy_row_version":expected_hierarchy_version+1,"workspace_row_version":next_workspace,"cache_revision_hash":cache_hash,"operation":operation}
            self._idempotency_finish(cursor,workspace_gid=workspace_gid,idempotency_key=idempotency_key,request_hash=request_hash,response=result)
        return result

    def save_materialization_verification(self, *, workspace_gid: str, version_gid: str,
                                          state: str, manifest_hash: str, report: Mapping[str, Any],
                                          tenant_gid: str, actor_gid: str,
                                          runtime_package_artifact_ref: Mapping[str, Any] | None = None,
                                          connector_device_id: str | None = None) -> dict[str, Any]:
        if state not in {"pending", "verified", "failed", "outcome_unknown", "stale"}:
            raise WorkspaceRepositoryError("verification_state_invalid")
        verification_gid = str(next_gid())
        manifest_body = _sha256_body(manifest_hash, "manifest_hash")
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM workmanship_sim_workspace_versions v JOIN workmanship_sim_workspaces w ON w.gid=v.workspace_gid "
                "WHERE w.gid=%s AND v.gid=%s AND w.tenant_gid=%s AND (w.owner_gid=%s OR w.visibility='shared') "
                "AND w.removed_at IS NULL AND v.removed_at IS NULL FOR UPDATE",
                (_gid(workspace_gid, "workspace_gid"), _gid(version_gid, "version_gid"),
                 _gid(tenant_gid, "tenant_gid"), _gid(actor_gid, "actor_gid")),
            )
            if not cursor.fetchone():
                raise WorkspaceRepositoryError("workspace_version_not_found")
            cursor.execute(
                "INSERT INTO workmanship_sim_materialization_verifications "
                "(gid,workspace_gid,version_gid,tenant_gid,actor_gid,state,manifest_hash,runtime_package_artifact_ref_json,"
                "connector_device_id,report_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE state=VALUES(state),actor_gid=VALUES(actor_gid),"
                "runtime_package_artifact_ref_json=VALUES(runtime_package_artifact_ref_json),connector_device_id=VALUES(connector_device_id),"
                "report_json=VALUES(report_json),updated_at=NOW(6)",
                (verification_gid, workspace_gid, version_gid, tenant_gid, actor_gid, state, manifest_body,
                 json.dumps(dict(runtime_package_artifact_ref), ensure_ascii=False, sort_keys=True, separators=(",", ":")) if runtime_package_artifact_ref else None,
                 str(connector_device_id or "") or None,
                 json.dumps(dict(report), ensure_ascii=False, sort_keys=True, separators=(",", ":"))),
            )
            cursor.execute(
                "SELECT gid FROM workmanship_sim_materialization_verifications "
                "WHERE tenant_gid=%s AND version_gid=%s AND manifest_hash=%s AND actor_gid=%s",
                (tenant_gid, version_gid, manifest_body, actor_gid),
            )
            stored = cursor.fetchone()
            if not stored:
                raise WorkspaceRepositoryError("runtime_verification_not_found")
            verification_gid = str(stored["gid"])
        return {"verification_gid": verification_gid, "workspace_gid": str(workspace_gid),
                "version_gid": str(version_gid), "state": state, "manifest_hash": "sha256:" + manifest_body,
                "report": dict(report)}

    def save_runtime_package_projection(self, *, workspace_gid: str, version_gid: str,
                                        connector_plan_id: str, manifest_hash: str,
                                        runtime_package_artifact_ref: Mapping[str, Any],
                                        connector_device_id: str, report: Mapping[str, Any],
                                        tenant_gid: str, actor_gid: str) -> dict[str, Any]:
        connector_plan_id = str(connector_plan_id or "")
        if not connector_plan_id or len(connector_plan_id) > 256:
            raise WorkspaceRepositoryError("connector_plan_id_invalid")
        workspace_gid, version_gid = _gid(workspace_gid, "workspace_gid"), _gid(version_gid, "version_gid")
        tenant_gid, actor_gid = _gid(tenant_gid, "tenant_gid"), _gid(actor_gid, "actor_gid")
        manifest_body = _sha256_body(manifest_hash, "manifest_hash")
        projection_gid = str(next_gid())
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM workmanship_sim_workspace_versions v JOIN workmanship_sim_workspaces w ON w.gid=v.workspace_gid "
                "WHERE w.gid=%s AND v.gid=%s AND w.tenant_gid=%s AND (w.owner_gid=%s OR w.visibility='shared') "
                "AND w.removed_at IS NULL AND v.removed_at IS NULL FOR UPDATE",
                (workspace_gid, version_gid, tenant_gid, actor_gid),
            )
            if not cursor.fetchone():
                raise WorkspaceRepositoryError("workspace_version_not_found")
            cursor.execute(
                "SELECT gid,workspace_gid,version_gid,tenant_gid,actor_gid,state,manifest_hash,"
                "runtime_package_artifact_ref_json,connector_device_id FROM workmanship_sim_runtime_package_projections "
                "WHERE connector_plan_id=%s FOR UPDATE",
                (connector_plan_id,),
            )
            replay = cursor.fetchone()
            if replay:
                replay_ref = replay.get("runtime_package_artifact_ref_json")
                if isinstance(replay_ref, str):
                    replay_ref = json.loads(replay_ref)
                exact = (
                    str(replay["workspace_gid"]) == workspace_gid
                    and str(replay["version_gid"]) == version_gid
                    and str(replay["tenant_gid"]) == tenant_gid
                    and str(replay["actor_gid"]) == actor_gid
                    and str(replay["manifest_hash"]) == manifest_body
                    and str(replay.get("connector_device_id") or "") == str(connector_device_id)
                    and isinstance(replay_ref, Mapping)
                    and all(
                        str(replay_ref.get(key) or "") == str(runtime_package_artifact_ref.get(key) or "")
                        for key in ("sha256", "byte_size", "media_type")
                    )
                )
                if not exact:
                    raise WorkspaceRepositoryError("connector_plan_idempotency_conflict")
                return {"projection_gid": str(replay["gid"]), "workspace_gid": workspace_gid,
                        "version_gid": version_gid, "connector_plan_id": connector_plan_id,
                        "state": str(replay["state"]), "manifest_hash": "sha256:" + manifest_body}
            cursor.execute(
                "INSERT INTO workmanship_sim_runtime_package_projections "
                "(gid,workspace_gid,version_gid,tenant_gid,actor_gid,connector_plan_id,state,manifest_hash,"
                "runtime_package_artifact_ref_json,connector_device_id,report_json) VALUES (%s,%s,%s,%s,%s,%s,'pending',%s,%s,%s,%s)",
                (projection_gid, workspace_gid, version_gid, tenant_gid, actor_gid, connector_plan_id, manifest_body,
                 json.dumps(dict(runtime_package_artifact_ref), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                 str(connector_device_id), json.dumps(dict(report), ensure_ascii=False, sort_keys=True, separators=(",", ":"))),
            )
        return {"projection_gid": projection_gid, "workspace_gid": workspace_gid, "version_gid": version_gid,
                "connector_plan_id": connector_plan_id, "state": "pending", "manifest_hash": "sha256:" + manifest_body}

    def apply_runtime_package_outcome(self, *, connector_plan_id: str, plan, outcome,
                                      tenant_gid: str, actor_gid: str) -> dict[str, Any]:
        """Project one signed App runtime outcome without claiming semantic verification."""
        connector_plan_id = str(connector_plan_id or "")
        if not connector_plan_id or len(connector_plan_id) > 256:
            raise WorkspaceRepositoryError("connector_plan_id_invalid")
        if plan.plan_id != connector_plan_id or getattr(plan, "capability_id", "") != "simulation.environment.runtime_package.open.request":
            raise WorkspaceRepositoryError("plan_outcome_invalid")
        tree = None
        if outcome.overall_status in {"outcome_unknown", "manual_review_required"}:
            state = "outcome_unknown"
        elif outcome.overall_status != "succeeded":
            state = "failed"
        else:
            tree_steps = [item for item in outcome.steps if item.step_id == "step-00002"]
            tree = tree_steps[0].result if len(tree_steps) == 1 and tree_steps[0].status == "succeeded" else None
            state = "read_back" if isinstance(tree, Mapping) and isinstance(tree.get("nodes"), list) else "failed"
        report = {
            "connector_plan_id": connector_plan_id,
            "outcome_status": outcome.overall_status,
            "readback": tree if outcome.overall_status == "succeeded" and isinstance(tree, Mapping) else None,
            "semantic_verification": "pending" if state == "read_back" else "not_available",
        }
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT gid,workspace_gid,version_gid,manifest_hash FROM workmanship_sim_runtime_package_projections "
                "WHERE connector_plan_id=%s AND tenant_gid=%s AND actor_gid=%s FOR UPDATE",
                (connector_plan_id, _gid(tenant_gid, "tenant_gid"), _gid(actor_gid, "actor_gid")),
            )
            row = cursor.fetchone()
            if not row:
                raise WorkspaceRepositoryError("runtime_verification_not_found")
            cursor.execute(
                "UPDATE workmanship_sim_runtime_package_projections SET state=%s,report_json=%s,updated_at=NOW(6) "
                "WHERE gid=%s AND connector_plan_id=%s",
                (state, json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                 row["gid"], connector_plan_id),
            )
        return {"verification_gid": str(row["gid"]), "workspace_gid": str(row["workspace_gid"]),
                "version_gid": str(row["version_gid"]), "state": state,
                "manifest_hash": "sha256:" + str(row["manifest_hash"]), "report": report}

    def import_environment_projection(self, *, workspace_gid: str, expected_workspace_version: int,
                                      display_name: str, document_role: str = "primary",
                                      artifact_ref: Mapping[str, Any], projection,
                                      resolved_dependencies: Mapping[str, Mapping[str, Any]],
                                      tenant_gid: str, actor_gid: str, idempotency_key: str) -> dict[str, Any]:
        """Persist one parsed PLMXML projection as one atomic draft mutation."""
        workspace_gid = _gid(workspace_gid, "workspace_gid")
        tenant_gid, actor_gid = _gid(tenant_gid, "tenant_gid"), _gid(actor_gid, "actor_gid")
        if not idempotency_key or len(idempotency_key) > 191:
            raise WorkspaceRepositoryError("idempotency_key_invalid")
        artifact_hash = _sha256_body(artifact_ref.get("sha256"), "artifact_sha256")
        if document_role not in {"auto", "primary", "inserted"}:
            raise WorkspaceRepositoryError("model_document_role_invalid")
        request_hash = hashlib.sha256(json.dumps({"artifact": dict(artifact_ref), "name": display_name, "role": document_role}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        document_gid = str(next_gid())
        hierarchy_gids: list[str] = []
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            workspace = self._lock_owned_workspace(cursor, workspace_gid=workspace_gid, tenant_gid=tenant_gid,
                                                   actor_gid=actor_gid, expected_row_version=expected_workspace_version)
            cursor.execute("SELECT request_hash,response_json FROM workmanship_sim_workspace_idempotency WHERE workspace_gid=%s AND idempotency_key=%s FOR UPDATE", (workspace_gid, idempotency_key))
            replay = cursor.fetchone()
            if replay:
                if str(replay["request_hash"]) != request_hash:
                    raise WorkspaceRepositoryError("idempotency_conflict")
                value = replay["response_json"]
                return json.loads(value) if isinstance(value, str) else dict(value)
            cursor.execute("SELECT gid FROM workmanship_sim_vm_documents WHERE workspace_gid=%s AND primary_slot=1 AND removed_at IS NULL FOR UPDATE", (workspace_gid,))
            primary = cursor.fetchone()
            if document_role == "auto":
                document_role = "inserted" if primary else "primary"
            elif primary and document_role == "primary":
                raise WorkspaceRepositoryError("primary_model_document_exists")
            cursor.execute(
                "INSERT INTO workmanship_sim_vm_documents (gid,workspace_gid,tenant_gid,owner_gid,document_role,primary_slot,display_name,media_type,artifact_ref_json,content_sha256,portability,sort_order,source_kind,source_identity_hash,status,row_version) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,'application/plmxml+xml',%s,%s,'portable',0,'artifact',%s,'active',1)",
                (document_gid, workspace_gid, tenant_gid, actor_gid, document_role,
                 1 if document_role == "primary" else None, display_name,
                 json.dumps(dict(artifact_ref), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                 artifact_hash, artifact_hash),
            )
            resolved = (item for item in projection.dependencies if item.location in resolved_dependencies)
            for order, dependency in enumerate(resolved, start=1):
                dependency_gid = str(next_gid())
                dependency_ref = dict(resolved_dependencies.get(dependency.location) or {})
                dependency_hash = _sha256_body(dependency_ref.get("sha256"), "dependency_artifact_sha256")
                source_hash = _dependency_source_identity(dependency_hash, dependency.location)
                cursor.execute(
                    "INSERT INTO workmanship_sim_vm_documents (gid,workspace_gid,tenant_gid,owner_gid,document_role,primary_slot,display_name,media_type,artifact_ref_json,content_sha256,portability,sort_order,source_kind,source_identity_hash,status,row_version) "
                    "VALUES (%s,%s,%s,%s,'inserted',NULL,%s,%s,%s,%s,'portable',%s,'artifact',%s,'active',1)",
                    (dependency_gid, workspace_gid, tenant_gid, actor_gid, dependency.location,
                     dependency.media_type,
                     json.dumps(dependency_ref, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                     dependency_hash, order, source_hash),
                )
            for hierarchy_order, hierarchy in enumerate(projection.hierarchies):
                hierarchy_gid = str(next_gid()); hierarchy_gids.append(hierarchy_gid)
                cursor.execute(
                    "INSERT INTO workmanship_sim_workspace_hierarchies (gid,workspace_gid,tenant_gid,owner_gid,name,projection_identity,status,sort_order,row_version) "
                    "VALUES (%s,%s,%s,%s,%s,%s,'active',%s,1)",
                    (hierarchy_gid, workspace_gid, tenant_gid, actor_gid, hierarchy.name,
                     hierarchy.projection_identity, hierarchy_order),
                )
                placement_ids = {item.projection_identity: str(next_gid()) for item in hierarchy.placements}
                for placement_order, placement in enumerate(hierarchy.placements):
                    cursor.execute(
                        "INSERT INTO workmanship_sim_workspace_placements (gid,hierarchy_gid,workspace_gid,tenant_gid,owner_gid,target_node_gid,parent_placement_gid,source_kind,source_ref_json,transform_json,display_name,sort_order,row_version) "
                        "VALUES (%s,%s,%s,%s,%s,NULL,%s,'vm_occurrence',%s,%s,%s,%s,1)",
                        (placement_ids[placement.projection_identity], hierarchy_gid, workspace_gid, tenant_gid, actor_gid,
                         placement_ids.get(placement.parent_identity),
                         json.dumps({"projection_identity": placement.projection_identity, "stable_identity": placement.stable_identity}, sort_keys=True, separators=(",", ":")),
                         json.dumps([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1], separators=(",", ":")),
                         placement.name, placement_order),
                    )
            next_version, cache_hash = self._advance_workspace_revision(cursor, workspace_gid=workspace_gid, current=workspace,
                patch={"op": "import_environment_plmxml", "document_gid": document_gid, "document_role": document_role, "content_sha256": artifact_hash,
                       "hierarchy_gids": hierarchy_gids})
            result = {"workspace_gid": workspace_gid, "document_gid": document_gid,
                      "hierarchy_gids": hierarchy_gids, "workspace_row_version": next_version,
                      "cache_revision_hash": cache_hash}
            cursor.execute("INSERT INTO workmanship_sim_workspace_idempotency (workspace_gid,idempotency_key,request_hash,response_json,expires_at) VALUES (%s,%s,%s,%s,DATE_ADD(NOW(6),INTERVAL 24 HOUR))", (workspace_gid, idempotency_key, request_hash, json.dumps(result, separators=(",", ":"))))
        return result

    def restore_environment_projection(self, *, name: str, display_name: str,
                                       artifact_ref: Mapping[str, Any], projection,
                                       resolved_dependencies: Mapping[str, Mapping[str, Any]],
                                       tenant_gid: str, actor_gid: str,
                                       idempotency_key: str) -> dict[str, Any]:
        """Create and populate one private draft environment in one transaction."""
        name, display_name = str(name or "").strip(), str(display_name or "").strip()
        if not name or len(name) > 255 or not display_name or len(display_name) > 255:
            raise WorkspaceRepositoryError("workspace_name_invalid")
        if not idempotency_key or len(idempotency_key) > 191:
            raise WorkspaceRepositoryError("idempotency_key_invalid")
        tenant_gid, actor_gid = _gid(tenant_gid, "tenant_gid"), _gid(actor_gid, "actor_gid")
        artifact_hash = _sha256_body(artifact_ref.get("sha256"), "artifact_sha256")
        request_hash = hashlib.sha256(json.dumps({
            "artifact_ref": dict(artifact_ref), "display_name": display_name, "name": name,
            "semantic_hash": projection.original_sha256,
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        workspace_gid, version_gid, document_gid, request_gid = (
            str(next_gid()), str(next_gid()), str(next_gid()), str(next_gid())
        )
        hierarchy_gids: list[str] = []
        create_patch = {"op": "restore_from_plmxml", "workspace_gid": workspace_gid,
                        "version_gid": version_gid, "artifact_sha256": artifact_hash}
        initial_hash = next_cache_revision_hash(_EMPTY_CACHE_REVISION_HASH, create_patch, 1)
        restore_patch = {"op": "restore_environment_plmxml", "document_gid": document_gid,
                         "content_sha256": artifact_hash}
        cache_hash = next_cache_revision_hash(initial_hash, restore_patch, 2)
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT request_hash,response_json FROM workmanship_sim_plmxml_restore_requests "
                "WHERE tenant_gid=%s AND actor_gid=%s AND idempotency_key=%s FOR UPDATE",
                (tenant_gid, actor_gid, idempotency_key),
            )
            replay = cursor.fetchone()
            if replay:
                if str(replay["request_hash"]) != request_hash:
                    raise WorkspaceRepositoryError("idempotency_conflict")
                value = replay["response_json"]
                return json.loads(value) if isinstance(value, str) else dict(value)
            cursor.execute(
                "INSERT INTO workmanship_sim_workspaces "
                "(gid,tenant_gid,owner_gid,name,review_type,version_label,status,visibility,primary_project_gid,cache_revision_hash,row_version) "
                "VALUES (%s,%s,%s,%s,'other','V1','active','private',NULL,%s,2)",
                (workspace_gid, tenant_gid, actor_gid, name, cache_hash),
            )
            cursor.execute(
                "INSERT INTO workmanship_sim_workspace_versions "
                "(gid,workspace_gid,tenant_gid,owner_gid,sequence,status,row_version) "
                "VALUES (%s,%s,%s,%s,1,'draft',1)",
                (version_gid, workspace_gid, tenant_gid, actor_gid),
            )
            cursor.execute(
                "INSERT INTO workmanship_sim_workspace_heads (workspace_gid,version_gid,row_version) VALUES (%s,%s,1)",
                (workspace_gid, version_gid),
            )
            cursor.execute(
                "INSERT INTO workmanship_sim_vm_documents "
                "(gid,workspace_gid,tenant_gid,owner_gid,document_role,primary_slot,display_name,media_type,artifact_ref_json,content_sha256,portability,sort_order,source_kind,source_identity_hash,status,row_version) "
                "VALUES (%s,%s,%s,%s,'primary',1,%s,'application/plmxml+xml',%s,%s,'portable',0,'artifact',%s,'active',1)",
                (document_gid, workspace_gid, tenant_gid, actor_gid, display_name,
                 json.dumps(dict(artifact_ref), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                 artifact_hash, artifact_hash),
            )
            resolved = (item for item in projection.dependencies if item.location in resolved_dependencies)
            for order, dependency in enumerate(resolved, start=1):
                dependency_gid = str(next_gid())
                dependency_ref = dict(resolved_dependencies.get(dependency.location) or {})
                dependency_hash = _sha256_body(dependency_ref.get("sha256"), "dependency_artifact_sha256")
                source_hash = _dependency_source_identity(dependency_hash, dependency.location)
                cursor.execute(
                    "INSERT INTO workmanship_sim_vm_documents "
                    "(gid,workspace_gid,tenant_gid,owner_gid,document_role,primary_slot,display_name,media_type,artifact_ref_json,content_sha256,portability,sort_order,source_kind,source_identity_hash,status,row_version) "
                    "VALUES (%s,%s,%s,%s,'inserted',NULL,%s,%s,%s,%s,'portable',%s,'artifact',%s,'active',1)",
                    (dependency_gid, workspace_gid, tenant_gid, actor_gid, dependency.location,
                     dependency.media_type,
                     json.dumps(dependency_ref, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                     dependency_hash, order, source_hash),
                )
            for hierarchy_order, hierarchy in enumerate(projection.hierarchies):
                hierarchy_gid = str(next_gid())
                hierarchy_gids.append(hierarchy_gid)
                cursor.execute(
                    "INSERT INTO workmanship_sim_workspace_hierarchies "
                    "(gid,workspace_gid,tenant_gid,owner_gid,name,projection_identity,status,sort_order,row_version) "
                    "VALUES (%s,%s,%s,%s,%s,%s,'active',%s,1)",
                    (hierarchy_gid, workspace_gid, tenant_gid, actor_gid, hierarchy.name,
                     hierarchy.projection_identity, hierarchy_order),
                )
                placement_ids = {item.projection_identity: str(next_gid()) for item in hierarchy.placements}
                for placement_order, placement in enumerate(hierarchy.placements):
                    source_ref = {"projection_identity": placement.projection_identity,
                                  "stable_identity": placement.stable_identity,
                                  "document_gid": document_gid,
                                  "content_sha256": "sha256:" + artifact_hash}
                    cursor.execute(
                        "INSERT INTO workmanship_sim_workspace_placements "
                        "(gid,hierarchy_gid,workspace_gid,tenant_gid,owner_gid,target_node_gid,parent_placement_gid,source_kind,source_ref_json,transform_json,display_name,sort_order,row_version) "
                        "VALUES (%s,%s,%s,%s,%s,NULL,%s,'vm_occurrence',%s,%s,%s,%s,1)",
                        (placement_ids[placement.projection_identity], hierarchy_gid, workspace_gid,
                         tenant_gid, actor_gid, placement_ids.get(placement.parent_identity),
                         json.dumps(source_ref, sort_keys=True, separators=(",", ":")),
                         json.dumps([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1], separators=(",", ":")),
                         placement.name, placement_order),
                    )
            result = {"workspace_gid": workspace_gid, "version_gid": version_gid,
                      "document_gid": document_gid, "hierarchy_gids": hierarchy_gids,
                      "workspace_row_version": 2, "cache_revision_hash": cache_hash}
            cursor.execute(
                "INSERT INTO workmanship_sim_plmxml_restore_requests "
                "(gid,tenant_gid,actor_gid,idempotency_key,request_hash,workspace_gid,response_json,expires_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,DATE_ADD(NOW(6),INTERVAL 24 HOUR))",
                (request_gid, tenant_gid, actor_gid, idempotency_key, request_hash, workspace_gid,
                 json.dumps(result, separators=(",", ":"))),
            )
        return result

    def load_environment_runtime_model(self, *, workspace_gid: str, tenant_gid: str, actor_gid: str):
        from ..domain.plmxml_environment_codec import (
            AlternateHierarchyProjection, EnvironmentModelDocument, EnvironmentPlacementProjection, EnvironmentRuntimeModel,
        )
        documents = self.search_model_documents(workspace_gid=workspace_gid, tenant_gid=tenant_gid, actor_gid=actor_gid)["items"]
        if not documents or sum(item["role"] == "primary" for item in documents) != 1:
            raise WorkspaceRepositoryError("primary_model_document_required")
        hierarchy_rows = self.search_alternate_hierarchies(workspace_gid=workspace_gid, tenant_gid=tenant_gid, actor_gid=actor_gid)["items"]
        hierarchies = []
        for row in hierarchy_rows:
            detail = self.get_alternate_hierarchy(hierarchy_gid=row["hierarchy_gid"], tenant_gid=tenant_gid, actor_gid=actor_gid)
            raw_placements = list((detail or {}).get("placements", ()))
            identity_by_gid = {str(item["placement_gid"]): str(item["source_ref"].get("projection_identity") or item["placement_gid"]) for item in raw_placements}
            children_by_parent: dict[str, list[str]] = {}
            for item in raw_placements:
                parent_gid = item.get("parent_placement_gid")
                if parent_gid is not None:
                    children_by_parent.setdefault(str(parent_gid), []).append(identity_by_gid[str(item["placement_gid"])])
            placements = tuple(EnvironmentPlacementProjection(
                projection_identity=identity_by_gid[str(item["placement_gid"])],
                stable_identity=str(item["source_ref"].get("stable_identity") or "placement:" + item["placement_gid"]),
                name=str(item.get("display_name") or ""),
                parent_identity=identity_by_gid.get(str(item.get("parent_placement_gid"))) if item.get("parent_placement_gid") is not None else None,
                child_identities=tuple(children_by_parent.get(str(item["placement_gid"]), ())), visible=True,
            ) for item in raw_placements)
            root = next((item.projection_identity for item in placements if item.parent_identity is None), None)
            hierarchies.append(AlternateHierarchyProjection(name=str(row["name"]), projection_identity=str(row.get("projection_identity") or "ai00-hierarchy-" + row["hierarchy_gid"]), root_refs=(), root_placement_identity=root, placements=placements))
        model_documents = tuple(EnvironmentModelDocument(
            document_gid=str(item["document_gid"]), role=str(item["role"]), display_name=str(item["display_name"]),
            media_type=str(item["media_type"]), artifact_ref=item.get("artifact_ref"),
            source_identity_hash=str(item["source_identity_hash"]), content_sha256=str(item["content_sha256"]),
            portability=str(item["portability"]), connector_device_id=item.get("connector_device_id"),
        ) for item in documents)
        return EnvironmentRuntimeModel(environment_gid=str(workspace_gid), documents=model_documents, hierarchies=tuple(hierarchies))
    def get_saved_version(self, *, workspace_gid: str, version_gid: str,
                          tenant_gid: str, owner_gid: str) -> dict[str, Any]:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT w.gid workspace_gid,v.gid version_gid,v.status,v.content_hash,"
                "v.manifest_artifact_ref_json manifest_artifact_ref "
                "FROM workmanship_sim_workspaces w JOIN workmanship_sim_workspace_versions v "
                "ON v.workspace_gid=w.gid WHERE w.gid=%s AND v.gid=%s "
                "AND w.tenant_gid=%s AND (w.owner_gid=%s OR w.visibility='shared') "
                "AND w.removed_at IS NULL AND v.removed_at IS NULL",
                (_gid(workspace_gid,"workspace_gid"),_gid(version_gid,"version_gid"),
                 _gid(tenant_gid,"tenant_gid"),
                 _gid(owner_gid,"owner_gid")),
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

    def resolve_export_ref(self, reference: str, *, tenant_gid: str, owner_gid: str) -> dict[str, Any]:
        import time
        from ..security.export_refs import ExportRefError, export_ref_digest, verify_export_ref
        try:
            claims=verify_export_ref(reference,now_epoch=int(time.time()))
        except ExportRefError as exc:
            raise WorkspaceRepositoryError(str(exc)) from exc
        if str(claims.get("tenant_gid"))!=str(tenant_gid) or str(claims.get("actor_gid"))!=str(owner_gid):raise WorkspaceRepositoryError("private_export_invalid")
        with get_simulation_conn() as conn,conn.cursor() as cursor:
            cursor.execute("SELECT e.content_hash,e.consumer_capability_id,e.consumer_major_version,e.target_personal_space_gid,e.target_repository_gid,v.manifest_artifact_ref_json FROM workmanship_sim_workspace_export_refs e JOIN workmanship_sim_workspace_versions v ON v.gid=e.workspace_version_gid WHERE e.token_digest=%s AND e.tenant_gid=%s AND e.owner_gid=%s AND e.revoked_at IS NULL AND e.expires_at>NOW(6)",(export_ref_digest(reference),tenant_gid,owner_gid));row=cursor.fetchone()
        if not row:raise WorkspaceRepositoryError("private_export_invalid")
        if claims.get("content_hash")!=row["content_hash"] or claims.get("consumer")!=f'{row["consumer_capability_id"]}@{row["consumer_major_version"]}':raise WorkspaceRepositoryError("private_export_invalid")
        value=row["manifest_artifact_ref_json"]
        claims["manifest_artifact_ref"]=json.loads(value) if isinstance(value,str) else dict(value)
        return claims

    def create(self, *, name: str, review_type: str, version_label: str, status: str, visibility: str,
               project_gids: list[str], primary_project_gid: str | None,
               tenant_gid: str, owner_gid: str) -> dict[str, Any]:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            return self._create_with_cursor(cursor, name=name, review_type=review_type,
                version_label=version_label, status=status, visibility=visibility,
                project_gids=project_gids, primary_project_gid=primary_project_gid,
                tenant_gid=tenant_gid, owner_gid=owner_gid)

    def _create_with_cursor(self, cursor, *, name: str, review_type: str, version_label: str,
                            status: str, visibility: str, project_gids: list[str],
                            primary_project_gid: str | None, tenant_gid: str,
                            owner_gid: str) -> dict[str, Any]:
        workspace_gid, version_gid = str(next_gid()), str(next_gid())
        create_patch = {
            "op": "create", "workspace_gid": workspace_gid, "version_gid": version_gid,
            "name": name, "review_type": review_type, "version_label": version_label,
            "status": status, "visibility": visibility, "project_gids": list(project_gids),
            "primary_project_gid": primary_project_gid,
        }
        cache_revision_hash = next_cache_revision_hash(_EMPTY_CACHE_REVISION_HASH, create_patch, 1)
        cursor.execute(
            "INSERT INTO workmanship_sim_workspaces "
            "(gid,tenant_gid,owner_gid,name,review_type,version_label,status,visibility,primary_project_gid,cache_revision_hash,row_version) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1)",
            (workspace_gid, _gid(tenant_gid, "tenant_gid"), _gid(owner_gid, "owner_gid"), name,
             review_type, version_label, status, visibility, primary_project_gid, cache_revision_hash),
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
        self._replace_projects(cursor, workspace_gid, project_gids)
        return {"workspace_gid": workspace_gid, "version_gid": version_gid, "name": name,
                "review_type": review_type, "version_label": version_label, "status": status,
                "visibility": visibility, "primary_project_gid": primary_project_gid,
                "owner_gid": str(owner_gid), "is_owner": True, "project_gids": project_gids,
                "updated_at": datetime.now(timezone.utc).isoformat(), "row_version": 1,
                "cache_revision_hash": cache_revision_hash, "nodes": [], "bindings": []}

    @staticmethod
    def _live_document_identity(tenant_gid, actor_gid, connector_device_id, document_session):
        for field, value, limit in (("connector_device_id", connector_device_id, 191),
                                    ("document_session", document_session, 2048)):
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                raise WorkspaceRepositoryError(f"{field}_invalid")
        identity = hashlib.sha256(json.dumps([connector_device_id, document_session],
            ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
        return _gid(tenant_gid, "tenant_gid"), _gid(actor_gid, "actor_gid"), identity

    @staticmethod
    def _live_document_bound_result(cursor, binding, *, tenant_gid, actor_gid):
        if binding["state"] == "stale" or not binding["workspace_gid"]:
            raise WorkspaceRepositoryError("live_document_binding_stale")
        cursor.execute(
            "SELECT w.gid AS workspace_gid,h.version_gid FROM workmanship_sim_workspaces w "
            "JOIN workmanship_sim_workspace_heads h ON h.workspace_gid=w.gid "
            "JOIN workmanship_sim_workspace_versions v ON v.gid=h.version_gid AND v.workspace_gid=w.gid "
            "WHERE w.gid=%s AND w.tenant_gid=%s AND w.owner_gid=%s AND w.removed_at IS NULL "
            "AND v.tenant_gid=%s AND v.owner_gid=%s AND v.removed_at IS NULL FOR UPDATE",
            (binding["workspace_gid"], tenant_gid, actor_gid, tenant_gid, actor_gid))
        row = cursor.fetchone()
        if not row:
            raise WorkspaceRepositoryError("live_document_binding_stale")
        return {"workspace_gid": str(row["workspace_gid"]), "version_gid": str(row["version_gid"]),
                "state": binding["state"]}

    def find_live_document_binding(self, *, tenant_gid: str, actor_gid: str,
                                   connector_device_id: str, document_session: str) -> dict[str, Any] | None:
        """Scoped persistence lookup only; does not attest native session currentness."""
        scope = self._live_document_identity(tenant_gid, actor_gid, connector_device_id, document_session)
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT workspace_gid,state FROM workmanship_sim_live_document_bindings "
                "WHERE tenant_gid=%s AND actor_gid=%s AND session_identity_hash=%s FOR UPDATE", scope)
            binding = cursor.fetchone()
            if binding is None:
                return None
            return self._live_document_bound_result(cursor, binding, tenant_gid=scope[0], actor_gid=scope[1])

    def _ensure_live_document_primary(self, cursor, *, workspace_gid: str, tenant_gid: str,
                                      actor_gid: str, connector_device_id: str,
                                      session_identity_hash: str, display_name: str) -> str:
        cursor.execute("SELECT gid FROM workmanship_sim_vm_documents WHERE workspace_gid=%s "
            "AND source_identity_hash=%s AND removed_at IS NULL FOR UPDATE",
            (workspace_gid, session_identity_hash))
        existing = cursor.fetchone()
        if existing:
            return str(existing["gid"])
        cursor.execute("SELECT gid FROM workmanship_sim_vm_documents WHERE workspace_gid=%s "
            "AND primary_slot=1 AND removed_at IS NULL FOR UPDATE", (workspace_gid,))
        if cursor.fetchone():
            raise WorkspaceRepositoryError("primary_model_document_exists")
        cursor.execute("SELECT row_version,cache_revision_hash FROM workmanship_sim_workspaces "
            "WHERE gid=%s AND tenant_gid=%s AND owner_gid=%s AND removed_at IS NULL FOR UPDATE",
            (workspace_gid, tenant_gid, actor_gid))
        workspace = cursor.fetchone()
        if not workspace:
            raise WorkspaceRepositoryError("live_document_binding_stale")
        document_gid = str(next_gid())
        cursor.execute("INSERT INTO workmanship_sim_vm_documents "
            "(gid,workspace_gid,tenant_gid,owner_gid,document_role,primary_slot,display_name,media_type,"
            "artifact_ref_json,content_sha256,portability,connector_device_id,sort_order,source_kind,source_identity_hash,status,row_version) "
            "VALUES (%s,%s,%s,%s,'primary',1,%s,'application/vnd.siemens.teamcenter.visualization-document',"
            "NULL,'','device_bound',%s,0,'live_document',%s,'active',1)",
            (document_gid, workspace_gid, tenant_gid, actor_gid, display_name,
             connector_device_id, session_identity_hash))
        self._advance_workspace_revision(cursor, workspace_gid=workspace_gid, current=workspace,
            patch={"op": "adopt_live_document_primary", "document_gid": document_gid,
                   "source_identity_hash": session_identity_hash})
        return document_gid

    def adopt_live_document(self, *, tenant_gid: str, actor_gid: str, connector_device_id: str,
                            document_session: str, name: str, document_display_name: str | None,
                            idempotency_key: str) -> dict[str, Any]:
        """Atomically adopt or reuse; governed caller must authenticate the live session.

        V1 binding alone imports no models or AH. V2 also persists the primary
        live document record; neither version imports AH observations here.
        Request reservation precedes session reservation consistently; InnoDB unique
        upserts serialize competing requests without missing-row SELECT gap locks.
        """
        scope = self._live_document_identity(tenant_gid, actor_gid, connector_device_id, document_session)
        if not isinstance(name, str) or not name.strip() or len(name) > 255:
            raise WorkspaceRepositoryError("workspace_name_invalid")
        if document_display_name is not None and (not isinstance(document_display_name, str)
                or not document_display_name.strip() or len(document_display_name) > 255):
            raise WorkspaceRepositoryError("document_display_name_invalid")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key) > 191:
            raise WorkspaceRepositoryError("idempotency_key_invalid")
        request_hash = hashlib.sha256(json.dumps([connector_device_id, document_session, name, document_display_name],
            ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
        request_scope = (*scope[:2], idempotency_key)
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute("INSERT INTO workmanship_sim_live_document_adoptions "
                "(tenant_gid,actor_gid,idempotency_key,request_hash) VALUES (%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE idempotency_key=idempotency_key", (*request_scope, request_hash))
            cursor.execute("SELECT request_hash,response_json FROM workmanship_sim_live_document_adoptions "
                "WHERE tenant_gid=%s AND actor_gid=%s AND idempotency_key=%s FOR UPDATE", request_scope)
            request = cursor.fetchone()
            if request["request_hash"] != request_hash:
                raise WorkspaceRepositoryError("idempotency_conflict")
            cursor.execute("INSERT INTO workmanship_sim_live_document_bindings "
                "(tenant_gid,actor_gid,session_identity_hash,connector_device_id,document_session) "
                "VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE session_identity_hash=session_identity_hash",
                (*scope, connector_device_id, document_session))
            reserved = cursor.rowcount == 1
            cursor.execute("SELECT workspace_gid,state,connector_device_id,document_session "
                "FROM workmanship_sim_live_document_bindings "
                "WHERE tenant_gid=%s AND actor_gid=%s AND session_identity_hash=%s FOR UPDATE", scope)
            binding = cursor.fetchone()
            if (binding["connector_device_id"], binding["document_session"]) != (connector_device_id, document_session):
                raise WorkspaceRepositoryError("live_document_identity_conflict")
            replay_result = request["response_json"]
            if isinstance(replay_result, str):
                replay_result = json.loads(replay_result)
            if binding["workspace_gid"] is not None or not reserved or request["response_json"] is not None:
                result = self._live_document_bound_result(cursor, binding, tenant_gid=scope[0], actor_gid=scope[1])
                result["created"] = bool(replay_result.get("created")) if isinstance(replay_result, Mapping) else False
            else:
                workspace = self._create_with_cursor(cursor, name=name, review_type="other",
                    version_label="V1", status="draft", visibility="private", project_gids=[],
                    primary_project_gid=None, tenant_gid=scope[0], owner_gid=scope[1])
                cursor.execute("UPDATE workmanship_sim_live_document_bindings SET workspace_gid=%s "
                    "WHERE tenant_gid=%s AND actor_gid=%s AND session_identity_hash=%s",
                    (workspace["workspace_gid"], *scope))
                result = {"workspace_gid": workspace["workspace_gid"], "version_gid": workspace["version_gid"],
                          "state": "importing", "created": True}
            if document_display_name is not None:
                result["model_document_gid"] = self._ensure_live_document_primary(cursor,
                    workspace_gid=result["workspace_gid"], tenant_gid=scope[0], actor_gid=scope[1],
                    connector_device_id=connector_device_id, session_identity_hash=scope[2],
                    display_name=document_display_name.strip())
            cursor.execute("UPDATE workmanship_sim_live_document_adoptions SET response_json=%s "
                "WHERE tenant_gid=%s AND actor_gid=%s AND idempotency_key=%s",
                (json.dumps(result, sort_keys=True, separators=(",", ":")), *request_scope))
            return result

    def live_document_binding_for_workspace(self, *, tenant_gid: str, actor_gid: str,
                                             workspace_gid: str) -> dict[str, Any] | None:
        """One owner-scoped binding; saved identity does not attest document liveness."""
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT b.workspace_gid,b.state,b.connector_device_id,b.document_session,h.version_gid "
                "FROM workmanship_sim_live_document_bindings b "
                "JOIN workmanship_sim_workspaces w ON w.gid=b.workspace_gid "
                "JOIN workmanship_sim_workspace_heads h ON h.workspace_gid=w.gid "
                "JOIN workmanship_sim_workspace_versions v ON v.gid=h.version_gid AND v.workspace_gid=w.gid "
                "WHERE b.workspace_gid=%s AND b.tenant_gid=%s AND b.actor_gid=%s "
                "AND w.tenant_gid=%s AND w.owner_gid=%s AND w.removed_at IS NULL "
                "AND v.tenant_gid=%s AND v.owner_gid=%s AND v.removed_at IS NULL LIMIT 2",
                (_gid(workspace_gid, 'workspace_gid'), _gid(tenant_gid, 'tenant_gid'), _gid(actor_gid, 'actor_gid'),
                 tenant_gid, actor_gid, tenant_gid, actor_gid))
            rows = cursor.fetchall()
        if len(rows) > 1:
            raise WorkspaceRepositoryError('live_document_binding_unavailable')
        if not rows: return None
        return {**dict(rows[0]), 'workspace_gid': str(rows[0]['workspace_gid']),
                'version_gid': str(rows[0]['version_gid'])}

    def apply_live_hierarchy_inventory(self, *, workspace_gid: str, tenant_gid: str,
                                       actor_gid: str, connector_device_id: str,
                                       document_session: str, inventory_operation_id: str,
                                       page: Mapping[str, Any], idempotency_key: str) -> dict[str, Any]:
        """Persist one signed complete AH page; absence never deletes saved rows."""
        workspace_gid = _gid(workspace_gid, "workspace_gid")
        tenant_gid, actor_gid = _gid(tenant_gid, "tenant_gid"), _gid(actor_gid, "actor_gid")
        _, _, identity_hash = self._live_document_identity(
            tenant_gid, actor_gid, connector_device_id, document_session)
        hierarchies = [dict(item) for item in page.get("hierarchies") or []]
        if len(hierarchies) > 16 or sum(len(item.get("nodes") or []) for item in hierarchies) > 100000:
            raise WorkspaceRepositoryError("live_document_inventory_invalid")
        request = {"op": "apply_live_hierarchy_inventory", "inventory_operation_id": inventory_operation_id,
                   "document_session": document_session, "start_index": page.get("start_index")}
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT w.row_version,w.cache_revision_hash,w.status FROM workmanship_sim_workspaces w "
                "JOIN workmanship_sim_live_document_bindings b ON b.workspace_gid=w.gid "
                "WHERE w.gid=%s AND w.tenant_gid=%s AND w.owner_gid=%s AND w.removed_at IS NULL "
                "AND b.tenant_gid=%s AND b.actor_gid=%s AND b.session_identity_hash=%s "
                "AND b.connector_device_id=%s AND b.document_session=%s FOR UPDATE",
                (workspace_gid, tenant_gid, actor_gid, tenant_gid, actor_gid, identity_hash,
                 connector_device_id, document_session))
            workspace = cursor.fetchone()
            if not workspace:
                raise WorkspaceRepositoryError("live_document_binding_stale")
            request_hash, replay = self._idempotency_begin(cursor, workspace_gid=workspace_gid,
                idempotency_key=idempotency_key, request=request)
            if replay is not None:
                return replay
            imported = 0
            cursor.execute("SELECT COALESCE(MAX(sort_order),-1)+1 AS position FROM workmanship_sim_workspace_hierarchies "
                "WHERE workspace_gid=%s AND removed_at IS NULL", (workspace_gid,))
            hierarchy_position = int((cursor.fetchone() or {"position": 0})["position"])
            for hierarchy in hierarchies:
                if hierarchy.get("complete") is not True:
                    raise WorkspaceRepositoryError("live_document_inventory_partial")
                native_index = int(hierarchy.get("native_index") or 0)
                name = str(hierarchy.get("name") or "").strip()[:255]
                snapshot_hash = str(hierarchy.get("snapshot_hash") or "")
                if native_index < 1 or not name or not re.fullmatch(r"sha256:[0-9a-f]{64}", snapshot_hash):
                    raise WorkspaceRepositoryError("live_document_inventory_invalid")
                projection_identity = f"vismockup-live:{identity_hash}:{native_index}"
                cursor.execute("SELECT gid,source_refs_json FROM workmanship_sim_workspace_hierarchies "
                    "WHERE workspace_gid=%s AND projection_identity=%s AND removed_at IS NULL FOR UPDATE",
                    (workspace_gid, projection_identity))
                existing = cursor.fetchone()
                if existing:
                    refs = existing.get("source_refs_json")
                    refs = json.loads(refs) if isinstance(refs, str) else (refs or {})
                    if refs.get("snapshot_hash") != snapshot_hash:
                        raise WorkspaceRepositoryError("live_document_inventory_conflict")
                    continue
                raw_nodes = [dict(item) for item in hierarchy.get("nodes") or []]
                by_key = {str(item.get("node_key") or ""): item for item in raw_nodes}
                if not by_key or "" in by_key or len(by_key) != len(raw_nodes):
                    raise WorkspaceRepositoryError("live_document_inventory_invalid")
                roots = [key for key, item in by_key.items() if item.get("parent_key") is None]
                if len(roots) != 1 or any(str(item.get("parent_key")) not in by_key
                    for item in raw_nodes if item.get("parent_key") is not None):
                    raise WorkspaceRepositoryError("live_document_inventory_invalid")
                ordered, pending = [], dict(by_key)
                while pending:
                    done = {key for key, _ in ordered}
                    ready = [(key, item) for key, item in pending.items()
                             if item.get("parent_key") is None or str(item.get("parent_key")) in done]
                    if not ready:
                        raise WorkspaceRepositoryError("live_document_inventory_cycle")
                    ready.sort(key=lambda pair: (str(pair[1].get("parent_key") or ""),
                                                  int(pair[1].get("child_order") or 0), pair[0]))
                    for key, item in ready:
                        ordered.append((key, item)); pending.pop(key)
                hierarchy_gid = str(next_gid())
                refs = json.dumps({"document_session": document_session, "native_index": native_index,
                    "snapshot_hash": snapshot_hash, "inventory_operation_id": inventory_operation_id},
                    ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                cursor.execute("INSERT INTO workmanship_sim_workspace_hierarchies "
                    "(gid,workspace_gid,tenant_gid,owner_gid,name,projection_identity,source_refs_json,status,sort_order,row_version) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,'active',%s,1)",
                    (hierarchy_gid, workspace_gid, tenant_gid, actor_gid, name,
                     projection_identity, refs, hierarchy_position))
                hierarchy_position += 1
                node_map = {key: str(next_gid()) for key, _ in ordered}
                rows = [(node_map[key], workspace_gid, tenant_gid, actor_gid, hierarchy_gid,
                    node_map.get(str(item.get("parent_key"))) if item.get("parent_key") is not None else None,
                    "alternate_hierarchy" if item.get("parent_key") is None else "native_observation",
                    str(item.get("name") or key)[:255], int(item.get("child_order") or 0))
                    for key, item in ordered]
                sql = "INSERT INTO workmanship_sim_workspace_nodes (gid,workspace_gid,tenant_gid,owner_gid,hierarchy_gid,parent_gid,node_type,name,sort_order,source_bop_node_gid,row_version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,1)"
                for offset in range(0, len(rows), 500):
                    cursor.executemany(sql, rows[offset:offset + 500])
                imported += 1
            if imported:
                next_version, cache_hash = self._advance_workspace_revision(cursor, workspace_gid=workspace_gid,
                    current=workspace, patch={"op": "import_live_hierarchy_page",
                        "inventory_operation_id": inventory_operation_id, "count": imported})
            else:
                next_version = int(workspace["row_version"])
                cache_hash = str(workspace.get("cache_revision_hash") or _EMPTY_CACHE_REVISION_HASH)
            complete = page.get("next_index") is None
            if complete:
                cursor.execute("UPDATE workmanship_sim_live_document_bindings SET state='bound',updated_at=NOW(6) "
                    "WHERE workspace_gid=%s AND tenant_gid=%s AND actor_gid=%s AND session_identity_hash=%s",
                    (workspace_gid, tenant_gid, actor_gid, identity_hash))
            result = {"workspace_gid": workspace_gid, "imported_hierarchy_count": imported,
                "next_index": page.get("next_index"), "total_hierarchies": int(page.get("total_hierarchies") or 0),
                "complete": complete, "workspace_row_version": next_version, "cache_revision_hash": cache_hash}
            self._idempotency_finish(cursor, workspace_gid=workspace_gid, idempotency_key=idempotency_key,
                request_hash=request_hash, response=result)
            return result

    def search(self, *, tenant_gid: str, owner_gid: str, offset: int, page_size: int) -> dict[str, Any]:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT w.gid AS workspace_gid,h.version_gid,w.owner_gid,w.name,w.review_type,w.version_label,w.status,w.visibility,w.primary_project_gid,w.cache_revision_hash,w.row_version,w.updated_at "
                "FROM workmanship_sim_workspaces w JOIN workmanship_sim_workspace_heads h ON h.workspace_gid=w.gid "
                "WHERE (w.owner_gid=%s OR w.visibility='shared') AND w.removed_at IS NULL "
                "ORDER BY w.updated_at DESC,w.gid DESC LIMIT %s OFFSET %s",
                (_gid(owner_gid, "owner_gid"), page_size + 1, offset),
            )
            rows = [dict(row) for row in cursor.fetchall()]
            workspace_gids = [row["workspace_gid"] for row in rows]
            project_map: dict[str, list[str]] = {str(value): [] for value in workspace_gids}
            if workspace_gids:
                marks = ",".join(["%s"] * len(workspace_gids))
                cursor.execute(
                    f"SELECT workspace_gid,project_gid FROM workmanship_sim_workspace_projects WHERE workspace_gid IN ({marks}) ORDER BY workspace_gid,sort_order,project_gid",
                    workspace_gids,
                )
                for item in cursor.fetchall():
                    project_map[str(item["workspace_gid"])].append(str(item["project_gid"]))
        more = len(rows) > page_size
        rows = rows[:page_size]
        for row in rows:
            row.update(self._decorate(row, owner_gid=owner_gid, project_gids=project_map.get(str(row["workspace_gid"]), [])))
        return {"items": rows, "next_cursor": str(offset + page_size) if more else None}

    def get(self, workspace_gid: str, *, tenant_gid: str, owner_gid: str, lock: bool = False) -> dict[str, Any] | None:
        suffix = " FOR UPDATE" if lock else ""
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT w.gid AS workspace_gid,h.version_gid,w.tenant_gid AS workspace_tenant_gid,w.owner_gid,w.name,w.review_type,w.version_label,w.status,w.visibility,w.primary_project_gid,w.cache_revision_hash,w.row_version,w.updated_at "
                "FROM workmanship_sim_workspaces w JOIN workmanship_sim_workspace_heads h ON h.workspace_gid=w.gid "
                "WHERE w.gid=%s AND (w.owner_gid=%s OR w.visibility='shared') AND w.removed_at IS NULL" + suffix,
                (_gid(workspace_gid, "workspace_gid"), _gid(owner_gid, "owner_gid")),
            )
            workspace = cursor.fetchone()
            if not workspace:
                return None
            workspace = dict(workspace)
            source_tenant_gid = _gid(workspace.pop("workspace_tenant_gid"), "workspace_tenant_gid")
            cursor.execute("SELECT project_gid FROM workmanship_sim_workspace_projects WHERE workspace_gid=%s ORDER BY sort_order,project_gid", (workspace_gid,))
            project_gids = [str(item["project_gid"]) for item in cursor.fetchall()]
            cursor.execute(
                "SELECT gid AS node_gid,parent_gid,node_type,name,sort_order AS position,row_version "
                "FROM workmanship_sim_workspace_nodes WHERE workspace_gid=%s AND tenant_gid=%s "
                "AND removed_at IS NULL ORDER BY parent_gid,sort_order,gid",
                (workspace_gid, source_tenant_gid),
            )
            nodes = [dict(row) for row in cursor.fetchall()]
            cursor.execute(
                "SELECT gid AS binding_gid,node_gid,occurrence_gid,binding_role AS role,row_version "
                "FROM workmanship_sim_workspace_bindings WHERE workspace_gid=%s AND tenant_gid=%s "
                "AND removed_at IS NULL ORDER BY node_gid,gid",
                (workspace_gid, source_tenant_gid),
            )
            bindings = [dict(row) for row in cursor.fetchall()]
        data = self._decorate(workspace, owner_gid=owner_gid, project_gids=project_gids)
        for row in nodes:
            row["node_gid"] = str(row["node_gid"])
            row["parent_gid"] = str(row["parent_gid"]) if row.get("parent_gid") is not None else None
        for row in bindings:
            for key in ("binding_gid", "node_gid", "occurrence_gid"):
                row[key] = str(row[key])
        data.update(nodes=nodes, bindings=bindings)
        return data

    def delete(self, *, workspace_gid: str, tenant_gid: str, owner_gid: str,
               expected_row_version: int, idempotency_key: str) -> dict[str, Any]:
        workspace_gid = _gid(workspace_gid, "workspace_gid")
        tenant_gid, owner_gid = _gid(tenant_gid, "tenant_gid"), _gid(owner_gid, "owner_gid")
        if isinstance(expected_row_version, bool) or not isinstance(expected_row_version, int) or expected_row_version < 1:
            raise WorkspaceRepositoryError("expected_row_version_invalid")
        if not idempotency_key or len(idempotency_key) > 191:
            raise WorkspaceRepositoryError("idempotency_key_invalid")
        request_hash = hashlib.sha256(b"delete_workspace").hexdigest()
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT request_hash,response_json FROM workmanship_sim_workspace_idempotency "
                "WHERE workspace_gid=%s AND idempotency_key=%s FOR UPDATE",
                (workspace_gid, idempotency_key),
            )
            replay = cursor.fetchone()
            if replay:
                if replay["request_hash"] != request_hash:
                    raise WorkspaceRepositoryError("idempotency_conflict")
                value = replay["response_json"]
                return json.loads(value) if isinstance(value, str) else dict(value)
            cursor.execute(
                "SELECT row_version,tenant_gid,cache_revision_hash FROM workmanship_sim_workspaces WHERE gid=%s "
                "AND owner_gid=%s AND removed_at IS NULL FOR UPDATE",
                (workspace_gid, owner_gid),
            )
            current = cursor.fetchone()
            if not current:
                raise WorkspaceRepositoryError("workspace_not_found")
            if int(current["row_version"]) != expected_row_version:
                raise WorkspaceRepositoryError("version_conflict")
            deletion_gid = str(next_gid())
            next_version = expected_row_version + 1
            cache_revision_hash = next_cache_revision_hash(
                str(current["cache_revision_hash"]),
                {"op": "delete", "deletion_gid": deletion_gid},
                next_version,
            )
            cursor.execute(
                "UPDATE workmanship_sim_workspaces SET removed_at=NOW(6),cache_revision_hash=%s,row_version=%s,updated_at=NOW(6) "
                "WHERE gid=%s AND row_version=%s",
                (cache_revision_hash, next_version, workspace_gid, expected_row_version),
            )
            if cursor.rowcount != 1:
                raise WorkspaceRepositoryError("version_conflict")
            result = {"workspace_gid": workspace_gid, "deleted": True,
                      "deletion_gid": deletion_gid, "row_version": next_version,
                      "cache_revision_hash": cache_revision_hash}
            cursor.execute(
                "INSERT INTO workmanship_sim_workspace_idempotency "
                "(workspace_gid,idempotency_key,request_hash,response_json,expires_at) "
                "VALUES (%s,%s,%s,%s,DATE_ADD(NOW(6),INTERVAL 24 HOUR))",
                (workspace_gid, idempotency_key, request_hash,
                 json.dumps(result, ensure_ascii=False, separators=(",", ":"))),
            )
        return result

    def search_saved_versions(self, *, workspace_gid: str, tenant_gid: str,
                              actor_gid: str) -> dict[str, Any]:
        with get_simulation_conn() as conn,conn.cursor() as cursor:
            cursor.execute("SELECT v.gid version_gid,v.workspace_gid,v.sequence,v.status,v.content_hash,v.created_at FROM workmanship_sim_workspace_versions v JOIN workmanship_sim_workspaces w ON w.gid=v.workspace_gid WHERE v.workspace_gid=%s AND (w.owner_gid=%s OR w.visibility='shared') AND w.removed_at IS NULL AND v.removed_at IS NULL AND v.status IN ('saved','frozen') ORDER BY v.sequence DESC,v.gid DESC",(_gid(workspace_gid,"workspace_gid"),_gid(actor_gid,"actor_gid")))
            rows=[dict(row) for row in cursor.fetchall()]
        for row in rows:
            row["version_gid"],row["workspace_gid"]=str(row["version_gid"]),str(row["workspace_gid"])
            if row.get("created_at") is not None and not isinstance(row["created_at"],str):row["created_at"]=row["created_at"].isoformat()
        return {"items":rows}

    def create_fork_preview(self, *, workspace_gid: str, version_gid: str, target_name: str,
                            target_version_label: str, fork_depth: str, visibility: str,
                            tenant_gid: str, actor_gid: str) -> dict[str, Any]:
        if fork_depth not in {"all", *_FORK_DEPTH_RANK}:
            raise WorkspaceRepositoryError("fork_depth_invalid")
        source=self.get_saved_version(workspace_gid=workspace_gid,version_gid=version_gid,
                                      tenant_gid=tenant_gid,owner_gid=actor_gid)
        if source.get("status") not in {"saved","frozen"} or not source.get("content_hash"):
            raise WorkspaceRepositoryError("source_version_not_immutable")
        fixed={"source_workspace_gid":str(workspace_gid),"source_version_gid":str(version_gid),
               "target_name":target_name,"target_version_label":target_version_label,"fork_depth":fork_depth,
               "tenant_gid":str(tenant_gid),"actor_gid":str(actor_gid),"visibility":visibility}
        canonical=json.dumps(fixed,ensure_ascii=False,sort_keys=True,separators=(",",":"))
        input_hash="sha256:"+hashlib.sha256(canonical.encode()).hexdigest()
        plan_hash="sha256:"+hashlib.sha256((canonical+str(source["content_hash"])).encode()).hexdigest()
        preview_gid=str(next_gid());expires=datetime.now(timezone.utc)+timedelta(minutes=10)
        with get_simulation_conn() as conn,conn.cursor() as cursor:
            cursor.execute("INSERT INTO workmanship_sim_workspace_fork_plans (gid,tenant_gid,actor_gid,source_workspace_gid,source_version_gid,target_name,target_version_label,input_hash,plan_hash,expires_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",(preview_gid,tenant_gid,actor_gid,workspace_gid,version_gid,target_name,target_version_label,input_hash,plan_hash,expires))
            cursor.execute("INSERT INTO workmanship_sim_workspace_fork_plan_options (plan_gid,fork_depth,visibility) VALUES (%s,%s,%s)",(preview_gid,fork_depth,visibility))
        return {"preview_gid":preview_gid,"plan_hash":plan_hash,"source_workspace_gid":str(workspace_gid),
                "source_version_gid":str(version_gid),"source_content_hash":str(source["content_hash"]),
                "target_name":target_name,"target_version_label":target_version_label,"fork_depth":fork_depth,
                "visibility":visibility,"expires_at":expires.isoformat()}

    def get_fork_plan(self, *, preview_gid: str, tenant_gid: str, actor_gid: str,
                      plan_hash: str) -> dict[str, Any]:
        with get_simulation_conn() as conn,conn.cursor() as cursor:
            cursor.execute("SELECT p.*,o.fork_depth,o.visibility,v.content_hash,v.manifest_artifact_ref_json,w.review_type,w.primary_project_gid FROM workmanship_sim_workspace_fork_plans p JOIN workmanship_sim_workspace_fork_plan_options o ON o.plan_gid=p.gid JOIN workmanship_sim_workspace_versions v ON v.gid=p.source_version_gid JOIN workmanship_sim_workspaces w ON w.gid=p.source_workspace_gid WHERE p.gid=%s AND p.tenant_gid=%s AND p.actor_gid=%s AND p.expires_at>NOW(6)",(preview_gid,tenant_gid,actor_gid));row=cursor.fetchone()
            if not row:raise WorkspaceRepositoryError("fork_preview_expired")
            if row["plan_hash"]!=plan_hash:raise WorkspaceRepositoryError("fork_plan_changed")
            cursor.execute("SELECT project_gid FROM workmanship_sim_workspace_projects WHERE workspace_gid=%s ORDER BY sort_order,project_gid",(row["source_workspace_gid"],));projects=[str(x["project_gid"]) for x in cursor.fetchall()]
        result=dict(row);result["project_gids"]=projects
        value=result["manifest_artifact_ref_json"];result["manifest_artifact_ref"]=json.loads(value) if isinstance(value,str) else dict(value)
        return result

    def apply_fork(self, *, plan: Mapping[str, Any], manifest: Mapping[str, Any], tenant_gid: str,
                   actor_gid: str, idempotency_key: str) -> dict[str, Any]:
        request_hash=hashlib.sha256(json.dumps({"preview_gid":str(plan["gid"]),"plan_hash":plan["plan_hash"]},sort_keys=True,separators=(",",":")).encode()).hexdigest()
        with get_simulation_conn() as conn,conn.cursor() as cursor:
            cursor.execute("SELECT apply_idempotency_key,apply_request_hash,outcome_json,expires_at FROM workmanship_sim_workspace_fork_plans WHERE gid=%s AND tenant_gid=%s AND actor_gid=%s FOR UPDATE",(plan["gid"],tenant_gid,actor_gid));locked=cursor.fetchone()
            if not locked or locked["expires_at"]<=datetime.now():raise WorkspaceRepositoryError("fork_preview_expired")
            if locked["outcome_json"] is not None:
                if locked["apply_idempotency_key"]!=idempotency_key or locked["apply_request_hash"]!=request_hash:raise WorkspaceRepositoryError("idempotency_conflict")
                value=locked["outcome_json"];return json.loads(value) if isinstance(value,str) else dict(value)
            cursor.execute("SELECT 1 FROM workmanship_sim_workspaces WHERE tenant_gid=%s AND owner_gid=%s AND name=%s AND removed_at IS NULL FOR UPDATE",(tenant_gid,actor_gid,plan["target_name"]))
            if cursor.fetchone():raise WorkspaceRepositoryError("workspace_name_exists")
            workspace_gid,version_gid=str(next_gid()),str(next_gid())
            projected=project_manifest_for_fork(manifest,str(plan["fork_depth"]))
            fork_patch={"op":"fork","workspace_gid":workspace_gid,"version_gid":version_gid,
                        "source_workspace_gid":str(plan["source_workspace_gid"]),
                        "source_version_gid":str(plan["source_version_gid"]),
                        "source_content_hash":str(plan["content_hash"]),
                        "fork_depth":str(plan["fork_depth"]),"name":plan["target_name"],
                        "version_label":plan["target_version_label"],
                        "project_gids":list(plan["project_gids"]),
                        "node_count":len(projected["nodes"]),"binding_count":len(projected["bindings"])}
            cache_revision_hash=next_cache_revision_hash(_EMPTY_CACHE_REVISION_HASH,fork_patch,1)
            cursor.execute("INSERT INTO workmanship_sim_workspaces (gid,tenant_gid,owner_gid,name,review_type,version_label,status,visibility,primary_project_gid,cache_revision_hash,row_version) VALUES (%s,%s,%s,%s,%s,%s,'active',%s,%s,%s,1)",(workspace_gid,tenant_gid,actor_gid,plan["target_name"],plan["review_type"],plan["target_version_label"],plan["visibility"],plan["primary_project_gid"],cache_revision_hash))
            cursor.execute("INSERT INTO workmanship_sim_workspace_versions (gid,workspace_gid,tenant_gid,owner_gid,sequence,status,row_version) VALUES (%s,%s,%s,%s,1,'draft',1)",(version_gid,workspace_gid,tenant_gid,actor_gid))
            cursor.execute("INSERT INTO workmanship_sim_workspace_heads (workspace_gid,version_gid,row_version) VALUES (%s,%s,1)",(workspace_gid,version_gid))
            self._replace_projects(cursor,workspace_gid,list(plan["project_gids"]))
            node_map={str(row["node_gid"]):str(next_gid()) for row in projected["nodes"]}
            nodes=[]
            for row in projected["nodes"]:
                old=str(row["node_gid"]);parent=row.get("parent_gid");new_parent=node_map.get(str(parent)) if parent is not None else None
                cursor.execute("INSERT INTO workmanship_sim_workspace_nodes (gid,workspace_gid,tenant_gid,owner_gid,parent_gid,node_type,name,sort_order,source_bop_node_gid,row_version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,1)",(node_map[old],workspace_gid,tenant_gid,actor_gid,new_parent,row["node_type"],row["name"],int(row.get("position",0)),row.get("source_bop_node_gid")))
                nodes.append({"node_gid":node_map[old],"parent_gid":new_parent,"node_type":row["node_type"],"name":row["name"],"position":int(row.get("position",0)),"row_version":1})
            bindings=[]
            for row in projected["bindings"]:
                node_gid=node_map.get(str(row["node_gid"]));
                if not node_gid:raise WorkspaceRepositoryError("fork_manifest_invalid")
                binding_gid=str(next_gid());cursor.execute("INSERT INTO workmanship_sim_workspace_bindings (gid,workspace_gid,tenant_gid,owner_gid,node_gid,occurrence_gid,binding_role,row_version) VALUES (%s,%s,%s,%s,%s,%s,%s,1)",(binding_gid,workspace_gid,tenant_gid,actor_gid,node_gid,row["occurrence_gid"],row.get("role","operate")))
                bindings.append({"binding_gid":binding_gid,"node_gid":node_gid,"occurrence_gid":str(row["occurrence_gid"]),"role":row.get("role","operate"),"row_version":1})
            result={"workspace_gid":workspace_gid,"version_gid":version_gid,"owner_gid":str(actor_gid),"is_owner":True,"name":plan["target_name"],"review_type":plan["review_type"],"version_label":plan["target_version_label"],"status":"active","visibility":plan["visibility"],"primary_project_gid":str(plan["primary_project_gid"]) if plan["primary_project_gid"] is not None else None,"project_gids":list(plan["project_gids"]),"updated_at":datetime.now(timezone.utc).isoformat(),"row_version":1,"cache_revision_hash":cache_revision_hash,"nodes":nodes,"bindings":bindings,"fork_base":{"workspace_gid":str(plan["source_workspace_gid"]),"version_gid":str(plan["source_version_gid"]),"content_hash":plan["content_hash"],"fork_depth":str(plan["fork_depth"])}}
            cursor.execute("UPDATE workmanship_sim_workspace_fork_plans SET apply_idempotency_key=%s,apply_request_hash=%s,outcome_json=%s,updated_at=NOW(6) WHERE gid=%s",(idempotency_key,request_hash,json.dumps(result,ensure_ascii=False,separators=(",",":")),plan["gid"]))
        return result

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
                "SELECT row_version,status,tenant_gid,cache_revision_hash FROM workmanship_sim_workspaces WHERE gid=%s "
                "AND owner_gid=%s AND removed_at IS NULL FOR UPDATE",
                (workspace_gid, owner_gid),
            )
            current = cursor.fetchone()
            if not current:
                raise WorkspaceRepositoryError("workspace_not_found")
            tenant_gid = _gid(current["tenant_gid"], "workspace_tenant_gid")
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

            if operation == "update_workspace":
                if current["status"] == "frozen":
                    raise WorkspaceRepositoryError("workspace_frozen")
                project_gids = list(values["project_gids"])
                cursor.execute(
                    "UPDATE workmanship_sim_workspaces SET name=%s,review_type=%s,version_label=%s,status=%s,visibility=%s,primary_project_gid=%s WHERE gid=%s",
                    (values["name"], values["review_type"], values["version_label"], values["status"],
                     values["visibility"], values["primary_project_gid"], workspace_gid),
                )
                self._replace_projects(cursor, workspace_gid, project_gids)
                entity_gid = workspace_gid
                patch = {"op": "update_workspace", **dict(values)}
            elif operation == "create_node":
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
            cache_revision_hash = next_cache_revision_hash(
                str(current["cache_revision_hash"]), patch, next_version,
            )
            cursor.execute(
                "UPDATE workmanship_sim_workspaces SET cache_revision_hash=%s,row_version=%s,updated_at=NOW(6) "
                "WHERE gid=%s AND row_version=%s",
                (cache_revision_hash, next_version, workspace_gid, expected_row_version),
            )
            if cursor.rowcount != 1:
                raise WorkspaceRepositoryError("version_conflict")
            result = {
                "entity_gid": entity_gid,
                "row_version": next_version,
                "cache_revision_hash": cache_revision_hash,
                "patch": patch,
            }
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
                "SELECT w.gid AS workspace_gid,h.version_gid,w.tenant_gid,w.row_version,v.status AS version_status "
                "FROM workmanship_sim_workspaces w JOIN workmanship_sim_workspace_heads h ON h.workspace_gid=w.gid "
                "JOIN workmanship_sim_workspace_versions v ON v.gid=h.version_gid "
                "WHERE w.gid=%s AND w.owner_gid=%s AND w.removed_at IS NULL",
                (workspace_gid, owner_gid),
            )
            source = cursor.fetchone()
            if not source:
                raise WorkspaceRepositoryError("workspace_not_found")
            source = dict(source)
            tenant_gid = _gid(source["tenant_gid"], "workspace_tenant_gid")
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
        from ..domain.plmxml_environment_codec import runtime_model_to_dict
        result["runtime_model"] = runtime_model_to_dict(self.load_environment_runtime_model(
            workspace_gid=workspace_gid, tenant_gid=tenant_gid, actor_gid=owner_gid,
        ))
        return result

    def find_freeze_result(self, *, workspace_gid: str, idempotency_key: str,
                           request_hash: str) -> dict[str, Any] | None:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT o.version_gid,o.content_hash,o.artifact_ref_json,o.status,w.row_version,w.cache_revision_hash "
                "FROM workmanship_sim_workspace_freeze_outbox o JOIN workmanship_sim_workspaces w ON w.gid=o.workspace_gid "
                "WHERE o.workspace_gid=%s AND o.idempotency_key=%s",
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
                "status": "frozen", "content_hash": request_hash, "artifact_ref": artifact,
                "row_version": int(row["row_version"]),
                "cache_revision_hash": str(row["cache_revision_hash"])}

    def complete_freeze(
        self, *, workspace_gid: str, tenant_gid: str, owner_gid: str, version_gid: str,
        expected_row_version: int, idempotency_key: str, content_hash: str,
        artifact_ref: Mapping[str, Any], algorithms: Mapping[str, str],
    ) -> dict[str, Any]:
        outbox_gid = str(next_gid())
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT w.row_version,w.cache_revision_hash,v.status FROM workmanship_sim_workspaces w "
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
            next_version = expected_row_version + 1
            cache_revision_hash = next_cache_revision_hash(
                str(current["cache_revision_hash"]),
                {"op": "freeze", "version_gid": str(version_gid), "content_hash": content_hash,
                 "artifact_ref": dict(artifact_ref), "algorithms": dict(algorithms)},
                next_version,
            )
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
                "UPDATE workmanship_sim_workspaces SET cache_revision_hash=%s,row_version=%s,updated_at=NOW(6) WHERE gid=%s "
                "AND row_version=%s", (cache_revision_hash, next_version, workspace_gid, expected_row_version),
            )
            if cursor.rowcount != 1:
                raise WorkspaceRepositoryError("version_conflict")
        return {"workspace_gid": str(workspace_gid), "version_gid": str(version_gid), "status": "frozen",
                "content_hash": content_hash, "artifact_ref": dict(artifact_ref),
                "row_version": next_version, "cache_revision_hash": cache_revision_hash}

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

"""Persistence boundary for private, owner-scoped Simulation workspaces."""
from __future__ import annotations

import json
import hashlib
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


class WorkspaceRepository:
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
    def get_saved_version(self, *, workspace_gid: str, version_gid: str,
                          tenant_gid: str, owner_gid: str) -> dict[str, Any]:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT w.gid workspace_gid,v.gid version_gid,v.status,v.content_hash,"
                "v.manifest_artifact_ref_json manifest_artifact_ref "
                "FROM workmanship_sim_workspaces w JOIN workmanship_sim_workspace_versions v "
                "ON v.workspace_gid=w.gid WHERE w.gid=%s AND v.gid=%s "
                "AND (w.owner_gid=%s OR w.visibility='shared') AND w.removed_at IS NULL AND v.removed_at IS NULL",
                (_gid(workspace_gid,"workspace_gid"),_gid(version_gid,"version_gid"),
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
        workspace_gid, version_gid = str(next_gid()), str(next_gid())
        create_patch = {
            "op": "create", "workspace_gid": workspace_gid, "version_gid": version_gid,
            "name": name, "review_type": review_type, "version_label": version_label,
            "status": status, "visibility": visibility, "project_gids": list(project_gids),
            "primary_project_gid": primary_project_gid,
        }
        cache_revision_hash = next_cache_revision_hash(_EMPTY_CACHE_REVISION_HASH, create_patch, 1)
        with get_simulation_conn() as conn, conn.cursor() as cursor:
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
                            target_version_label: str, fork_depth: str,
                            tenant_gid: str, actor_gid: str) -> dict[str, Any]:
        if fork_depth not in {"all", *_FORK_DEPTH_RANK}:
            raise WorkspaceRepositoryError("fork_depth_invalid")
        source=self.get_saved_version(workspace_gid=workspace_gid,version_gid=version_gid,
                                      tenant_gid=tenant_gid,owner_gid=actor_gid)
        if source.get("status") not in {"saved","frozen"} or not source.get("content_hash"):
            raise WorkspaceRepositoryError("source_version_not_immutable")
        fixed={"source_workspace_gid":str(workspace_gid),"source_version_gid":str(version_gid),
               "target_name":target_name,"target_version_label":target_version_label,"fork_depth":fork_depth,
               "tenant_gid":str(tenant_gid),"actor_gid":str(actor_gid),"visibility":"private"}
        canonical=json.dumps(fixed,ensure_ascii=False,sort_keys=True,separators=(",",":"))
        input_hash="sha256:"+hashlib.sha256(canonical.encode()).hexdigest()
        plan_hash="sha256:"+hashlib.sha256((canonical+str(source["content_hash"])).encode()).hexdigest()
        preview_gid=str(next_gid());expires=datetime.now(timezone.utc)+timedelta(minutes=10)
        with get_simulation_conn() as conn,conn.cursor() as cursor:
            cursor.execute("INSERT INTO workmanship_sim_workspace_fork_plans (gid,tenant_gid,actor_gid,source_workspace_gid,source_version_gid,target_name,target_version_label,input_hash,plan_hash,expires_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",(preview_gid,tenant_gid,actor_gid,workspace_gid,version_gid,target_name,target_version_label,input_hash,plan_hash,expires))
            cursor.execute("INSERT INTO workmanship_sim_workspace_fork_plan_options (plan_gid,fork_depth) VALUES (%s,%s)",(preview_gid,fork_depth))
        return {"preview_gid":preview_gid,"plan_hash":plan_hash,"source_workspace_gid":str(workspace_gid),
                "source_version_gid":str(version_gid),"source_content_hash":str(source["content_hash"]),
                "target_name":target_name,"target_version_label":target_version_label,"fork_depth":fork_depth,
                "visibility":"private","expires_at":expires.isoformat()}

    def get_fork_plan(self, *, preview_gid: str, tenant_gid: str, actor_gid: str,
                      plan_hash: str) -> dict[str, Any]:
        with get_simulation_conn() as conn,conn.cursor() as cursor:
            cursor.execute("SELECT p.*,o.fork_depth,v.content_hash,v.manifest_artifact_ref_json,w.review_type,w.primary_project_gid FROM workmanship_sim_workspace_fork_plans p JOIN workmanship_sim_workspace_fork_plan_options o ON o.plan_gid=p.gid JOIN workmanship_sim_workspace_versions v ON v.gid=p.source_version_gid JOIN workmanship_sim_workspaces w ON w.gid=p.source_workspace_gid WHERE p.gid=%s AND p.tenant_gid=%s AND p.actor_gid=%s AND p.expires_at>NOW(6)",(preview_gid,tenant_gid,actor_gid));row=cursor.fetchone()
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
            cursor.execute("INSERT INTO workmanship_sim_workspaces (gid,tenant_gid,owner_gid,name,review_type,version_label,status,visibility,primary_project_gid,cache_revision_hash,row_version) VALUES (%s,%s,%s,%s,%s,%s,'active','private',%s,%s,1)",(workspace_gid,tenant_gid,actor_gid,plan["target_name"],plan["review_type"],plan["target_version_label"],plan["primary_project_gid"],cache_revision_hash))
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
            result={"workspace_gid":workspace_gid,"version_gid":version_gid,"owner_gid":str(actor_gid),"is_owner":True,"name":plan["target_name"],"review_type":plan["review_type"],"version_label":plan["target_version_label"],"status":"active","visibility":"private","primary_project_gid":str(plan["primary_project_gid"]) if plan["primary_project_gid"] is not None else None,"project_gids":list(plan["project_gids"]),"updated_at":datetime.now(timezone.utc).isoformat(),"row_version":1,"cache_revision_hash":cache_revision_hash,"nodes":nodes,"bindings":bindings,"fork_base":{"workspace_gid":str(plan["source_workspace_gid"]),"version_gid":str(plan["source_version_gid"]),"content_hash":plan["content_hash"],"fork_depth":str(plan["fork_depth"])}}
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

"""MySQL adapter for BOP repository foundation operations."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from backend.platform_sdk.ids import next_gid

from .bop_repository import BopRepositoryError
from .connection import get_craft_conn


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _decode(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else (value or {})


class MysqlBopRepositoryStore:
    def __init__(self, connection_factory: Callable[..., Any] = get_craft_conn) -> None:
        self._connect = connection_factory

    @staticmethod
    def _row(cur, sql, args, error):
        cur.execute(sql, args); row = cur.fetchone()
        if not row: raise BopRepositoryError(error)
        return dict(row)

    @staticmethod
    def _page(cur, sql, args, offset, page_size):
        cur.execute(sql + " LIMIT %s OFFSET %s", (*args, page_size + 1, offset))
        rows = [dict(row) for row in cur.fetchall()]
        return {"items": rows[:page_size], "next_cursor": str(offset + page_size) if len(rows) > page_size else None}

    def _write(self, cur, *, tenant_gid, operation, resource_gid, key, payload, effect):
        digest = hashlib.sha256(_json(payload).encode()).hexdigest()
        cur.execute("SELECT request_hash,status,outcome_json FROM workmanship_craft_bop_operation_ledger WHERE tenant_gid=%s AND operation_kind=%s AND idempotency_key=%s FOR UPDATE", (tenant_gid, operation, key))
        prior = cur.fetchone()
        if prior:
            if prior["request_hash"] != digest: raise BopRepositoryError("idempotency_conflict")
            if prior["status"] == "completed":
                return json.loads(prior["outcome_json"]) if isinstance(prior["outcome_json"], str) else prior["outcome_json"]
            raise BopRepositoryError("operation_in_progress")
        ledger_gid = str(next_gid())
        cur.execute("INSERT INTO workmanship_craft_bop_operation_ledger (gid,tenant_gid,operation_kind,resource_gid,idempotency_key,request_hash,status) VALUES (%s,%s,%s,%s,%s,%s,'running')", (ledger_gid,tenant_gid,operation,resource_gid,key,digest))
        result = effect()
        cur.execute("UPDATE workmanship_craft_bop_operation_ledger SET status='completed',outcome_json=%s,updated_at=CURRENT_TIMESTAMP(6) WHERE gid=%s", (_json(result),ledger_gid))
        return result

    def search_repositories(self, *, tenant_gid, actor_gid, project_gid=None, offset=0, page_size=50):
        # Project repositories are organization-visible; tenant_gid remains an
        # audit/storage partition and is not a visibility boundary.
        where, args = "deleted_at IS NULL", []
        if project_gid: where += " AND project_gid=%s"; args.append(project_gid)
        with self._connect() as conn, conn.cursor() as cur:
            return self._page(cur, f"SELECT gid repository_gid,project_gid,baseline_version_gid,lifecycle_status,row_version,updated_at FROM workmanship_craft_bop_repositories WHERE {where} ORDER BY updated_at DESC,gid DESC", tuple(args), offset, page_size)

    def get_repository(self, *, repository_gid, tenant_gid, actor_gid):
        with self._connect() as conn, conn.cursor() as cur:
            return self._row(cur, "SELECT gid repository_gid,project_gid,baseline_version_gid,lifecycle_status,row_version,created_at,updated_at FROM workmanship_craft_bop_repositories WHERE gid=%s AND deleted_at IS NULL", (repository_gid,), "repository_not_found")

    def create_repository(self, *, project_gid, tenant_gid, actor_gid, idempotency_key):
        payload={"project_gid":project_gid,"actor_gid":actor_gid}
        with self._connect() as conn, conn.cursor() as cur:
            def effect():
                cur.execute("SELECT gid FROM workmanship_craft_bop_repositories WHERE tenant_gid=%s AND project_gid=%s AND deleted_at IS NULL FOR UPDATE",(tenant_gid,project_gid))
                if cur.fetchone(): raise BopRepositoryError("target_repository_exists")
                rg,sg,hg=map(str,(next_gid(),next_gid(),next_gid())); empty="sha256:"+hashlib.sha256(b'{"members":[]}').hexdigest()
                cur.execute("INSERT INTO workmanship_craft_bop_repositories (gid,tenant_gid,project_gid,created_by) VALUES (%s,%s,%s,%s)",(rg,tenant_gid,project_gid,actor_gid))
                cur.execute("INSERT INTO workmanship_craft_bop_spaces (gid,repository_gid,tenant_gid,space_kind,created_by) VALUES (%s,%s,%s,'team',%s)",(sg,rg,tenant_gid,actor_gid))
                cur.execute("INSERT INTO workmanship_craft_bop_space_heads (gid,space_gid,tenant_gid,content_hash,updated_by) VALUES (%s,%s,%s,%s,%s)",(hg,sg,tenant_gid,empty,actor_gid))
                return {"repository_gid":rg,"project_gid":str(project_gid),"team_space_gid":sg,"head_gid":hg,"baseline_version_gid":None,"lifecycle_status":"active","row_version":1}
            return self._write(cur,tenant_gid=tenant_gid,operation="repository.create",resource_gid=None,key=idempotency_key,payload=payload,effect=effect)

    def _repository_lifecycle(self, action, *, repository_gid, tenant_gid, actor_gid, expected_row_version, idempotency_key, reason=""):
        payload={"repository_gid":repository_gid,"expected_row_version":expected_row_version,"reason":reason}
        with self._connect() as conn, conn.cursor() as cur:
            def effect():
                row=self._row(cur,"SELECT lifecycle_status,row_version FROM workmanship_craft_bop_repositories WHERE gid=%s AND tenant_gid=%s AND deleted_at IS NULL FOR UPDATE",(repository_gid,tenant_gid),"repository_not_found")
                if row["row_version"] != expected_row_version: raise BopRepositoryError("resource_version_conflict")
                if action == "delete":
                    cur.execute("SELECT 1 FROM workmanship_craft_bop_spaces WHERE repository_gid=%s AND space_kind='managed_personal' AND deleted_at IS NULL LIMIT 1",(repository_gid,))
                    if cur.fetchone(): raise BopRepositoryError("active_personal_space_exists")
                    cur.execute("SELECT 1 FROM workmanship_craft_bop_change_proposals WHERE repository_gid=%s AND apply_status<>'applied' AND review_status NOT IN ('rejected','withdrawn','cancelled','superseded') LIMIT 1",(repository_gid,))
                    if cur.fetchone(): raise BopRepositoryError("unresolved_proposal_exists")
                    cur.execute("SELECT 1 FROM workmanship_craft_bop_fork_runs WHERE repository_gid=%s AND status IN ('previewing','pending','running','reconciling') LIMIT 1",(repository_gid,))
                    if cur.fetchone(): raise BopRepositoryError("active_run_exists")
                    deletion_gid=str(next_gid()); cur.execute("UPDATE workmanship_craft_bop_repositories SET deleted_at=CURRENT_TIMESTAMP(6),deleted_by=%s,deletion_gid=%s,row_version=row_version+1 WHERE gid=%s",(actor_gid,deletion_gid,repository_gid)); return {"repository_gid":str(repository_gid),"deleted":True,"deletion_gid":deletion_gid,"row_version":expected_row_version+1}
                status="archived" if action=="archive" else "active"
                cur.execute("UPDATE workmanship_craft_bop_repositories SET lifecycle_status=%s,row_version=row_version+1,updated_at=CURRENT_TIMESTAMP(6) WHERE gid=%s",(status,repository_gid))
                return {"repository_gid":str(repository_gid),"lifecycle_status":status,"row_version":expected_row_version+1}
            return self._write(cur,tenant_gid=tenant_gid,operation=f"repository.{action}",resource_gid=repository_gid,key=idempotency_key,payload=payload,effect=effect)

    def archive_repository(self, **kw): return self._repository_lifecycle("archive",**kw)
    def restore_repository(self, **kw): return self._repository_lifecycle("restore",**kw)
    def delete_repository(self, **kw): return self._repository_lifecycle("delete",**kw)

    def search_spaces(self, *, repository_gid, tenant_gid, actor_gid, owner_gid, offset=0, page_size=50):
        with self._connect() as conn, conn.cursor() as cur:
            return self._page(cur,"SELECT s.gid space_gid,s.repository_gid,s.space_kind,s.owner_user_gid,s.fork_base_version_gid,s.frozen_version_gid,s.row_version,s.updated_at,h.gid head_gid,h.row_version head_row_version,h.content_hash FROM workmanship_craft_bop_spaces s JOIN workmanship_craft_bop_space_heads h ON h.space_gid=s.gid WHERE s.repository_gid=%s AND s.deleted_at IS NULL AND (s.space_kind='team' OR s.owner_user_gid=%s) ORDER BY s.updated_at DESC,s.gid DESC",(repository_gid,owner_gid),offset,page_size)

    def get_space(self, space_gid, *, tenant_gid, actor_gid):
        with self._connect() as conn, conn.cursor() as cur:
            space = self._row(cur,"SELECT s.gid space_gid,s.repository_gid,r.project_gid,s.space_kind,s.owner_user_gid,s.fork_base_version_gid,s.frozen_version_gid,s.row_version,h.gid head_gid,h.row_version head_row_version,h.content_hash FROM workmanship_craft_bop_spaces s JOIN workmanship_craft_bop_repositories r ON r.gid=s.repository_gid JOIN workmanship_craft_bop_space_heads h ON h.space_gid=s.gid WHERE s.gid=%s AND s.deleted_at IS NULL",(space_gid,),"space_not_found")
            cur.execute(
                "SELECT m.logical_gid node_gid,n.lineage_gid,r.parent_node_gid parent_gid,"
                "r.node_type,r.order_key,r.properties_json,map.legacy_gid "
                "FROM workmanship_craft_bop_space_head_members m "
                "JOIN workmanship_craft_bop_node_revisions r ON r.gid=m.node_revision_gid "
                "JOIN workmanship_craft_bop_nodes n ON n.gid=m.logical_gid "
                "LEFT JOIN workmanship_craft_bop_repository_id_map map "
                "ON map.legacy_kind='entry' AND map.repository_gid=n.repository_gid "
                "AND map.logical_gid=m.logical_gid "
                "WHERE m.space_head_gid=%s AND m.member_kind='node' AND m.is_tombstone=0 "
                "ORDER BY r.order_key,m.logical_gid LIMIT 20001", (space["head_gid"],),
            )
            raw_nodes = [dict(row) for row in cur.fetchall()]
            if len(raw_nodes) > 20000:
                raise BopRepositoryError("space_projection_limit_exceeded")
            by_gid = {str(row["node_gid"]): row for row in raw_nodes}

            def line_for(row):
                current = row
                visited = set()
                while current and str(current["node_gid"]) not in visited:
                    visited.add(str(current["node_gid"]))
                    if current.get("node_type") in {"line", "line_process"}:
                        return str(current.get("legacy_gid") or current["node_gid"])
                    current = by_gid.get(str(current.get("parent_gid"))) if current.get("parent_gid") else None
                return None

            nodes = []
            for row in raw_nodes:
                properties = _decode(row.get("properties_json"))
                nodes.append({
                    "node_gid": str(row["node_gid"]),
                    "parent_gid": str(row["parent_gid"]) if row.get("parent_gid") is not None else None,
                    "node_type": row["node_type"],
                    "name": str(properties.get("title") or properties.get("name") or row["node_type"]),
                    "position": row.get("order_key") or "0",
                    "line_gid": line_for(row),
                })
            space["nodes"] = nodes
            space["bindings"] = []
            return space

    def search_space_versions(self, *, space_gid, tenant_gid, actor_gid, offset=0, page_size=50):
        with self._connect() as conn, conn.cursor() as cur:
            return self._page(cur,"SELECT gid version_gid,space_gid,version_kind,parent_version_gid,manifest_hash,created_by,created_at FROM workmanship_craft_bop_space_versions WHERE space_gid=%s AND tenant_gid=%s ORDER BY created_at DESC,gid DESC",(space_gid,tenant_gid),offset,page_size)

    def get_space_version(self, *, version_gid, tenant_gid, actor_gid):
        with self._connect() as conn, conn.cursor() as cur:
            return self._row(cur,"SELECT gid version_gid,space_gid,version_kind,parent_version_gid,source_refs_json source_refs,algorithm_versions_json algorithm_versions,manifest_artifact_ref_json manifest_artifact_ref,manifest_hash,created_by,created_at FROM workmanship_craft_bop_space_versions WHERE gid=%s AND tenant_gid=%s",(version_gid,tenant_gid),"space_version_not_found")

    # Writes below deliberately reuse the transaction-safe invariant implementation until
    # node revision services are introduced by the following implementation tasks.
    def save_space_version(self, **kwargs):
        from .bop_repository_mysql_writes import save_space_version
        return save_space_version(self, **kwargs)
    def freeze_team_space(self, **kwargs):
        from .bop_repository_mysql_writes import freeze_team_space
        return freeze_team_space(self, **kwargs)
    def set_baseline(self, **kwargs):
        from .bop_repository_mysql_writes import set_baseline
        return set_baseline(self, **kwargs)
    def delete_personal_space(self, **kwargs):
        from .bop_repository_mysql_writes import delete_personal_space
        return delete_personal_space(self, **kwargs)


__all__=["MysqlBopRepositoryStore"]

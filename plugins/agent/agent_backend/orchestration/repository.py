from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from ..data.connection import get_agent_conn
from .models import GraphDraft


class RevisionConflict(RuntimeError):
    pass


class ResourceNotAccessible(RuntimeError):
    pass


class InvalidTransition(RuntimeError):
    pass


class UntrustedBindingEvidence(RuntimeError):
    pass


_RUN_TRANSITIONS = {
    "pending": {"running", "failed"},
    "running": {"waiting_human", "succeeded", "failed"},
    "waiting_human": {"running", "failed"},
    "succeeded": set(),
    "failed": set(),
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _decoded(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    return json.loads(value) if isinstance(value, str) else value


def _require_scope(tenant_gid: str | None, project_gid: str | None) -> tuple[str, str]:
    if not tenant_gid or not project_gid:
        raise ResourceNotAccessible("tenant and project scope are required")
    return tenant_gid, project_gid


class OrchestrationRepository:
    def __init__(self, connection_factory: Callable[[], AbstractContextManager] = get_agent_conn):
        self._connection_factory = connection_factory

    @staticmethod
    def _owned_version_for_update(
        cur: Any, version_gid: str, actor_gid: str,
        tenant_gid: str | None = None, project_gid: str | None = None,
    ) -> dict[str, Any]:
        scope_sql = ""
        scope_params: list[str] = []
        if tenant_gid:
            scope_sql += " AND p.tenant_gid=%s"
            scope_params.append(tenant_gid)
        if project_gid:
            scope_sql += " AND p.project_gid=%s"
            scope_params.append(project_gid)
        cur.execute(
            """SELECT v.panorama_gid,v.status,v.revision
               FROM workmanship_agent_orch_versions v
               JOIN workmanship_agent_orch_panoramas p ON p.gid=v.panorama_gid
               WHERE v.gid=%s AND p.owner_user_gid=%s""" + scope_sql + " FOR UPDATE",
            (version_gid, actor_gid, *scope_params),
        )
        version = cur.fetchone()
        if not version:
            raise ResourceNotAccessible("orchestration version is not accessible")
        return dict(version)

    @staticmethod
    def _insert_run_event(
        cur: Any,
        *,
        run_gid: str,
        sequence_no: int,
        event_type: str,
        actor_type: str,
        actor_gid: str | None,
        payload: dict[str, Any],
        item_gid: str | None = None,
        capability_call_id: str | None = None,
        evidence_id: str | None = None,
    ) -> str:
        event_gid = str(uuid.uuid4())
        cur.execute(
            """INSERT INTO workmanship_agent_orch_run_events
               (gid,run_gid,sequence_no,event_type,item_gid,actor_type,actor_gid,payload_json,
                capability_call_id,evidence_id,occurred_at,created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(6),NOW(6))""",
            (
                event_gid,
                run_gid,
                sequence_no,
                event_type,
                item_gid,
                actor_type,
                actor_gid,
                _json(payload),
                capability_call_id,
                evidence_id,
            ),
        )
        return event_gid

    def list_panoramas_for_user(self, actor_gid: str, *, tenant_gid: str, project_gid: str, limit: int = 50) -> list[dict[str, Any]]:
        tenant_gid, project_gid = _require_scope(tenant_gid, project_gid)
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT gid,name,current_version_gid,revision,updated_at
                   FROM workmanship_agent_orch_panoramas
                   WHERE owner_user_gid=%s AND tenant_gid=%s AND project_gid=%s
                   ORDER BY updated_at DESC LIMIT %s""",
                (actor_gid, tenant_gid, project_gid, min(max(limit, 1), 100)),
            )
            return list(cur.fetchall())

    def get_metric_for_user(self, panorama_gid: str, period_key: str, actor_gid: str, *, tenant_gid: str, project_gid: str) -> dict[str, Any]:
        tenant_gid, project_gid = _require_scope(tenant_gid, project_gid)
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT m.* FROM workmanship_agent_orch_metric_snapshots m
                   JOIN workmanship_agent_orch_panoramas p ON p.gid=m.panorama_gid
                   WHERE m.panorama_gid=%s AND m.period_key=%s AND p.owner_user_gid=%s
                     AND p.tenant_gid=%s AND p.project_gid=%s
                   ORDER BY m.calculated_at DESC LIMIT 1""",
                (panorama_gid, period_key, actor_gid, tenant_gid, project_gid),
            )
            row = cur.fetchone()
        if not row:
            raise KeyError(f"orchestration metric not found: {panorama_gid}/{period_key}")
        return dict(row)

    def get_workload_evidence(
        self, evidence_gid: str, *, actor_gid: str, tenant_gid: str, project_gid: str,
    ) -> dict[str, Any]:
        """Read KPI evidence only through the owning repository and scope."""
        tenant_gid, project_gid = _require_scope(tenant_gid, project_gid)
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT a.gid AS evidence_gid, b.task_key, a.run_gid,
                          b.version_gid, b.gid AS workload_baseline_gid,
                          b.authorization_evidence_gid, a.acceptance_evidence_gid,
                          b.authorization_artifact_hash, a.acceptance_artifact_hash,
                          b.annual_task_volume, b.standard_manual_hours,
                          a.agent_share, a.acceptance_pass_rate,
                          a.safety_gate_passed, b.mandatory_human,
                          (b.authorization_revoked OR a.acceptance_revoked) AS revoked,
                          b.authorization_valid_from AS valid_from,
                          b.authorization_valid_until AS valid_until,
                          a.acceptance_valid_from, a.acceptance_valid_until
                   FROM workmanship_agent_orch_acceptance_facts a
                   JOIN workmanship_agent_orch_workload_baselines b
                     ON b.panorama_gid=a.panorama_gid
                    AND b.version_gid=a.version_gid
                    AND b.task_key=a.task_key
                    AND b.period_key=a.period_key
                   JOIN workmanship_agent_orch_panoramas p ON p.gid=a.panorama_gid
                   JOIN workmanship_agent_orch_runs r ON r.gid=a.run_gid
                   WHERE a.gid=%s AND p.owner_user_gid=%s
                     AND p.tenant_gid=%s AND p.project_gid=%s
                     AND r.status='succeeded'
                   LIMIT 1""",
                (evidence_gid, actor_gid, tenant_gid, project_gid),
            )
            row = cur.fetchone()
        if not row:
            raise KeyError(f"trusted workload evidence not found: {evidence_gid}")
        return dict(row)

    def list_automation_workflows(self, *, tenant_gid: str, project_gid: str) -> tuple[set[str], set[str]]:
        """Return publication/runtime sets from the scoped Agent tables."""
        tenant_gid, project_gid = _require_scope(tenant_gid, project_gid)
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT v.gid, MAX(CASE WHEN r.status='succeeded' THEN 1 ELSE 0 END) AS ran
                   FROM workmanship_agent_orch_versions v
                   JOIN workmanship_agent_orch_panoramas p ON p.gid=v.panorama_gid
                   LEFT JOIN workmanship_agent_orch_runs r ON r.version_gid=v.gid
                   WHERE v.status='published' AND p.tenant_gid=%s AND p.project_gid=%s
                   GROUP BY v.gid""",
                (tenant_gid, project_gid),
            )
            rows = cur.fetchall()
        published = {str(row["gid"]) for row in rows}
        successful = {str(row["gid"]) for row in rows if int(row.get("ran") or 0) == 1}
        return published, successful

    def get_graph(
        self, version_gid: str, *, actor_gid: str,
        tenant_gid: str, project_gid: str,
    ) -> GraphDraft:
        tenant_gid, project_gid = _require_scope(tenant_gid, project_gid)
        scope_sql = (" AND p.tenant_gid=%s" if tenant_gid else "") + (" AND p.project_gid=%s" if project_gid else "")
        scope_params = tuple(value for value in (tenant_gid, project_gid) if value)
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT v.mode FROM workmanship_agent_orch_versions v
                   JOIN workmanship_agent_orch_panoramas p ON p.gid=v.panorama_gid
                   WHERE v.gid=%s AND p.owner_user_gid=%s""" + scope_sql,
                (version_gid, actor_gid, *scope_params),
            )
            version = cur.fetchone()
            if not version:
                raise ResourceNotAccessible("orchestration version is not accessible")
            cur.execute(
                "SELECT x_items_json,y_items_json FROM workmanship_agent_orch_axis_views WHERE version_gid=%s ORDER BY created_at LIMIT 1",
                (version_gid,),
            )
            axis = cur.fetchone() or {}

            cur.execute(
                "SELECT gid,node_key,title,x_item_key,y_item_key,objective,owner_ref,position_json,inputs_json,outputs_json,acceptance_json FROM workmanship_agent_orch_business_nodes WHERE version_gid=%s ORDER BY created_at",
                (version_gid,),
            )
            nodes = [{
                "gid": row["gid"], "node_key": row["node_key"], "title": row["title"],
                "x_item_key": row["x_item_key"], "y_item_key": row["y_item_key"],
                "objective": row.get("objective") or "", "owner_ref": row.get("owner_ref") or "",
                "position": _decoded(row.get("position_json"), {"x": 0, "y": 0}),
                "inputs": _decoded(row.get("inputs_json"), []),
                "outputs": _decoded(row.get("outputs_json"), []),
                "acceptance_criteria": _decoded(row.get("acceptance_json"), []),
            } for row in cur.fetchall()]

            cur.execute(
                "SELECT gid,edge_type,source_node_gid,target_node_gid,label,route_points_json FROM workmanship_agent_orch_flow_edges WHERE version_gid=%s ORDER BY created_at",
                (version_gid,),
            )
            edges = [{
                "gid": row["gid"], "edge_type": row["edge_type"],
                "source_node_gid": row["source_node_gid"], "target_node_gid": row["target_node_gid"],
                "label": row.get("label") or "", "route_points": _decoded(row.get("route_points_json"), []),
            } for row in cur.fetchall()]

            cur.execute(
                "SELECT gid,business_node_gid,item_type,title,sequence_no,config_json FROM workmanship_agent_orch_items WHERE version_gid=%s ORDER BY sequence_no,gid",
                (version_gid,),
            )
            items = [{
                "gid": row["gid"], "business_node_gid": row.get("business_node_gid") or None,
                "item_type": row["item_type"], "title": row["title"],
                "sequence_no": row.get("sequence_no", 0), "config": _decoded(row.get("config_json"), {}),
            } for row in cur.fetchall()]

            cur.execute(
                "SELECT gid,source_item_gid,target_item_gid,relation_type,sequence_no FROM workmanship_agent_orch_item_edges WHERE version_gid=%s ORDER BY sequence_no,gid",
                (version_gid,),
            )
            item_edges = list(cur.fetchall())

            cur.execute(
                "SELECT gid,source_item_gid,capability_id,capability_version_gid,purpose,version_constraint,input_mapping_json,output_mapping_json,authorization_scope_json,execution_policy_json,evidence_policy_json FROM workmanship_agent_orch_capability_bindings WHERE version_gid=%s ORDER BY created_at",
                (version_gid,),
            )
            capability_bindings = []
            for row in cur.fetchall():
                policy = _decoded(row.get("execution_policy_json"), {})
                capability_bindings.append({
                    "gid": row["gid"], "source_item_gid": row["source_item_gid"],
                    "capability_version_gid": row["capability_version_gid"],
                    "purpose": row["purpose"],
                    "input_mapping": _decoded(row.get("input_mapping_json"), {}),
                    "output_mapping": _decoded(row.get("output_mapping_json"), {}),
                    "authorization_scope": _decoded(row.get("authorization_scope_json"), {}),
                    "timeout_seconds": policy.get("timeout_seconds", 30),
                    "retry_policy": policy.get("retry", {}), "fallback_policy": policy.get("fallback", {}),
                    "evidence_policy": _decoded(row.get("evidence_policy_json"), {}),
                })

            cur.execute(
                "SELECT gid,source_item_gid,ref_type,ref_gid,ref_version,snapshot_gid,purpose FROM workmanship_agent_orch_context_bindings WHERE version_gid=%s ORDER BY created_at",
                (version_gid,),
            )
            context_bindings = list(cur.fetchall())

        return GraphDraft.model_validate({
            "mode": version.get("mode") or "fixed",
            "axis": {
                "x_items": _decoded(axis.get("x_items_json"), None),
                "y_items": _decoded(axis.get("y_items_json"), None),
            } if axis else {},
            "nodes": nodes, "edges": edges, "items": items, "item_edges": item_edges,
            "capability_bindings": capability_bindings, "context_bindings": context_bindings,
        })

    def get_graph_for_user(
        self, version_gid: str, actor_gid: str,
        tenant_gid: str, project_gid: str,
    ) -> GraphDraft:
        return self.get_graph(
            version_gid, actor_gid=actor_gid,
            tenant_gid=tenant_gid, project_gid=project_gid,
        )

    def publish_version(
        self,
        version_gid: str,
        *,
        expected_revision: int,
        actor_gid: str,
        resolved_bindings: list[dict[str, Any]],
        tenant_gid: str | None = None,
        project_gid: str | None = None,
    ) -> dict[str, Any]:
        tenant_gid, project_gid = _require_scope(tenant_gid, project_gid)
        with self._connection_factory() as conn, conn.cursor() as cur:
            version = self._owned_version_for_update(cur, version_gid, actor_gid, tenant_gid, project_gid)
            if version["status"] != "draft" or int(version["revision"]) != expected_revision:
                raise RevisionConflict("orchestration version is published or stale")
            cur.execute(
                """SELECT gid,capability_version_gid
                   FROM workmanship_agent_orch_capability_bindings
                   WHERE version_gid=%s ORDER BY gid FOR UPDATE""",
                (version_gid,),
            )
            stored_bindings = list(cur.fetchall())
            resolved_by_gid = {
                binding["binding_gid"]: binding for binding in resolved_bindings
            }
            stored_by_gid = {binding["gid"]: binding for binding in stored_bindings}
            if (
                len(resolved_by_gid) != len(resolved_bindings)
                or set(resolved_by_gid) != set(stored_by_gid)
                or any(
                    resolved_by_gid[gid]["capability_version_gid"]
                    != stored_by_gid[gid]["capability_version_gid"]
                    for gid in stored_by_gid
                )
            ):
                raise UntrustedBindingEvidence(
                    "stored Capability bindings do not match trusted resolution evidence"
                )
            for binding in resolved_bindings:
                execution_policy = {
                    "gateway_ref": binding["gateway_ref"],
                    "provider_ref": binding["provider_ref"],
                    "catalog_release_gid": binding["catalog_release_gid"],
                    "artifact_hash": binding["artifact_hash"],
                    "timeout_seconds": binding["timeout_seconds"],
                    "retry": binding["retry_policy"],
                    "fallback": binding["fallback_policy"],
                }
                cur.execute(
                    """UPDATE workmanship_agent_orch_capability_bindings
                       SET capability_id=%s,version_constraint=%s,execution_policy_json=%s,updated_at=NOW(6)
                       WHERE gid=%s AND version_gid=%s AND capability_version_gid=%s""",
                    (
                        binding["capability_id"],
                        f"={binding['major_version']}",
                        _json(execution_policy),
                        binding["binding_gid"],
                        version_gid,
                        binding["capability_version_gid"],
                    ),
                )
                if cur.rowcount != 1:
                    raise ResourceNotAccessible("orchestration Capability binding is not accessible")
            cur.execute(
                """UPDATE workmanship_agent_orch_versions
                   SET status='published', revision=revision+1, published_at=NOW(6),
                       updated_at=NOW(6), updated_by=%s
                   WHERE gid=%s AND status='draft' AND revision=%s""",
                (actor_gid, version_gid, expected_revision),
            )
            if cur.rowcount != 1:
                raise RevisionConflict("orchestration version is published or stale")
            cur.execute(
                """UPDATE workmanship_agent_orch_panoramas
                   SET current_version_gid=%s, revision=revision+1, updated_at=NOW(6)
                   WHERE gid=(SELECT panorama_gid FROM workmanship_agent_orch_versions WHERE gid=%s)""",
                (version_gid, version_gid),
            )
        return {"version_gid": version_gid, "revision": expected_revision + 1, "status": "published"}

    def delete_binding(
        self, binding_gid: str, *, actor_gid: str,
        tenant_gid: str | None = None, project_gid: str | None = None,
    ) -> None:
        tenant_gid, project_gid = _require_scope(tenant_gid, project_gid)
        scope_sql = ""
        scope_params: list[str] = []
        if tenant_gid:
            scope_sql += " AND p.tenant_gid=%s"
            scope_params.append(tenant_gid)
        if project_gid:
            scope_sql += " AND p.project_gid=%s"
            scope_params.append(project_gid)
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT b.gid FROM workmanship_agent_orch_capability_bindings b
                   JOIN workmanship_agent_orch_versions v ON v.gid=b.version_gid
                   JOIN workmanship_agent_orch_panoramas p ON p.gid=v.panorama_gid
                   WHERE b.gid=%s AND v.status='draft' AND p.owner_user_gid=%s""" + scope_sql + " FOR UPDATE",
                (binding_gid, actor_gid, *scope_params),
            )
            if not cur.fetchone():
                raise ResourceNotAccessible("orchestration binding is not accessible")
            cur.execute(
                "DELETE FROM workmanship_agent_orch_capability_bindings WHERE gid=%s",
                (binding_gid,),
            )

    def create_run_with_started_event(
        self,
        *,
        panorama_gid: str,
        version_gid: str,
        frozen_context: dict[str, Any],
        actor_gid: str,
        tenant_gid: str | None = None,
        project_gid: str | None = None,
    ) -> str:
        tenant_gid, project_gid = _require_scope(tenant_gid, project_gid)
        run_gid = str(uuid.uuid4())
        scope_sql = (" AND p.tenant_gid=%s" if tenant_gid else "") + (" AND p.project_gid=%s" if project_gid else "")
        scope_params = tuple(value for value in (tenant_gid, project_gid) if value)
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT v.gid FROM workmanship_agent_orch_versions v
                   JOIN workmanship_agent_orch_panoramas p ON p.gid=v.panorama_gid
                   WHERE v.gid=%s AND v.panorama_gid=%s AND v.status='published'
                     AND p.owner_user_gid=%s""" + scope_sql + " FOR UPDATE",
                (version_gid, panorama_gid, actor_gid, *scope_params),
            )
            if not cur.fetchone():
                raise ResourceNotAccessible("published orchestration version is not accessible")
            cur.execute(
                """INSERT INTO workmanship_agent_orch_runs
                   (gid,panorama_gid,version_gid,status,frozen_context_json,started_at,started_by,created_at,updated_at)
                   VALUES (%s,%s,%s,'running',%s,NOW(6),%s,NOW(6),NOW(6))""",
                (run_gid, panorama_gid, version_gid, _json(frozen_context), actor_gid),
            )
            self._insert_run_event(
                cur,
                run_gid=run_gid,
                sequence_no=1,
                event_type="started",
                actor_type="human",
                actor_gid=actor_gid,
                payload={},
            )
        return run_gid

    def transition_run_with_event(
        self,
        run_gid: str,
        *,
        target_status: str,
        authorized_principal_gid: str,
        actor_type: str,
        event_actor_gid: str,
        payload: dict[str, Any],
        item_gid: str | None = None,
        capability_call_id: str | None = None,
        evidence_id: str | None = None,
        tenant_gid: str | None = None,
        project_gid: str | None = None,
    ) -> dict[str, Any]:
        tenant_gid, project_gid = _require_scope(tenant_gid, project_gid)
        scope_sql = (" AND p.tenant_gid=%s" if tenant_gid else "") + (" AND p.project_gid=%s" if project_gid else "")
        scope_params = tuple(value for value in (tenant_gid, project_gid) if value)
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT r.status FROM workmanship_agent_orch_runs r
                   JOIN workmanship_agent_orch_panoramas p ON p.gid=r.panorama_gid
                   WHERE r.gid=%s AND p.owner_user_gid=%s""" + scope_sql + " FOR UPDATE",
                (run_gid, authorized_principal_gid, *scope_params),
            )
            run = cur.fetchone()
            if not run:
                raise ResourceNotAccessible("orchestration run is not accessible")
            current_status = run["status"]
            if target_status not in _RUN_TRANSITIONS.get(current_status, set()):
                raise InvalidTransition(
                    f"invalid orchestration transition: {current_status} -> {target_status}"
                )
            cur.execute(
                """SELECT COALESCE(MAX(sequence_no),0) AS last_sequence_no
                   FROM workmanship_agent_orch_run_events WHERE run_gid=%s""",
                (run_gid,),
            )
            sequence_no = int(cur.fetchone()["last_sequence_no"]) + 1
            terminal = target_status in {"succeeded", "failed"}
            cur.execute(
                """UPDATE workmanship_agent_orch_runs
                   SET status=%s,finished_at=CASE WHEN %s THEN NOW(6) ELSE NULL END,updated_at=NOW(6)
                   WHERE gid=%s""",
                (target_status, terminal, run_gid),
            )
            event_payload = {"from": current_status, "to": target_status, **payload}
            event_gid = self._insert_run_event(
                cur,
                run_gid=run_gid,
                sequence_no=sequence_no,
                event_type="status_changed",
                actor_type=actor_type,
                actor_gid=event_actor_gid,
                payload=event_payload,
                item_gid=item_gid,
                capability_call_id=capability_call_id,
                evidence_id=evidence_id,
            )
        return {
            "run_gid": run_gid,
            "status": target_status,
            "sequence_no": sequence_no,
            "event_gid": event_gid,
        }

    def get_run_state_for_user(self, run_gid: str, actor_gid: str, *, tenant_gid: str, project_gid: str) -> dict[str, Any]:
        tenant_gid, project_gid = _require_scope(tenant_gid, project_gid)
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT r.status,COALESCE(MAX(e.sequence_no),0) AS last_sequence_no
                   FROM workmanship_agent_orch_runs r
                   JOIN workmanship_agent_orch_panoramas p ON p.gid=r.panorama_gid
                   LEFT JOIN workmanship_agent_orch_run_events e ON e.run_gid=r.gid
                   WHERE r.gid=%s AND p.owner_user_gid=%s
                     AND p.tenant_gid=%s AND p.project_gid=%s
                   GROUP BY r.gid,r.status""",
                (run_gid, actor_gid, tenant_gid, project_gid),
            )
            row = cur.fetchone()
        if not row:
            raise KeyError(f"orchestration run not found: {run_gid}")
        return {"status": row["status"], "last_sequence_no": int(row["last_sequence_no"])}

    def save_graph(
        self,
        version_gid: str,
        graph: GraphDraft,
        *,
        expected_revision: int,
        actor_gid: str,
        tenant_gid: str | None = None,
        project_gid: str | None = None,
    ) -> int:
        tenant_gid, project_gid = _require_scope(tenant_gid, project_gid)
        next_revision = expected_revision + 1
        with self._connection_factory() as conn, conn.cursor() as cur:
            version = self._owned_version_for_update(cur, version_gid, actor_gid, tenant_gid, project_gid)
            if version["status"] != "draft" or int(version["revision"]) != expected_revision:
                raise RevisionConflict("orchestration version is published or stale")
            cur.execute(
                """UPDATE workmanship_agent_orch_versions
                   SET mode=%s, revision=revision+1, updated_at=NOW(6), updated_by=%s
                   WHERE gid=%s AND status='draft' AND revision=%s""",
                (graph.mode, actor_gid, version_gid, expected_revision),
            )
            if cur.rowcount != 1:
                raise RevisionConflict("orchestration version is published or stale")

            for table in (
                "workmanship_agent_orch_axis_views",
                "workmanship_agent_orch_flow_edges",
                "workmanship_agent_orch_item_edges",
                "workmanship_agent_orch_capability_bindings",
                "workmanship_agent_orch_context_bindings",
                "workmanship_agent_orch_items",
                "workmanship_agent_orch_business_nodes",
            ):
                cur.execute(f"DELETE FROM {table} WHERE version_gid=%s", (version_gid,))

            cur.execute(
                """INSERT INTO workmanship_agent_orch_axis_views
                   (gid,version_gid,name,x_items_json,y_items_json,revision,created_at,updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,NOW(6),NOW(6))""",
                (
                    str(uuid.uuid4()),
                    version_gid,
                    "默认视图",
                    _json(graph.axis.x_items),
                    _json(graph.axis.y_items),
                    next_revision,
                ),
            )
            for node in graph.nodes:
                cur.execute(
                    """INSERT INTO workmanship_agent_orch_business_nodes
                       (gid,version_gid,node_key,title,objective,owner_ref,x_item_key,y_item_key,
                        position_json,inputs_json,outputs_json,acceptance_json,created_at,updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(6),NOW(6))""",
                    (
                        node.gid, version_gid, node.node_key, node.title, node.objective,
                        node.owner_ref, node.x_item_key, node.y_item_key,
                        _json(node.position.model_dump()), _json(node.inputs), _json(node.outputs),
                        _json(node.acceptance_criteria),
                    ),
                )
            for edge in graph.edges:
                cur.execute(
                    """INSERT INTO workmanship_agent_orch_flow_edges
                       (gid,version_gid,edge_type,source_node_gid,target_node_gid,label,
                        route_points_json,metadata_json,created_at,updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW(6),NOW(6))""",
                    (
                        edge.gid, version_gid, edge.edge_type, edge.source_node_gid,
                        edge.target_node_gid, edge.label,
                        _json([point.model_dump() for point in edge.route_points]), _json({}),
                    ),
                )
            for item in graph.items:
                cur.execute(
                    """INSERT INTO workmanship_agent_orch_items
                       (gid,version_gid,business_node_gid,item_type,title,sequence_no,config_json,created_at,updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,NOW(6),NOW(6))""",
                    (
                        item.gid, version_gid, item.business_node_gid or "", item.item_type,
                        item.title, item.sequence_no, _json(item.config),
                    ),
                )
            for edge in graph.item_edges:
                cur.execute(
                    """INSERT INTO workmanship_agent_orch_item_edges
                       (gid,version_gid,source_item_gid,target_item_gid,relation_type,sequence_no,created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,NOW(6))""",
                    (
                        edge.gid, version_gid, edge.source_item_gid, edge.target_item_gid,
                        edge.relation_type, edge.sequence_no,
                    ),
                )
            for binding in graph.capability_bindings:
                execution_policy = {
                    "timeout_seconds": binding.timeout_seconds,
                    "retry": binding.retry_policy,
                    "fallback": binding.fallback_policy,
                }
                cur.execute(
                    """INSERT INTO workmanship_agent_orch_capability_bindings
                       (gid,version_gid,source_item_gid,capability_id,capability_version_gid,purpose,
                        version_constraint,input_mapping_json,output_mapping_json,authorization_scope_json,
                        execution_policy_json,evidence_policy_json,created_at,updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(6),NOW(6))""",
                    (
                        binding.gid, version_gid, binding.source_item_gid, None,
                        binding.capability_version_gid, binding.purpose, None,
                        _json(binding.input_mapping), _json(binding.output_mapping),
                        _json(binding.authorization_scope), _json(execution_policy),
                        _json(binding.evidence_policy),
                    ),
                )
            for binding in graph.context_bindings:
                cur.execute(
                    """INSERT INTO workmanship_agent_orch_context_bindings
                       (gid,version_gid,source_item_gid,ref_type,ref_gid,ref_version,snapshot_gid,purpose,
                        metadata_json,created_at,updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(6),NOW(6))""",
                    (
                        binding.gid, version_gid, binding.source_item_gid, binding.ref_type,
                        binding.ref_gid, binding.ref_version, binding.snapshot_gid, binding.purpose,
                        _json({}),
                    ),
                )
        return next_revision

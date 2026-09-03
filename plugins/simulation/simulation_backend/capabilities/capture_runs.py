"""Governed materialization and reverse-process capture capabilities."""
from __future__ import annotations

import json
from typing import Any

from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError,
    CapabilityContext,
    CapabilityOutput,
    CapabilityRisk,
    CapabilitySpec,
    EvidenceRef,
)
from backend.contracts.connector_execution_plan_v1 import canonical_hash

from ..application.capture_worker import CaptureWorkflow, SimulationWorkflowError
from ..application.runtime_ports import connector_port, craft_screenshot_port
from ..data.connection import get_simulation_conn
from ..data.environment_repository import repository as manifest_repository


def _loads(value, default):
    if isinstance(value, str):
        return json.loads(value)
    return default if value is None else value


class SqlCaptureWorkflowRepository:
    def can_read_capture_run(self, capture_run_id, *, user_gid, team_gid):
        if not capture_run_id or not user_gid or not team_gid:
            return False
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM workmanship_sim_capture_runs "
                "WHERE capture_run_id=%s AND (owner_gid=%s OR team_gid=%s) LIMIT 1",
                (capture_run_id, user_gid, team_gid),
            )
            return cursor.fetchone() is not None

    def can_read_materialization_run(self, run_id, *, user_gid, team_gid):
        if not run_id or not user_gid or not team_gid:
            return False
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM workmanship_sim_materialization_runs "
                "WHERE run_id=%s AND (owner_gid=%s OR team_gid=%s) LIMIT 1",
                (run_id, user_gid, team_gid),
            )
            return cursor.fetchone() is not None

    def get_manifest(self, environment_id, environment_version, context):
        return manifest_repository.get_manifest(environment_id, environment_version, context)

    def create_materialization_run(self, row):
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO workmanship_sim_materialization_runs "
                "(run_id,environment_id,environment_version,manifest_hash,device_id,plan_id,plan_json,status,owner_gid,team_gid,created_at,updated_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(6),NOW(6))",
                tuple(row[key] for key in (
                    "run_id", "environment_id", "environment_version", "manifest_hash", "device_id",
                    "plan_id",
                )) + (json.dumps(row["plan"], sort_keys=True, separators=(",", ":")),) + tuple(
                    row[key] for key in ("status", "owner_gid", "team_gid")
                ),
            )

    def get_materialization_run(self, run_id, context):
        visibility = "" if context is None else " AND (owner_gid=%s OR (%s IS NOT NULL AND team_gid=%s))"
        params: tuple[Any, ...] = (run_id,)
        if context is not None:
            params += (context.user_gid, context.team_gid, context.team_gid)
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT run_id,environment_id,environment_version,manifest_hash,device_id,plan_id,plan_json,status "
                "FROM workmanship_sim_materialization_runs WHERE run_id=%s" + visibility + " LIMIT 1",
                params,
            )
            row = cursor.fetchone()
        if not row:
            return None
        value = dict(row)
        value["plan"] = _loads(value.pop("plan_json"), None)
        operation_status = {
            "queued": "accepted", "leased": "running", "running": "running",
            "completed": "completed", "failed": "failed", "cancelled": "cancelled",
            "outcome_unknown": "outcome_unknown",
        }[value["status"]]
        value["operation_ref"] = {
            "operation_id": value["plan_id"], "status": operation_status, "version": 1,
        }
        return value

    def create_capture_run(self, row):
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO workmanship_sim_capture_runs "
                "(capture_run_id,environment_id,environment_version,manifest_hash,device_id,plan_id,status,owner_gid,team_gid,created_at,updated_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(6),NOW(6))",
                tuple(row[key] for key in (
                    "capture_run_id", "environment_id", "environment_version", "manifest_hash", "device_id",
                    "plan_id", "status", "owner_gid", "team_gid",
                )),
            )
            cursor.executemany(
                "INSERT INTO workmanship_sim_capture_steps "
                "(capture_run_id,step_id,operation_id,sequence,status,attempt,expected_scene_hash,plan_json,artifact_attached,owner_gid,team_gid,created_at,updated_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,FALSE,%s,%s,NOW(6),NOW(6))",
                [(
                    row["capture_run_id"], f"capture-{index:05d}", step["operation_id"], step["sequence"],
                    step["status"], step["attempt"], step["expected_scene_hash"],
                    json.dumps(step["plan"], sort_keys=True, separators=(",", ":")),
                    row["owner_gid"], row["team_gid"],
                ) for index, step in enumerate(row["steps"], start=1)],
            )

    def update_materialization_run(self, run_id, **changes):
        if set(changes) != {"status"}:
            raise ValueError("materialization_run_update_not_allowed")
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "UPDATE workmanship_sim_materialization_runs SET status=%s,updated_at=NOW(6) WHERE run_id=%s",
                (changes["status"], run_id),
            )
            if cursor.rowcount != 1:
                raise SimulationWorkflowError("materialization_run_not_found")

    def get_capture_run(self, capture_run_id, context):
        visibility = "" if context is None else " AND (owner_gid=%s OR (%s IS NOT NULL AND team_gid=%s))"
        params: tuple[Any, ...] = (capture_run_id,)
        if context is not None:
            params += (context.user_gid, context.team_gid, context.team_gid)
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT capture_run_id,environment_id,environment_version,manifest_hash,device_id,plan_id,status "
                "FROM workmanship_sim_capture_runs WHERE capture_run_id=%s" + visibility + " LIMIT 1",
                params,
            )
            run = cursor.fetchone()
            if not run:
                return None
            cursor.execute(
                "SELECT operation_id,sequence,status,attempt,artifact_ref_json,plan_json,artifact_attached,expected_scene_hash "
                "FROM workmanship_sim_capture_steps WHERE capture_run_id=%s ORDER BY sequence DESC,operation_id DESC",
                (capture_run_id,),
            )
            steps = [dict(item) for item in cursor.fetchall()]
        value = dict(run)
        for step in steps:
            step["artifact_ref"] = _loads(step.pop("artifact_ref_json"), None)
            step["plan"] = _loads(step.pop("plan_json"), None)
            step["artifact_attached"] = bool(step["artifact_attached"])
        operation_status = {
            "queued": "accepted", "leased": "running", "running": "running",
            "cancelling": "running", "completed": "completed", "partial": "failed",
            "failed": "failed", "cancelled": "cancelled", "outcome_unknown": "outcome_unknown",
        }[value["status"]]
        value["operation_ref"] = {"operation_id": value["plan_id"], "status": operation_status, "version": 1}
        value["steps"] = steps
        return value

    def update_capture_run(self, capture_run_id, **changes):
        if set(changes) != {"status"}:
            raise ValueError("capture_run_update_not_allowed")
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "UPDATE workmanship_sim_capture_runs SET status=%s,updated_at=NOW(6) WHERE capture_run_id=%s",
                (changes["status"], capture_run_id),
            )
            if cursor.rowcount != 1:
                raise SimulationWorkflowError("capture_run_not_found")

    def update_capture_step(self, capture_run_id, operation_id, **changes):
        allowed = {"status", "attempt", "plan", "artifact_ref", "artifact_attached", "actual_scene_hash", "failure_code"}
        if not changes or set(changes) - allowed:
            raise ValueError("capture_step_update_not_allowed")
        assignments, params = [], []
        for key, value in changes.items():
            column = {"artifact_ref": "artifact_ref_json", "plan": "plan_json"}.get(key, key)
            assignments.append(f"`{column}`=%s")
            params.append(
                json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                if key in {"artifact_ref", "plan"} and value is not None else value
            )
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                f"UPDATE workmanship_sim_capture_steps SET {','.join(assignments)},updated_at=NOW(6) "
                "WHERE capture_run_id=%s AND operation_id=%s",
                tuple(params) + (capture_run_id, operation_id),
            )
            if cursor.rowcount != 1:
                raise SimulationWorkflowError("capture_step_not_found")
            if changes.get("artifact_ref"):
                artifact = changes["artifact_ref"]
                cursor.execute(
                    "SELECT owner_gid,team_gid FROM workmanship_sim_capture_runs WHERE capture_run_id=%s",
                    (capture_run_id,),
                )
                owner = cursor.fetchone()
                cursor.execute(
                    "INSERT INTO workmanship_sim_capture_artifact_refs "
                    "(capture_run_id,step_id,operation_id,artifact_id,artifact_version,artifact_sha256,artifact_ref_json,craft_attachment_status,owner_gid,team_gid,created_at) "
                    "SELECT capture_run_id,step_id,operation_id,%s,%s,%s,%s,'pending',%s,%s,NOW(6) "
                    "FROM workmanship_sim_capture_steps WHERE capture_run_id=%s AND operation_id=%s "
                    "ON DUPLICATE KEY UPDATE artifact_ref_json=VALUES(artifact_ref_json)",
                    (artifact["artifact_id"], artifact["version"], artifact["sha256"], json.dumps(artifact, sort_keys=True), owner["owner_gid"], owner["team_gid"], capture_run_id, operation_id),
                )
            if changes.get("artifact_attached") is True:
                cursor.execute(
                    "UPDATE workmanship_sim_capture_artifact_refs SET craft_attachment_status='attached' "
                    "WHERE capture_run_id=%s AND operation_id=%s AND craft_attachment_status='pending'",
                    (capture_run_id, operation_id),
                )


class _UnavailableConnectorPort:
    def queue_plan(self, plan, context, *, approval_reference):
        raise SimulationWorkflowError("connector_offline")


class _UnavailableCraftPort:
    def attach_screenshot(self, **kwargs):
        raise SimulationWorkflowError("craft_screenshot_attach_failed")


def _project_capture(row: dict[str, Any]) -> dict[str, Any]:
    projected = {key: row[key] for key in (
        "capture_run_id", "environment_id", "environment_version", "manifest_hash",
        "device_id", "plan_id", "status", "operation_ref", "steps",
    )}
    projected["steps"] = [
        {key: value for key, value in step.items() if key != "plan"}
        for step in projected["steps"]
    ]
    return projected


class CaptureRunProvider:
    def __init__(self, workflow: CaptureWorkflow):
        self.workflow = workflow

    @staticmethod
    def _call(function, *args):
        try:
            return function(*args)
        except SimulationWorkflowError as exc:
            raise CapabilityBusinessError(str(exc), str(exc)) from exc

    @staticmethod
    async def _call_async(function, *args):
        try:
            return await function(*args)
        except SimulationWorkflowError as exc:
            raise CapabilityBusinessError(str(exc), str(exc)) from exc

    async def materialize(self, payload, context):
        row = await self._call_async(self.workflow.start_materialization, payload["environment_id"], payload["environment_version"], payload["device_id"], context)
        data = {key: row[key] for key in ("run_id", "environment_id", "environment_version", "manifest_hash", "device_id", "plan_id", "status", "operation_ref")}
        return CapabilityOutput(data=data, evidence=(EvidenceRef(kind="simulation.materialization", reference=f"simulation://materialization/{row['run_id']}", digest=row["manifest_hash"]),))

    @staticmethod
    def _project_action(action):
        if action is None:
            return None
        return {
            "capability_id": action["capability_id"],
            "major_version": action["major_version"],
            "payload_json": json.dumps(action["payload"], sort_keys=True, separators=(",", ":")),
            "payload_hash": canonical_hash(action["payload"]),
            "idempotency_key": action["idempotency_key"],
        }

    def materialization_action(self, payload, context):
        action = self._call(
            self.workflow.next_materialization_action, payload["run_id"], context,
        )
        return CapabilityOutput(data={"action": self._project_action(action)})

    async def dispatch_materialization(self, payload, context):
        row = await self._call_async(
            self.workflow.dispatch_materialization,
            payload["run_id"], context.confirmation_token, context,
        )
        data = {key: row[key] for key in (
            "run_id", "environment_id", "environment_version", "manifest_hash",
            "device_id", "plan_id", "status", "operation_ref",
        )}
        return CapabilityOutput(data=data)

    async def start(self, payload, context):
        row = await self._call_async(self.workflow.start_capture, payload["environment_id"], payload["environment_version"], payload["device_id"], context)
        return CapabilityOutput(data=_project_capture(row), evidence=(EvidenceRef(kind="simulation.capture_run", reference=f"simulation://capture/{row['capture_run_id']}", digest=row["manifest_hash"]),))

    def get(self, payload, context):
        return CapabilityOutput(data=_project_capture(self._call(self.workflow.get, payload["capture_run_id"], context)))

    def action(self, payload, context):
        action = self._call(self.workflow.next_action, payload["capture_run_id"], context)
        return CapabilityOutput(data={"action": self._project_action(action)})

    async def dispatch(self, payload, context):
        row = await self._call_async(
            self.workflow.dispatch_next,
            payload["capture_run_id"],
            context.confirmation_token,
            context,
        )
        return CapabilityOutput(data=_project_capture(row))

    def cancel(self, payload, context):
        return CapabilityOutput(data=self._call(self.workflow.cancel, payload["capture_run_id"], context))

    async def retry(self, payload, context):
        return CapabilityOutput(data=await self._call_async(self.workflow.retry_step, payload["capture_run_id"], payload["operation_id"], context))


default_provider = CaptureRunProvider(CaptureWorkflow(
    repository=SqlCaptureWorkflowRepository(),
    connector_port=connector_port, craft_port=craft_screenshot_port,
))


def specs(provider: CaptureRunProvider = default_provider):
    common = {"owner": "simulation", "version": 1, "permissions": ("simulation.use",), "plugin_callable": True, "tags": ("simulation", "connector_environment")}
    return (
        (CapabilitySpec(id="simulation.environment.materialize", description="Queue exact Connector materialization for an immutable environment.", risk=CapabilityRisk.WRITE, confirmation="user", **common), provider.materialize),
        (CapabilitySpec(id="simulation.materialization_run.action.get", description="Read the exact materialization action awaiting user confirmation.", risk=CapabilityRisk.READ, confirmation="none", **common), provider.materialization_action),
        (CapabilitySpec(id="simulation.materialization_run.dispatch", description="Dispatch one prepared materialization action using its separate user confirmation.", risk=CapabilityRisk.WRITE, confirmation="none", **common), provider.dispatch_materialization),
        (CapabilitySpec(id="simulation.capture_run.start", description="Queue internal VisMockup captures in reverse process order.", risk=CapabilityRisk.WRITE, confirmation="user", **common), provider.start),
        (CapabilitySpec(id="simulation.capture_run.get", description="Read authoritative reverse-capture progress.", risk=CapabilityRisk.READ, confirmation="none", **common), provider.get),
        (CapabilitySpec(id="simulation.capture_run.action.get", description="Read the exact next downstream action awaiting user confirmation.", risk=CapabilityRisk.READ, confirmation="none", **common), provider.action),
        (CapabilitySpec(id="simulation.capture_run.dispatch", description="Dispatch exactly one downstream action using its separately issued user confirmation.", risk=CapabilityRisk.WRITE, confirmation="none", **common), provider.dispatch),
        (CapabilitySpec(id="simulation.capture_run.cancel", description="Cancel unstarted capture steps and reconcile active work.", risk=CapabilityRisk.WRITE, confirmation="user", **common), provider.cancel),
        (CapabilitySpec(id="simulation.capture_step.retry", description="Retry one proven-failed capture step with a new attempt.", risk=CapabilityRisk.WRITE, confirmation="user", **common), provider.retry),
    )


__all__ = ["CaptureRunProvider", "SqlCaptureWorkflowRepository", "default_provider", "specs"]

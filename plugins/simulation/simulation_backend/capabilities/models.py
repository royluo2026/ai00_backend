"""Immutable inputs, reproducible environments and asynchronous Simulation runs."""
from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any, Mapping

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilityOutput, CapabilitySpec, EvidenceRef
from backend.domain_ports.simulation import ExecutionPlanRef, ParameterSetRef, SimulationProfileRef
from backend.domain_ports.versioned_resources import versioned_resource_resolvers

from ..data.connection import get_simulation_conn


def _canonical(value: Any) -> tuple[str, str]:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest(), encoded.decode("utf-8")


def _loads(value: Any, default: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return default
    return value if value is not None else default


def _pairs(value: Any, *, value_key: str) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        return [{"name": str(key), value_key: item} for key, item in sorted(value.items())]
    return [dict(item) for item in (value or ())]


class RegisteredSourceResolver:
    def resolve_execution_plan(self, ref: Mapping[str, Any], context: CapabilityContext) -> dict[str, Any]:
        try:
            return versioned_resource_resolvers.resolve("craft.execution_plan", ref, context)
        except LookupError as exc:
            raise CapabilityBusinessError("source_resolver_unavailable", str(exc)) from exc

    def resolve_model_snapshot(self, ref: Mapping[str, Any], context: CapabilityContext) -> dict[str, Any]:
        try:
            return versioned_resource_resolvers.resolve("digital_model.snapshot", ref, context)
        except LookupError as exc:
            raise CapabilityBusinessError("source_resolver_unavailable", str(exc)) from exc


class SimulationRepository:
    def create_parameter_set(self, row: Mapping[str, Any]) -> None:
        with get_simulation_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO workmanship_sim_parameter_sets (parameter_set_id,version,name,content_hash,parameters_json,owner_gid,team_gid,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,NOW())",
                    (row["parameter_set_id"], row["version"], row["name"], row["content_hash"], row["parameters_json"], row["owner_gid"], row.get("team_gid")),
                )

    def get_parameter_set(self, ref: Mapping[str, Any], context: CapabilityContext) -> dict[str, Any] | None:
        with get_simulation_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT parameter_set_id,version,name,content_hash,parameters_json FROM workmanship_sim_parameter_sets WHERE parameter_set_id=%s AND version=%s AND content_hash=%s AND (owner_gid=%s OR (%s IS NOT NULL AND team_gid=%s))",
                    (ref["parameter_set_id"], ref["version"], ref["content_hash"], context.user_gid, context.team_gid, context.team_gid),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def create_profile(self, row: Mapping[str, Any]) -> None:
        with get_simulation_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO workmanship_sim_profiles (profile_id,version,name,solver,solver_version,content_hash,settings_json,owner_gid,team_gid,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())",
                    (row["profile_id"], row["version"], row["name"], row["solver"], row["solver_version"], row["content_hash"], row["settings_json"], row["owner_gid"], row.get("team_gid")),
                )

    def get_profile(self, ref: Mapping[str, Any], context: CapabilityContext) -> dict[str, Any] | None:
        with get_simulation_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT profile_id,version,name,solver,solver_version,content_hash,settings_json FROM workmanship_sim_profiles WHERE profile_id=%s AND version=%s AND content_hash=%s AND (owner_gid=%s OR (%s IS NOT NULL AND team_gid=%s))",
                    (ref["profile_id"], ref["version"], ref["content_hash"], context.user_gid, context.team_gid, context.team_gid),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def create_environment(self, row: Mapping[str, Any]) -> None:
        source = row["source"]
        craft = source["execution_plan"]
        with get_simulation_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO workmanship_sim_environments (gid,name,status,owner_gid,team_gid,source_bop_version_gid,source_bop_revision,source_bop_hash,execution_plan_snapshot_uri,pinned_source,source_fingerprint,created_at,updated_at) VALUES (%s,%s,'draft',%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())",
                    (row["environment_id"], row["name"], row["owner_gid"], row.get("team_gid"), craft["version_gid"], craft["revision"], str(craft["content_hash"]).removeprefix("sha256:"), craft["craft_commit_ref"], json.dumps(source, ensure_ascii=False, sort_keys=True), source["source_fingerprint"]),
                )

    def get_environment(self, environment_id: str, context: CapabilityContext) -> dict[str, Any] | None:
        with get_simulation_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT gid AS environment_id,name,status,pinned_source AS source,source_fingerprint FROM workmanship_sim_environments WHERE gid=%s AND (owner_gid=%s OR (%s IS NOT NULL AND team_gid=%s))", (environment_id, context.user_gid, context.team_gid, context.team_gid))
                row = cur.fetchone()
        if row:
            row = dict(row); row["source"] = _loads(row.get("source"), {})
        return row

    def list_environments(self, limit: int, context: CapabilityContext) -> list[dict[str, Any]]:
        with get_simulation_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT gid AS environment_id,name,status,pinned_source AS source,source_fingerprint FROM workmanship_sim_environments WHERE owner_gid=%s OR (%s IS NOT NULL AND team_gid=%s) ORDER BY updated_at DESC LIMIT %s", (context.user_gid, context.team_gid, context.team_gid, limit))
                rows = [dict(row) for row in cur.fetchall()]
        for row in rows: row["source"] = _loads(row.get("source"), {})
        return rows

    def create_run(self, row: Mapping[str, Any]) -> None:
        source = row["source"]
        with get_simulation_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO workmanship_sim_runs (run_id,environment_id,operation_id,status,source_fingerprint,craft_commit_ref,model_snapshot_hash,parameter_set_id,parameter_version,profile_id,profile_version,solver,solver_version,pinned_source,result_artifact_refs,owner_gid,team_gid,created_at,updated_at) VALUES (%s,%s,%s,'queued',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'[]',%s,%s,NOW(),NOW())",
                    (
                        row["run_id"], row["environment_id"], row["operation_ref"]["operation_id"], row["source_fingerprint"],
                        source["execution_plan"]["craft_commit_ref"], source["model_snapshot"]["snapshot_hash"],
                        source["parameter_set"]["parameter_set_id"], source["parameter_set"]["version"],
                        source["simulation_profile"]["profile_id"], source["simulation_profile"]["version"],
                        source["simulation_profile"]["solver"], source["simulation_profile"]["solver_version"],
                        json.dumps(source, ensure_ascii=False, sort_keys=True), row["owner_gid"], row.get("team_gid"),
                    ),
                )

    def get_run(self, run_id: str, context: CapabilityContext) -> dict[str, Any] | None:
        with get_simulation_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT run_id,environment_id,operation_id,status,source_fingerprint,pinned_source AS source,result_artifact_refs FROM workmanship_sim_runs WHERE run_id=%s AND (owner_gid=%s OR (%s IS NOT NULL AND team_gid=%s))", (run_id, context.user_gid, context.team_gid, context.team_gid))
                row = cur.fetchone()
        if row:
            row = dict(row); row["source"] = _loads(row.get("source"), {}); row["result_artifact_refs"] = _loads(row.get("result_artifact_refs"), [])
        return row


repository = SimulationRepository()
source_resolver = RegisteredSourceResolver()


def _parameter(row: Mapping[str, Any]) -> dict[str, Any]:
    parameters = _pairs(_loads(row.get("parameters_json", row.get("parameters", row.get("values", []))), []), value_key="value")
    return {"parameter_set_ref": {"parameter_set_id": str(row["parameter_set_id"]), "version": int(row["version"]), "content_hash": str(row["content_hash"])}, "name": str(row.get("name") or row["parameter_set_id"]), "parameters": parameters}


def _profile(row: Mapping[str, Any]) -> dict[str, Any]:
    settings = _pairs(_loads(row.get("settings_json", row.get("settings", [])), []), value_key="value")
    return {"simulation_profile_ref": {"profile_id": str(row["profile_id"]), "version": int(row["version"]), "content_hash": str(row["content_hash"])}, "name": str(row.get("name") or row["profile_id"]), "solver": str(row["solver"]), "solver_version": str(row["solver_version"]), "settings": settings}


def _verified_source(value: Mapping[str, Any]) -> dict[str, Any]:
    source = dict(value)
    stored = str(source.pop("source_fingerprint", ""))
    actual, _ = _canonical(source)
    if stored != actual:
        raise CapabilityBusinessError(
            "source_version_mismatch", "Simulation source fingerprint does not match its pinned inputs",
            details={"stored_fingerprint": stored, "actual_fingerprint": actual},
        )
    return {**source, "source_fingerprint": stored}


def create_parameter_set(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    parameters = sorted((dict(item) for item in payload["parameters"]), key=lambda item: item["name"])
    content_hash, parameters_json = _canonical(parameters)
    row = {"parameter_set_id": "sps_" + secrets.token_hex(16), "version": 1, "name": str(payload["name"]).strip(), "content_hash": content_hash, "parameters": parameters, "parameters_json": parameters_json, "owner_gid": context.user_gid, "team_gid": context.team_gid}
    repository.create_parameter_set(row)
    data = _parameter(row)
    return CapabilityOutput(data=data, evidence=(EvidenceRef(kind="simulation.parameter_set", reference=f"simulation://parameter-set/{row['parameter_set_id']}/v1", digest=content_hash),))


def get_parameter_set(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    ref = ParameterSetRef.model_validate(payload["parameter_set_ref"]).model_dump(mode="json")
    row = repository.get_parameter_set(ref, context)
    if not row: raise CapabilityBusinessError("parameter_set_not_found", "Simulation parameter set not found")
    return CapabilityOutput(data=_parameter(row))


def create_profile(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    settings = sorted((dict(item) for item in payload["settings"]), key=lambda item: item["name"])
    content_hash, settings_json = _canonical({"solver": payload["solver"], "solver_version": payload["solver_version"], "settings": settings})
    row = {"profile_id": "spf_" + secrets.token_hex(16), "version": 1, "name": str(payload["name"]).strip(), "solver": str(payload["solver"]), "solver_version": str(payload["solver_version"]), "content_hash": content_hash, "settings": settings, "settings_json": settings_json, "owner_gid": context.user_gid, "team_gid": context.team_gid}
    repository.create_profile(row)
    data = _profile(row)
    return CapabilityOutput(data=data, evidence=(EvidenceRef(kind="simulation.profile", reference=f"simulation://profile/{row['profile_id']}/v1", digest=content_hash),))


def get_profile(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    ref = SimulationProfileRef.model_validate(payload["simulation_profile_ref"]).model_dump(mode="json")
    row = repository.get_profile(ref, context)
    if not row: raise CapabilityBusinessError("simulation_profile_not_found", "Simulation profile not found")
    return CapabilityOutput(data=_profile(row))


def create_environment(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    execution_ref = ExecutionPlanRef.model_validate(payload["execution_plan_ref"]).model_dump(mode="json")
    execution = source_resolver.resolve_execution_plan(execution_ref, context)
    model_ref = dict(payload["model_snapshot_ref"])
    model = source_resolver.resolve_model_snapshot(model_ref, context)
    parameter_row = repository.get_parameter_set(dict(payload["parameter_set_ref"]), context)
    profile_row = repository.get_profile(dict(payload["simulation_profile_ref"]), context)
    if not parameter_row: raise CapabilityBusinessError("parameter_set_not_found", "Simulation parameter set not found")
    if not profile_row: raise CapabilityBusinessError("simulation_profile_not_found", "Simulation profile not found")
    parameter, profile = _parameter(parameter_row), _profile(profile_row)
    source_without_hash = {"execution_plan": execution, "model_snapshot": model, "parameter_set": {**parameter["parameter_set_ref"], "parameters": parameter["parameters"]}, "simulation_profile": {**profile["simulation_profile_ref"], "solver": profile["solver"], "solver_version": profile["solver_version"], "settings": profile["settings"]}}
    fingerprint, _ = _canonical(source_without_hash)
    source = {**source_without_hash, "source_fingerprint": fingerprint}
    row = {"environment_id": "senv_" + secrets.token_hex(16), "name": str(payload["name"]).strip(), "status": "draft", "source": source, "owner_gid": context.user_gid, "team_gid": context.team_gid}
    repository.create_environment(row)
    data = {key: row[key] for key in ("environment_id", "name", "status", "source")}
    return CapabilityOutput(data=data, evidence=(EvidenceRef(kind="simulation.environment", reference=f"simulation://environment/{row['environment_id']}", digest=fingerprint),))


def get_environment(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    row = repository.get_environment(str(payload["environment_id"]), context)
    if not row: raise CapabilityBusinessError("simulation_environment_not_found", "Simulation environment not found")
    return CapabilityOutput(data={key: row[key] for key in ("environment_id", "name", "status", "source")})


def list_environments(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    rows = repository.list_environments(max(1, min(int(payload.get("limit") or 50), 200)), context)
    items = [{key: row[key] for key in ("environment_id", "name", "status", "source")} for row in rows]
    return CapabilityOutput(data={"items": items, "total": len(items)})


def _run(row: Mapping[str, Any]) -> dict[str, Any]:
    source = _verified_source(row["source"]); execution = source["execution_plan"]; model = source["model_snapshot"]; parameter = source["parameter_set"]; profile = source["simulation_profile"]
    operation_id = str(row.get("operation_id") or row["operation_ref"]["operation_id"])
    return {"run_id": str(row["run_id"]), "environment_id": str(row["environment_id"]), "status": str(row["status"]), "source_fingerprint": str(row["source_fingerprint"]), "craft_commit_ref": str(execution["craft_commit_ref"]), "model_snapshot_hash": str(model["snapshot_hash"]), "parameter_version": int(parameter["version"]), "solver_version": str(profile["solver_version"]), "operation_ref": {"operation_id": operation_id, "status": "accepted" if row["status"] == "queued" else str(row["status"]), "version": 1}}


def start_run(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    environment = repository.get_environment(str(payload["environment_id"]), context)
    if not environment: raise CapabilityBusinessError("simulation_environment_not_found", "Simulation environment not found")
    source = _verified_source(environment["source"])
    operation_id = str(getattr(context, "operation_id", None) or ("op_" + secrets.token_hex(16)))
    row = {"run_id": operation_id, "environment_id": environment["environment_id"], "status": "queued", "source_fingerprint": source["source_fingerprint"], "source": source, "operation_ref": {"operation_id": operation_id, "status": "accepted", "version": 1}, "owner_gid": context.user_gid, "team_gid": context.team_gid}
    repository.create_run(row)
    data = _run(row)
    return CapabilityOutput(data=data, evidence=(EvidenceRef(kind="simulation.run", reference=f"simulation://run/{row['run_id']}", digest=row["source_fingerprint"]),))


def get_run(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    row = repository.get_run(str(payload["run_id"]), context)
    if not row: raise CapabilityBusinessError("simulation_run_not_found", "Simulation run not found")
    return CapabilityOutput(data=_run(row))


def get_result(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    row = repository.get_run(str(payload["run_id"]), context)
    if not row: raise CapabilityBusinessError("simulation_run_not_found", "Simulation run not found")
    artifacts = list(row.get("result_artifact_refs") or ())
    if row["status"] != "completed" or not artifacts: raise CapabilityBusinessError("simulation_result_not_ready", "Simulation result is not ready", retryable=True)
    return CapabilityOutput(data={"run_id": row["run_id"], "status": row["status"], "source_fingerprint": row["source_fingerprint"], "result_artifact_refs": artifacts}, evidence=tuple(EvidenceRef(kind="simulation.result", reference=f"artifact:{item['artifact_id']}", digest="sha256:" + item["sha256"]) for item in artifacts))


def specs() -> tuple[tuple[CapabilitySpec, Any], ...]:
    common = {"owner": "simulation", "plugin_callable": True, "permissions": ("simulation.use",), "tags": ("simulation",)}
    return (
        (CapabilitySpec(id="simulation.parameter_set.create", description="Create an immutable Simulation parameter set.", risk="write", confirmation="user", **common), create_parameter_set),
        (CapabilitySpec(id="simulation.parameter_set.get", description="Read an immutable Simulation parameter set.", **common), get_parameter_set),
        (CapabilitySpec(id="simulation.profile.create", description="Create an immutable solver profile.", risk="write", confirmation="user", **common), create_profile),
        (CapabilitySpec(id="simulation.profile.get", description="Read an immutable solver profile.", **common), get_profile),
        (CapabilitySpec(id="simulation.environment.create", description="Create a reproducible environment from four immutable references.", risk="write", confirmation="user", **common), create_environment),
        (CapabilitySpec(id="simulation.environment.get", description="Read a reproducible Simulation environment.", **common), get_environment),
        (CapabilitySpec(id="simulation.environment.list", description="List visible Simulation environments.", **common), list_environments),
        (CapabilitySpec(id="simulation.run.start", description="Queue a Simulation run with exact pinned inputs.", risk="write", confirmation="user", idempotent=False, **common), start_run),
        (CapabilitySpec(id="simulation.run.get", description="Read Simulation run state and pinned versions.", **common), get_run),
        (CapabilitySpec(id="simulation.result.get", description="Read completed Simulation result ArtifactRefs.", **common), get_result),
    )


__all__ = ["repository", "source_resolver", "specs"]

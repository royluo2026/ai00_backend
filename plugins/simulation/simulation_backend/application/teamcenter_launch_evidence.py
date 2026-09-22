"""Validate persisted Teamcenter launch evidence; never trust Renderer launch claims."""
from datetime import UTC, datetime, timedelta
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.contracts.connector_execution_plan_v2 import ConnectorExecutionPlanV2, canonicalize_v2
from .connector_protocol_v2 import OutcomeVerifier
from .live_document_identity import NativeDocumentIdentity

LAUNCH_CAPABILITY = "simulation.teamcenter.visualization.launch.request"
LAUNCH_OPERATION = "teamcenter.visualization.launch@1"
LAUNCH_CONTRACT_HASH = "sha256:d74338b54d5abd84dad3435768aa56756ef4fbb560f1d605b2b1bb9cc18519a8"
FRESHNESS = timedelta(seconds=120)
OPENED_SOURCE_CONTRACT_HASH = 'sha256:807ebf90b7f92d994a1da3963c459191750fb21ca8890a096e3bb04d398e407a'


class TeamcenterLaunchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    launch_id: str = Field(pattern=r"^tclaunch:[0-9a-f]{64}$")
    runner_started: bool
    expected_visdoc_uid: str
    source_identity_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class TeamcenterOpenedSourceResult(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    protocol: Literal['ai00.viewer.opened-source.v1']
    launch: TeamcenterLaunchResult
    document_identity: NativeDocumentIdentity


def _utc(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _json(value):
    return json.loads(value) if isinstance(value, str) else value


def launch_only_plan(plan: ConnectorExecutionPlanV2, *, opened_source=False) -> bool:
    if not (
        plan.capability_id == LAUNCH_CAPABILITY
        and plan.major_version == (2 if opened_source else 1)
        and len(plan.steps) == 1
        and plan.adapter_id == "ai00.vismockup"
        and plan.adapter_major == 1
        and plan.target_product.product_id == "siemens.vismockup"
    ):
        return False
    step = plan.steps[0]
    payload = step.payload
    selector = payload.get("source_selector") if isinstance(payload, dict) else None
    return (
        step.operation_id == ('teamcenter.visualization.launch@2' if opened_source else LAUNCH_OPERATION)
        and step.contract_hash == (OPENED_SOURCE_CONTRACT_HASH if opened_source else LAUNCH_CONTRACT_HASH)
        and step.side_effect_classification == "write"
        and step.post_condition_probe_id == "vismockup.application.probe@1"
        and set(payload) == {"source_selector", "expected_visdoc_uid"}
        and isinstance(payload.get("expected_visdoc_uid"), str)
        and isinstance(selector, dict)
        and set(selector) == {
            "endpoint_id", "object_uid", "item_revision_uid", "bom_view_uid",
            "revision_rule", "configuration_date",
        }
        and all(isinstance(value, str) for value in selector.values())
    )


def verify_teamcenter_launch_evidence(row, runtime, *, actor_id: str, tenant_id: str, now) -> dict:
    return _verify_launch(row, runtime, actor_id=actor_id, tenant_id=tenant_id, now=now, opened_source=False)


def verify_teamcenter_opened_source_evidence(row, runtime, *, actor_id: str, tenant_id: str, now) -> dict:
    return _verify_launch(row, runtime, actor_id=actor_id, tenant_id=tenant_id, now=now, opened_source=True)


def _verify_launch(row, runtime, *, actor_id, tenant_id, now, opened_source):
    """Fail-closed verification of one owner-scoped signed launch outcome."""
    try:
        if not row or not runtime or not actor_id or not tenant_id:
            raise ValueError("launch_evidence_unavailable")
        plan = ConnectorExecutionPlanV2.model_validate(_json(row["plan_json"]))
        outcome = OutcomeVerifier.verify(_json(row["outcome_json"]), _json(runtime["device_signing_jwk"]))
        OutcomeVerifier.verify_steps(plan, outcome)
        if not launch_only_plan(plan, opened_source=opened_source) or row["status"] != "succeeded" or outcome.overall_status != "succeeded":
            raise ValueError("launch_evidence_unavailable")
        if (plan.actor_id, row["actor_gid"], runtime["owner_user_gid"]) != (actor_id,) * 3:
            raise ValueError("launch_evidence_unavailable")
        if (plan.tenant_id, outcome.tenant_id, row["tenant_gid"], runtime["tenant_gid"]) != (tenant_id,) * 4:
            raise ValueError("launch_evidence_unavailable")
        for field in ("device_id", "runtime_generation", "runtime_instance_id"):
            runtime_field = "current_runtime_instance_id" if field == "runtime_instance_id" else field
            if not (getattr(plan, field) == getattr(outcome, field) == row[field] == runtime[runtime_field]):
                raise ValueError("launch_evidence_unavailable")
        if (
            row["protocol"] != plan.protocol
            or runtime["protocol"] != plan.protocol
            or runtime["runtime_type"] != "electron"
            or runtime["status"] != "active"
            or not runtime["session_token_hash"]
            or row["session_token_hash"] != runtime["session_token_hash"]
            or outcome.device_key_id != runtime["device_key_id"]
            or not (plan.plan_id == outcome.plan_id == row["plan_id"])
            or not (plan.plan_hash == outcome.plan_hash == row["plan_hash"])
            or outcome.lease_id != row["lease_id"]
            or hashlib.sha256(canonicalize_v2(outcome)).hexdigest() != row["outcome_hash"]
        ):
            raise ValueError("launch_evidence_unavailable")
        now, receipt = _utc(now), _utc(row["updated_at"])
        started, completed = _utc(outcome.steps[0].started_at), _utc(outcome.steps[0].completed_at)
        reported = _utc(outcome.reported_at)
        if not (
            now - FRESHNESS <= receipt <= now
            and now - FRESHNESS <= started <= completed <= reported <= receipt
            and _utc(plan.issued_at) <= started <= completed <= _utc(plan.expires_at)
            and receipt <= _utc(row["lease_until"])
            and now < _utc(runtime["session_expires_at"])
            and now - FRESHNESS <= _utc(runtime["heartbeat_at"]) <= now
        ):
            raise ValueError("launch_evidence_stale")
        receipt = TeamcenterOpenedSourceResult.model_validate(outcome.steps[0].result) if opened_source else None
        result = receipt.launch if receipt else TeamcenterLaunchResult.model_validate(outcome.steps[0].result)
        expected_source_hash = "sha256:" + hashlib.sha256(
            canonicalize_v2(plan.steps[0].payload["source_selector"])
        ).hexdigest()
        if not result.runner_started or result.source_identity_hash != expected_source_hash:
            raise ValueError("launch_evidence_unavailable")
        verified = {
            "connector_device_id": plan.device_id,
            "source_identity_hash": result.source_identity_hash,
            "launch_id": result.launch_id,
        }
        if receipt:
            identity = receipt.document_identity
            expected_session = 'sha256:' + hashlib.sha256(canonicalize_v2(
                identity.model_dump(exclude={'document_session'}))).hexdigest()
            if identity.document_session != expected_session or not identity.document_handle.strip():
                raise ValueError('opened_source_identity_invalid')
            verified.update(document_session=identity.document_session,
                runtime_instance_id=plan.runtime_instance_id, runtime_generation=plan.runtime_generation)
        return verified
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("launch_evidence_unavailable") from exc

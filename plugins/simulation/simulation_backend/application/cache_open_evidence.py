"""Attest exactly one admitted frozen-cache package open in the current runtime."""
from typing import Literal
import hashlib
from pydantic import BaseModel, ConfigDict, Field
from backend.contracts.connector_execution_plan_v2 import ConnectorExecutionPlanV2, canonicalize_v2
from .connector_protocol_v2 import OutcomeVerifier
from .live_document_identity import NativeDocumentIdentity
from .teamcenter_launch_evidence import _utc, _json, FRESHNESS

CACHE_OPEN_CONTRACT_HASH = 'sha256:ffa45d329b0d9f88358b7f0846670c3120992614b4eda0b8d6ddfe76bb8b1eec'

class CacheBinding(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    batch_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    generation: str | None = Field(pattern=r'^[0-9a-f]{32}$')
    snapshot_hash: str | None = Field(pattern=r'^sha256:[0-9a-f]{64}$')
    schema_version: Literal[1]

class ArtifactRef(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    artifact_id: str = Field(min_length=1)
    media_type: Literal['model/jt', 'model/plmxml', 'application/vnd.siemens.plmxml+xml', 'model/step', 'image/png']
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    byte_size: int = Field(ge=0)
    version: int = Field(ge=1)

class PackageDependency(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    package_path: str = Field(pattern=r'^dependencies/[A-Za-z0-9_.-]+[.]jt$')
    artifact_ref: ArtifactRef

class CacheOpenPayload(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    artifact_ref: ArtifactRef
    package_dependencies: list[PackageDependency] = Field(default_factory=list, max_length=10000)
    cache_binding: CacheBinding
    package_hash: str = Field(pattern=r'^sha256:[0-9a-f]{64}$')

def cache_package_hash(package):
    return 'sha256:' + hashlib.sha256(canonicalize_v2(package)).hexdigest()

class OpenedCacheResult(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    protocol: Literal['ai00.viewer.opened-cache.v1']
    cache_binding: CacheBinding
    package_hash: str = Field(pattern=r'^sha256:[0-9a-f]{64}$')
    artifact_ref: ArtifactRef
    document_identity: NativeDocumentIdentity

def cache_only_plan(plan):
    if not (plan.capability_id == 'simulation.environment.cache_source.open.request'
        and plan.major_version == 1 and len(plan.steps) == 1
        and plan.adapter_id == 'ai00.vismockup' and plan.adapter_major == 1
        and plan.target_product.product_id == 'siemens.vismockup'):
        return False
    step = plan.steps[0]
    payload = step.payload
    if step.operation_id=='vismockup.model.open@3':
        from .cache_tc_open_contract import TC_OPEN_CONTRACT_HASH,TcCacheOpenPayload
        TcCacheOpenPayload.model_validate(payload)
        return (step.contract_hash==TC_OPEN_CONTRACT_HASH and step.side_effect_classification=='write'
            and step.post_condition_probe_id=='vismockup.application.probe@1')
    return (step.operation_id == 'vismockup.model.open@2'
        and step.contract_hash == CACHE_OPEN_CONTRACT_HASH
        and step.side_effect_classification == 'write'
        and step.post_condition_probe_id == 'vismockup.application.probe@1'
        and {'artifact_ref', 'cache_binding', 'package_hash'} <= set(payload)
        and set(payload) <= {'artifact_ref', 'cache_binding', 'package_hash', 'package_dependencies'}
        and isinstance(payload['artifact_ref'], dict)
        and isinstance(payload.get('package_dependencies', []), list))

def verify_cache_open_evidence(row, runtime, *, actor_id, tenant_id, now):
    try:
        if not row or not runtime or not actor_id or not tenant_id:
            raise ValueError("cache_open_evidence_unavailable")
        plan = ConnectorExecutionPlanV2.model_validate(_json(row["plan_json"]))
        outcome = OutcomeVerifier.verify(_json(row["outcome_json"]), _json(runtime["device_signing_jwk"]))
        OutcomeVerifier.verify_steps(plan, outcome)
        if not cache_only_plan(plan) or row["status"] != "succeeded" or outcome.overall_status != "succeeded":
            raise ValueError("cache_open_evidence_unavailable")
        if (plan.actor_id, row["actor_gid"], runtime["owner_user_gid"]) != (actor_id,) * 3:
            raise ValueError("cache_open_evidence_unavailable")
        if (plan.tenant_id, outcome.tenant_id, row["tenant_gid"], runtime["tenant_gid"]) != (tenant_id,) * 4:
            raise ValueError("cache_open_evidence_unavailable")
        for field in ("device_id", "runtime_generation", "runtime_instance_id"):
            runtime_field = "current_runtime_instance_id" if field == "runtime_instance_id" else field
            if not (getattr(plan, field) == getattr(outcome, field) == row[field] == runtime[runtime_field]):
                raise ValueError("cache_open_evidence_unavailable")
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
            raise ValueError("cache_open_evidence_unavailable")
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
            raise ValueError("cache_open_evidence_stale")
        local=plan.steps[0].operation_id=='vismockup.model.open@3'
        if local:
            from .cache_tc_open_contract import TcCacheOpenPayload,OpenedTcCacheResult
            payload=TcCacheOpenPayload.model_validate(plan.steps[0].payload).model_dump()
            receipt=OpenedTcCacheResult.model_validate(outcome.steps[0].result)
            package_hash=cache_package_hash({k:v for k,v in payload.items() if k!='package_hash'})
            expected={d['file_ref']['dependency_key'] for d in payload['tc_dependencies']}
            actual=[f.dependency_key for f in receipt.files]
            if (payload['package_hash']!=package_hash or receipt.package_hash!=package_hash
                    or receipt.cache_binding.model_dump()!=payload['cache_binding'] or set(actual)!=expected or len(actual)!=len(expected)):
                raise ValueError('cache_open_package_mismatch')
            package=dict(cache_binding=payload['cache_binding'],tc_open_payload=payload)
        else:
            receipt = OpenedCacheResult.model_validate(outcome.steps[0].result)
            payload = CacheOpenPayload.model_validate(plan.steps[0].payload).model_dump()
            binding = CacheBinding.model_validate(payload['cache_binding']).model_dump()
            package = dict(artifact_ref=payload['artifact_ref'],
                package_dependencies=payload.get('package_dependencies', []), cache_binding=binding)
            package_hash = cache_package_hash(package)
            if (payload['package_hash'] != package_hash or receipt.package_hash != package_hash
                or receipt.cache_binding.model_dump() != binding or receipt.artifact_ref.model_dump() != package['artifact_ref']):
                raise ValueError('cache_open_package_mismatch')
        identity = receipt.document_identity
        expected_session = 'sha256:' + hashlib.sha256(canonicalize_v2(
            identity.model_dump(exclude={'document_session'}))).hexdigest()
        if identity.document_session != expected_session or not identity.document_handle.strip():
            raise ValueError('cache_open_identity_invalid')
        return dict(connector_device_id=plan.device_id, document_session=identity.document_session,
            runtime_instance_id=plan.runtime_instance_id, runtime_generation=plan.runtime_generation,
            source_identity_hash=package_hash, package_hash=package_hash, **package)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError('cache_open_evidence_unavailable') from exc

def locked_cache_open_evidence(cursor, operation_id, *, actor_id, tenant_id, now):
    from ..data.connector_repository import SimulationConnectorRepository, ConnectorRepositoryError
    cursor.execute('SELECT * FROM workmanship_sim_connector_runtime_plans '
        'WHERE plan_id=%s AND actor_gid=%s AND tenant_gid=%s AND protocol=%s',
        (operation_id, actor_id, tenant_id, 'ai00.connector.execution-plan.v2'))
    row = cursor.fetchone()
    if not row:
        raise ConnectorRepositoryError('cache_open_evidence_unavailable')
    runtime = SimulationConnectorRepository._locked_runtime(cursor, row['device_id'])
    cursor.execute('SELECT * FROM workmanship_sim_connector_runtime_plans WHERE plan_id=%s FOR UPDATE', (operation_id,))
    row = cursor.fetchone()
    try:
        return verify_cache_open_evidence(row, runtime, actor_id=actor_id, tenant_id=tenant_id, now=now)
    except ValueError as exc:
        raise ConnectorRepositoryError('cache_open_evidence_unavailable') from exc

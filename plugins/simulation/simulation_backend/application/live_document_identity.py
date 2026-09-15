"""Validate persisted native identity evidence; never accept Renderer identity JSON."""
from datetime import UTC, datetime, timedelta
import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field
from backend.contracts.connector_execution_plan_v2 import ConnectorExecutionPlanV2, canonicalize_v2
from .connector_protocol_v2 import OutcomeVerifier

IDENTITY_CAPABILITY = 'simulation.vismockup.document.identity.read.request'
IDENTITY_OPERATION = 'vismockup.document.identity.read@1'
IDENTITY_CONTRACT_HASH = 'sha256:2a8b6e89d3a13cf35b0584a989ed79977700d3cd3fe9fcc918c3b871d1c8c4d7'
HIERARCHY_INVENTORY_CAPABILITY = 'simulation.vismockup.document.hierarchy_inventory.read.request'
HIERARCHY_INVENTORY_OPERATION = 'vismockup.document.hierarchy_inventory.read@1'
HIERARCHY_INVENTORY_CONTRACT_HASH = 'sha256:a89bdc3fbb04ee643f1434dee83c653df8a04fc406ac7fff1e61ce39ee99685a'
FRESHNESS = timedelta(seconds=120)


class NativeDocumentIdentity(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    document_session: str = Field(pattern=r'^sha256:[0-9a-f]{64}$')
    process_id: int = Field(gt=0)
    process_started_utc_ticks: str = Field(pattern=r'^[1-9][0-9]*$')
    document_handle: str = Field(min_length=1)


def identity_only_plan(plan):
    return (plan.capability_id == IDENTITY_CAPABILITY and plan.major_version == 1
        and len(plan.steps) == 1 and plan.adapter_id == 'ai00.vismockup' and plan.adapter_major == 1
        and plan.target_product.product_id == 'siemens.vismockup'
        and plan.steps[0].operation_id == IDENTITY_OPERATION
        and plan.steps[0].contract_hash == IDENTITY_CONTRACT_HASH
        and plan.steps[0].payload == {} and plan.steps[0].side_effect_classification == 'read'
        and plan.steps[0].post_condition_probe_id is None)


def hierarchy_inventory_only_plan(plan):
    if not (plan.capability_id == HIERARCHY_INVENTORY_CAPABILITY and plan.major_version == 1
        and len(plan.steps) == 1 and plan.adapter_id == 'ai00.vismockup' and plan.adapter_major == 1
        and plan.target_product.product_id == 'siemens.vismockup'):
        return False
    step = plan.steps[0]
    payload = step.payload
    return (step.operation_id == HIERARCHY_INVENTORY_OPERATION
        and step.contract_hash == HIERARCHY_INVENTORY_CONTRACT_HASH
        and step.side_effect_classification == 'read' and step.post_condition_probe_id is None
        and set(payload) == {'document_session','start_index','page_size','max_nodes'}
        and isinstance(payload.get('document_session'), str)
        and isinstance(payload.get('start_index'), int) and payload['start_index'] >= 0
        and isinstance(payload.get('page_size'), int) and 1 <= payload['page_size'] <= 16
        and isinstance(payload.get('max_nodes'), int) and 1 <= payload['max_nodes'] <= 100000)


def evidence_only_plan(plan):
    return identity_only_plan(plan) or hierarchy_inventory_only_plan(plan)


def _utc(value):
    if isinstance(value, str): value = datetime.fromisoformat(value)
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _json(value):
    return json.loads(value) if isinstance(value, str) else value


def verify_identity_evidence(row, runtime, *, actor_id, tenant_id, now):
    """Bounded, fail-closed verification of server-owned plan/outcome/runtime rows."""
    try:
        if not row or not runtime or not actor_id or not tenant_id:
            raise ValueError('live_document_identity_unavailable')
        plan = ConnectorExecutionPlanV2.model_validate(_json(row['plan_json']))
        outcome = OutcomeVerifier.verify(_json(row['outcome_json']), _json(runtime['device_signing_jwk']))
        OutcomeVerifier.verify_steps(plan, outcome)
        if not identity_only_plan(plan) or row['status'] != 'succeeded' or outcome.overall_status != 'succeeded':
            raise ValueError('live_document_identity_unavailable')
        if (plan.actor_id, row['actor_gid'], runtime['owner_user_gid']) != (actor_id,) * 3:
            raise ValueError('live_document_identity_unavailable')
        if (plan.tenant_id, outcome.tenant_id, row['tenant_gid'], runtime['tenant_gid']) != (tenant_id,) * 4:
            raise ValueError('live_document_identity_unavailable')
        for field in ('device_id', 'runtime_generation', 'runtime_instance_id'):
            runtime_field = 'current_runtime_instance_id' if field == 'runtime_instance_id' else field
            if not (getattr(plan, field) == getattr(outcome, field) == row[field] == runtime[runtime_field]):
                raise ValueError('live_document_identity_unavailable')
        if (row['protocol'] != plan.protocol or runtime['protocol'] != plan.protocol
            or runtime['runtime_type'] != 'electron' or runtime['status'] != 'active'
            or not runtime['session_token_hash'] or row['session_token_hash'] != runtime['session_token_hash']
            or outcome.device_key_id != runtime['device_key_id']
            or not (plan.plan_id == outcome.plan_id == row['plan_id'])
            or not (plan.plan_hash == outcome.plan_hash == row['plan_hash'])
            or outcome.lease_id != row['lease_id']
            or hashlib.sha256(canonicalize_v2(outcome)).hexdigest() != row['outcome_hash']):
            raise ValueError('live_document_identity_unavailable')
        now, receipt = _utc(now), _utc(row['updated_at'])
        started, completed = _utc(outcome.steps[0].started_at), _utc(outcome.steps[0].completed_at)
        reported = _utc(outcome.reported_at)
        if not (now - FRESHNESS <= receipt <= now
            and now - FRESHNESS <= started <= completed <= reported <= receipt
            and _utc(plan.issued_at) <= started <= completed <= _utc(plan.expires_at)
            and receipt <= _utc(row['lease_until'])
            and now < _utc(runtime['session_expires_at'])
            and now - FRESHNESS <= _utc(runtime['heartbeat_at']) <= now):
            raise ValueError('live_document_identity_stale')
        identity = NativeDocumentIdentity.model_validate(outcome.steps[0].result)
        source = identity.model_dump(exclude={'document_session'})
        expected = 'sha256:' + hashlib.sha256(canonicalize_v2(source)).hexdigest()
        if identity.document_session != expected or not identity.document_handle.strip():
            raise ValueError('live_document_identity_unavailable')
        return dict(connector_device_id=plan.device_id, document_session=identity.document_session)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError('live_document_identity_unavailable') from exc

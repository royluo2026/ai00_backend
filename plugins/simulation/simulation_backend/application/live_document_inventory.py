"""Verify persisted, signed, bounded VisMockup hierarchy inventory evidence."""
from datetime import UTC, timedelta
import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field, model_validator
from backend.contracts.connector_execution_plan_v2 import ConnectorExecutionPlanV2, canonicalize_v2
from .connector_protocol_v2 import OutcomeVerifier
from .live_document_identity import FRESHNESS, hierarchy_inventory_only_plan


class InventoryNode(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    node_key: str = Field(min_length=1, max_length=4096)
    parent_key: str | None = Field(default=None, max_length=4096)
    child_order: int = Field(ge=0)
    name: str = Field(max_length=16384)
    occurrence_id: str = Field(max_length=4096)
    product_ref: str = Field(max_length=4096)


class InventoryHierarchy(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    native_index: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=16384)
    snapshot_hash: str = Field(pattern=r'^sha256:[0-9a-f]{64}$')
    nodes: list[InventoryNode] = Field(max_length=100000)
    complete: bool


class InventoryPage(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    document_session: str = Field(pattern=r'^sha256:[0-9a-f]{64}$')
    start_index: int = Field(ge=0)
    next_index: int | None = Field(default=None, ge=0)
    total_hierarchies: int = Field(ge=0)
    hierarchies: list[InventoryHierarchy] = Field(max_length=16)

    @model_validator(mode='after')
    def bounded(self):
        if sum(len(item.nodes) for item in self.hierarchies) > 100000:
            raise ValueError('live_document_inventory_unavailable')
        return self


def _utc(value):
    if isinstance(value, str): value = __import__('datetime').datetime.fromisoformat(value)
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _json(value):
    return json.loads(value) if isinstance(value, str) else value


def verify_hierarchy_inventory_evidence(row, runtime, *, actor_id, tenant_id, now):
    try:
        if not row or not runtime or not actor_id or not tenant_id:
            raise ValueError('live_document_inventory_unavailable')
        plan = ConnectorExecutionPlanV2.model_validate(_json(row['plan_json']))
        outcome = OutcomeVerifier.verify(_json(row['outcome_json']), _json(runtime['device_signing_jwk']))
        OutcomeVerifier.verify_steps(plan, outcome)
        if not hierarchy_inventory_only_plan(plan) or row['status'] != 'succeeded' or outcome.overall_status != 'succeeded':
            raise ValueError('live_document_inventory_unavailable')
        if (plan.actor_id, row['actor_gid'], runtime['owner_user_gid']) != (actor_id,) * 3:
            raise ValueError('live_document_inventory_unavailable')
        if (plan.tenant_id, outcome.tenant_id, row['tenant_gid'], runtime['tenant_gid']) != (tenant_id,) * 4:
            raise ValueError('live_document_inventory_unavailable')
        for field in ('device_id','runtime_generation','runtime_instance_id'):
            runtime_field = 'current_runtime_instance_id' if field == 'runtime_instance_id' else field
            if not (getattr(plan, field) == getattr(outcome, field) == row[field] == runtime[runtime_field]):
                raise ValueError('live_document_inventory_unavailable')
        if (row['protocol'] != plan.protocol or runtime['protocol'] != plan.protocol
            or runtime['runtime_type'] != 'electron' or runtime['status'] != 'active'
            or not runtime['session_token_hash'] or row['session_token_hash'] != runtime['session_token_hash']
            or outcome.device_key_id != runtime['device_key_id']
            or not (plan.plan_id == outcome.plan_id == row['plan_id'])
            or not (plan.plan_hash == outcome.plan_hash == row['plan_hash'])
            or outcome.lease_id != row['lease_id']
            or hashlib.sha256(canonicalize_v2(outcome)).hexdigest() != row['outcome_hash']):
            raise ValueError('live_document_inventory_unavailable')
        now, receipt = _utc(now), _utc(row['updated_at'])
        started, completed = _utc(outcome.steps[0].started_at), _utc(outcome.steps[0].completed_at)
        reported = _utc(outcome.reported_at)
        if not (now - FRESHNESS <= receipt <= now
            and now - FRESHNESS <= started <= completed <= reported <= receipt
            and _utc(plan.issued_at) <= started <= completed <= _utc(plan.expires_at)
            and receipt <= _utc(row['lease_until']) and now < _utc(runtime['session_expires_at'])
            and now - FRESHNESS <= _utc(runtime['heartbeat_at']) <= now):
            raise ValueError('live_document_inventory_stale')
        result = InventoryPage.model_validate(outcome.steps[0].result)
        request = plan.steps[0].payload
        if result.document_session != request['document_session'] or result.start_index != request['start_index']:
            raise ValueError('live_document_inventory_unavailable')
        if len(result.hierarchies) > request['page_size'] or sum(len(item.nodes) for item in result.hierarchies) > request['max_nodes']:
            raise ValueError('live_document_inventory_unavailable')
        return {'connector_device_id': plan.device_id, **result.model_dump()}
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError('live_document_inventory_unavailable') from exc

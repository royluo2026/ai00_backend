import hashlib
import json
from pathlib import Path

import jsonschema
import pytest

from backend.capability_v2.contracts import OperationRef, OperationStatus
from backend.capability_v2.provider_contracts import CapabilityBusinessError
from plugins.simulation.tests.test_live_document_capabilities import Connectors, Registry, context, NOW
from plugins.simulation.simulation_backend.capabilities.connector_runtime import (
    ConnectorControlPlane, DIRECT_VISMOCKUP_OPERATIONS, register_connector_runtime_capabilities,
)

REQUEST = 'simulation.teamcenter.product_structure.children.read.request'
ATOM = 'simulation.teamcenter.product_structure.children.read'
ROOT = Path(__file__).resolve().parents[3]


def payload():
    return dict(source_selector=dict(endpoint_id='tc-production', object_uid='root',
        item_revision_uid='', bom_view_uid='', revision_rule='Latest Working',
        configuration_date='2026-09-16T00:00:00Z'), parent_path=[], cursor=0,
        page_size=100, refresh=False, generation=None)


def registered():
    connectors = Connectors()
    control = ConnectorControlPlane(connectors, clock=lambda: NOW)
    queued = []
    control.queue_v2 = lambda plan, ctx, **kw: queued.append(plan) or OperationRef(
        operation_id=plan['plan_id'], status=OperationStatus.ACCEPTED)
    registry = Registry()
    register_connector_runtime_capabilities(registry, control)
    return registry.items, connectors, queued


def test_children_closed_schema_generation_and_atomic_contract_agree():
    items, _, _ = registered()
    schema = items[REQUEST][0].input_schema
    jsonschema.validate(payload(), schema)
    jsonschema.validate(dict(payload(), cursor=100, generation='pinned'), schema)
    for patch in ({'unknown': True}, {'page_size': 501}, {'cursor': 1},
                  {'generation': 'old'}, {'cursor': 1, 'generation': 'pinned', 'refresh': True},
                  {'parent_path': [{'occurrence_uid': 'edge', 'item_revision_uid': 'rev', 'uid': 'live'}]}):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(dict(payload(), **patch), schema)
    for key in payload():
        incomplete = payload(); del incomplete[key]
        with pytest.raises(jsonschema.ValidationError): jsonschema.validate(incomplete, schema)
    contract = json.loads((ROOT / 'docs/contracts/teamcenter.product_structure.children.read@1.json').read_text())
    assert schema == contract['input'] == items[ATOM][0].input_schema
    assert contract['output'] == items[ATOM][0].output_schema
    digest = 'sha256:' + hashlib.sha256(json.dumps(contract, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    assert DIRECT_VISMOCKUP_OPERATIONS['tc_children'] == (contract['id'], digest)


def test_children_queue_preserves_payload_and_requires_web_app_v2():
    items, connectors, queued = registered()
    spec, handler, descriptor = items[REQUEST]
    ctx = context().model_copy(update=dict(capability_version_gid='cv2_'+'a'*24,
        business_definition_hash='sha256:'+'b'*64, catalog_release='rel_test',
        request_id='request', idempotency_key='key', normalized_input_hash='sha256:'+'c'*64))
    handler(payload(), ctx)
    step = queued[0]['steps'][0]
    assert step['payload'] == payload()
    assert step['operation_id'] == 'teamcenter.product_structure.children.read@1'
    assert step['side_effect_classification'] == 'read'
    assert step['post_condition_probe_id'] is None
    assert spec.risk.value == 'read' and spec.confirmation == 'none'
    assert {k for k, v in descriptor.exposure.model_dump().items() if v} == {'web'}
    assert descriptor.resource_selectors
    assert 'direct children' in descriptor.business_effect
    with pytest.raises(CapabilityBusinessError): handler(payload(), ctx.model_copy(update={'source': 'agent'}))
    connectors.bound_runtime_for_user = lambda *_: None
    with pytest.raises(CapabilityBusinessError): handler(payload(), ctx)
    assert len(queued) == 1


def test_children_output_is_closed_partial_tree_with_unknown_child_disclosure():
    items, _, _ = registered()
    schema = items[ATOM][0].output_schema
    root = dict(occurrence_id='sha256:'+'a'*64, parent_occurrence_id=None,
        occurrence_path=[], depth=0, child_order=0, name='Root',
        item_revision_uid='rev', revision_id='01', component_type='Assembly', has_children=True)
    child = dict(root, occurrence_id='sha256:'+'b'*64,
        parent_occurrence_id=root['occurrence_id'],
        occurrence_path=[dict(occurrence_uid='edge', item_revision_uid='rev')],
        depth=1, has_children=None)
    page = dict(source_identity_hash='sha256:'+'c'*64, captured_at='2026-09-16T00:00:00Z',
        cache_hit=True, generation='d'*32, parent=root, nodes=[child], cursor=0,
        next_cursor=None, child_count=1, complete=False)
    jsonschema.validate(page, schema)
    for invalid in (dict(page, complete=True), dict(page, observation_id='full'),
                    dict(page, nodes=[dict(child, geometry_refs=[])])):
        with pytest.raises(jsonschema.ValidationError): jsonschema.validate(invalid, schema)

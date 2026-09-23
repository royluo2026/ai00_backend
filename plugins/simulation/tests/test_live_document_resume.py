"""An opened Teamcenter model can regain local authority after Connector restart without relaunch."""
import hashlib
import json
import sqlite3
from datetime import timedelta

import pytest

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext
from backend.contracts.connector_execution_plan_v2 import canonicalize_v2
from plugins.simulation.tests.test_live_document_identity_evidence import evidence as identity_evidence
from plugins.simulation.tests.test_teamcenter_opened_source_evidence import seal
from plugins.simulation.tests.test_teamcenter_launch_evidence import NOW
from plugins.simulation.tests.test_viewer_opened_source_binding import database, opened, bind
from plugins.simulation.simulation_backend.capabilities.live_documents import LiveDocumentProvider


@pytest.fixture
def restarted(database, opened):
    bound = bind(opened)
    row, _ = identity_evidence()
    identity = opened['outcome_json']['steps'][0]['result']['document_identity']
    plan, outcome = row['plan_json'], row['outcome_json']
    row.update(plan_id='existing-identity', device_id=opened['device_id'], actor_gid='30', tenant_gid='20',
        runtime_instance_id='new-instance', runtime_generation=opened['runtime_generation'])
    plan.update(plan_id='existing-identity', capability_id='simulation.vismockup.document.existing_identity.read.request',
        device_id=opened['device_id'], actor_id='30', tenant_id='20', runtime_instance_id='new-instance',
        runtime_generation=opened['runtime_generation'])
    plan['steps'][0].update(operation_id='vismockup.document.existing_identity.read@1',
        contract_hash='sha256:9aa9528fff83c565d3d005daa1167b41cef2f6d413d485790c6c98c139fc1471',
        payload={'expected_document_session':bound['document_session']},
        payload_hash='sha256:' + hashlib.sha256(canonicalize_v2({'expected_document_session':bound['document_session']})).hexdigest())
    outcome.update(plan_id='existing-identity', tenant_id='20', runtime_instance_id='new-instance',
        runtime_generation=opened['runtime_generation'])
    outcome['steps'][0]['result'] = identity
    stamp=lambda value:value.strftime('%Y-%m-%dT%H:%M:%SZ')
    plan.update(issued_at=stamp(NOW-timedelta(seconds=5)), expires_at=stamp(NOW+timedelta(minutes=5)))
    outcome.update(reported_at=stamp(NOW-timedelta(seconds=1)))
    outcome['steps'][0].update(started_at=stamp(NOW-timedelta(seconds=3)),
        completed_at=stamp(NOW-timedelta(seconds=2)))
    row.update(updated_at=NOW,lease_until=NOW+timedelta(seconds=60))
    seal(row)
    with sqlite3.connect(database) as db:
        db.execute("UPDATE workmanship_sim_connector_runtime_devices SET current_runtime_instance_id='new-instance'")
        columns=list(row)
        db.execute('INSERT INTO workmanship_sim_connector_runtime_plans ('+','.join(columns)+') VALUES ('+
            ','.join('?' for _ in columns)+')',
            [json.dumps(row[key]) if isinstance(row[key],dict) else row[key].isoformat()
             if hasattr(row[key],'isoformat') else row[key] for key in columns])
    return bound


def resume(bound, **changes):
    payload=dict(workspace_gid='10',document_gid='11',identity_operation_id='existing-identity',
        expected_document_session=bound['document_session'],expected_workspace_row_version=2,
        idempotency_key='resume-1')
    return LiveDocumentProvider(object(),clock=lambda:NOW).resume_online(
        {**payload,**changes},CapabilityContext(user_gid='30',team_gid='20',source='web')).data


def test_resume_renews_only_source_association(database, restarted):
    result=resume(restarted)
    assert result['source_association_id'] != restarted['source_association_id']
    assert result['workspace_row_version'] == 2
    assert resume(restarted) == result
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT row_version FROM workmanship_sim_workspaces').fetchone()[0] == 2
        assert db.execute('SELECT COUNT(*) FROM workmanship_sim_live_document_bindings').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM workmanship_sim_viewer_source_associations WHERE active=1').fetchone()[0] == 1
        assert db.execute('SELECT runtime_instance_id FROM workmanship_sim_viewer_source_associations WHERE active=1').fetchone()[0] == 'new-instance'


@pytest.mark.parametrize('sql', [
    "UPDATE workmanship_sim_vm_documents SET content_sha256='changed'",
    "UPDATE workmanship_sim_live_document_bindings SET document_session='different'",
    "UPDATE workmanship_sim_viewer_source_associations SET source_revision='changed'",
    "UPDATE workmanship_sim_connector_runtime_devices SET current_runtime_instance_id='other'",
])
def test_resume_rejects_wrong_source_or_session(database, restarted, sql):
    with sqlite3.connect(database) as db: db.execute(sql)
    with pytest.raises(CapabilityBusinessError): resume(restarted)
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT COUNT(*) FROM workmanship_sim_viewer_source_associations').fetchone()[0] == 1

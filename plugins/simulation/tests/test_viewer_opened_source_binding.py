"""Exercise signed receipt verification and association/binding in one SQL transaction."""
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext
from plugins.simulation.tests.test_live_document_binding_repository import database, seed_teamcenter_online_workspace
from plugins.simulation.tests.test_teamcenter_opened_source_evidence import opened_evidence, seal
from plugins.simulation.tests.test_teamcenter_launch_evidence import NOW, SOURCE_HASH
from plugins.simulation.simulation_backend.capabilities.live_documents import LiveDocumentProvider


@pytest.fixture
def opened(database):
    row, runtime = opened_evidence()
    row.update(actor_gid='30', tenant_gid='20')
    row['plan_json'].update(actor_id='30', tenant_id='20')
    row['outcome_json']['tenant_id'] = '20'
    runtime.update(owner_user_gid='30', tenant_gid='20')
    seal(row)
    seed_teamcenter_online_workspace(database, content_sha256=SOURCE_HASH[7:])
    ddl = (Path(__file__).parents[3] / 'backend/db/migrations/domains/simulation/0028_viewer_interaction.sql').read_text()
    ddl = re.sub(r' CHARACTER SET \w+| COLLATE \w+', '', ddl)
    ddl = re.sub(r'\) ENGINE=InnoDB[^;]*;', ');', ddl)
    ddl = re.sub(r'^\s*(?:UNIQUE )?KEY [^\n]+\n', '', ddl, flags=re.M)
    ddl = re.sub(r',\s*\)', ')', ddl)
    with sqlite3.connect(database) as db:
        db.executescript(ddl)
        for table, values in [('connector_runtime_plans', row), ('connector_runtime_devices', runtime)]:
            db.execute('CREATE TABLE workmanship_sim_' + table + ' (' + ','.join(
                key + (' INTEGER' if isinstance(value, int) else ' TEXT') for key, value in values.items()) + ')')
            db.execute('INSERT INTO workmanship_sim_' + table + ' VALUES (' + ','.join('?' for _ in values) + ')',
                [json.dumps(v) if isinstance(v, dict) else v.isoformat() if isinstance(v, datetime) else v
                 for v in values.values()])
    return row


def bind(opened, **overrides):
    # No independent identity service exists in this test; the signed launch is authoritative.
    provider = LiveDocumentProvider(object(), clock=lambda: NOW)
    assert hasattr(provider, 'bind_online_v2'), 'launch@2 source association binding is missing'
    payload = dict(workspace_gid='10', document_gid='11', launch_operation_id=opened['plan_id'],
        expected_workspace_row_version=1, idempotency_key='bind-v2')
    return provider.bind_online_v2({**payload, **overrides}, CapabilityContext(user_gid='30', team_gid='20', source='web')).data


def test_current_open_receipt_atomically_binds_source_and_idempotent_association(database, opened):
    result = bind(opened)
    assert result['source_association_id']
    assert result['document_session'] == opened['outcome_json']['steps'][0]['result']['document_identity']['document_session']
    assert result == bind(opened)
    with sqlite3.connect(database) as db:
        association = db.execute('SELECT source_association_id,document_gid,device_id,runtime_instance_id,source_revision,active '
            'FROM workmanship_sim_viewer_source_associations').fetchall()
        assert association == [(result['source_association_id'], 11, opened['device_id'], opened['runtime_instance_id'], SOURCE_HASH[7:], 1)]
        assert db.execute('SELECT row_version FROM workmanship_sim_workspaces').fetchone()[0] == 2


def test_association_failure_rolls_back_binding_document_and_idempotency(database, opened):
    with sqlite3.connect(database) as db:
        db.execute("CREATE TRIGGER association_failure BEFORE INSERT ON workmanship_sim_viewer_source_associations BEGIN SELECT RAISE(ABORT, 'association failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match='association failure'):
        bind(opened)
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT COUNT(*) FROM workmanship_sim_live_document_bindings').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM workmanship_sim_workspace_idempotency').fetchone()[0] == 0
        assert db.execute('SELECT row_version FROM workmanship_sim_workspaces').fetchone()[0] == 1


@pytest.mark.parametrize('sql', [
    "UPDATE workmanship_sim_connector_runtime_devices SET current_runtime_instance_id='changed'",
    "UPDATE workmanship_sim_connector_runtime_devices SET status='revoked'",
    "UPDATE workmanship_sim_connector_runtime_plans SET actor_gid='31'",
    "UPDATE workmanship_sim_vm_documents SET content_sha256='changed'",
])
def test_changed_scope_cannot_create_association(database, opened, sql):
    with sqlite3.connect(database) as db: db.execute(sql)
    with pytest.raises(CapabilityBusinessError): bind(opened)
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT COUNT(*) FROM workmanship_sim_viewer_source_associations').fetchone()[0] == 0


def test_bind_v2_rejects_independent_identity_operation(database, opened):
    with pytest.raises(CapabilityBusinessError): bind(opened, identity_operation_id='unrelated')

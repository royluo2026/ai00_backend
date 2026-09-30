"""Real SQL authorization/renewal tests; SQLite does not prove MySQL lock behavior."""
from contextlib import contextmanager
from datetime import timedelta
import importlib
import re
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.tests.test_simulation_connector_runtime_v2_sql import SQLiteConnection
from plugins.simulation.tests.test_viewer_interaction_authorization import NOW, signing


@pytest.fixture
def grant_case(tmp_path, monkeypatch):
    name = 'plugins.simulation.simulation_backend.data.viewer_interaction_repository'
    assert importlib.util.find_spec(name), 'transactional viewer grant repository is missing'
    module = importlib.import_module(name)
    path = tmp_path / 'viewer.db'
    with sqlite3.connect(path) as db:
        db.executescript('''
          CREATE TABLE workmanship_sim_workspaces (gid TEXT PRIMARY KEY, tenant_gid TEXT, owner_gid TEXT, status TEXT, removed_at TEXT);
          CREATE TABLE workmanship_sim_vm_documents (gid TEXT PRIMARY KEY, workspace_gid TEXT, tenant_gid TEXT, owner_gid TEXT,
            document_role TEXT, source_kind TEXT, content_sha256 TEXT, removed_at TEXT);
          CREATE TABLE workmanship_sim_live_document_bindings (workspace_gid TEXT, tenant_gid TEXT, actor_gid TEXT,
            connector_device_id TEXT, document_session TEXT, state TEXT);
          CREATE TABLE workmanship_sim_connector_runtime_devices (device_id TEXT PRIMARY KEY, owner_user_gid TEXT, tenant_gid TEXT,
            status TEXT, protocol TEXT, runtime_type TEXT, runtime_generation INTEGER, current_runtime_instance_id TEXT,
            session_token_hash TEXT, session_expires_at TEXT, heartbeat_at TEXT);
        ''')
        migration_root = Path(__file__).parents[1] / 'db/migrations/domains/simulation'
        ddl = '\n'.join((migration_root / name).read_text() for name in ('0028_viewer_interaction.sql', '0029_viewer_grant_evidence.sql'))
        ddl = re.sub(r' CHARACTER SET \w+| COLLATE \w+', '', ddl)
        ddl = re.sub(r'\) ENGINE=InnoDB[^;]*;', ');', ddl)
        ddl = re.sub(r'^\s*(?:UNIQUE )?KEY [^\n]+\n', '', ddl, flags=re.M)
        ddl = re.sub(r',\s*\)', ')', ddl).replace('CURRENT_TIMESTAMP(6)', 'CURRENT_TIMESTAMP')
        db.executescript(ddl)
        db.execute("INSERT INTO workmanship_sim_workspaces VALUES ('10','12','11','active',NULL)")
        db.execute("INSERT INTO workmanship_sim_vm_documents VALUES ('20','10','12','11','primary','teamcenter_online',?,NULL)", ('c'*64,))
        db.execute("INSERT INTO workmanship_sim_live_document_bindings VALUES ('10','12','11','device-1',?,'bound')", ('sha256:'+'b'*64,))
        db.execute("INSERT INTO workmanship_sim_connector_runtime_devices VALUES ('device-1','11','12','active',"
                   "'ai00.connector.execution-plan.v2','electron',1,'runtime-1','token-hash',?,?)",
                   ((NOW+timedelta(minutes=5)).isoformat(), NOW.isoformat()))

    @contextmanager
    def connect():
        db = sqlite3.connect(path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE')
            yield SQLiteConnection(db)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    repository = module.ViewerInteractionRepository(connect=connect)
    with connect() as conn, conn.cursor() as cursor:
        association = repository.record_source_association(cursor, tenant_gid='12', actor_gid='11',
            workspace_gid='10', document_gid='20', device_id='device-1', runtime_instance_id='runtime-1',
            runtime_generation=1, document_session='sha256:'+'b'*64, source_revision='c'*64, now=NOW)
    from plugins.simulation.tests.test_viewer_interaction_provider import registry
    from backend.capability_v2.catalog import build_release, ProviderArtifact
    from backend.capability_v2.business_definition import business_definition_hash
    from backend.capability_v2 import gateway
    release = build_release([item[2] for item in registry().values()], [ProviderArtifact(
        plugin_id='official.simulation', module='simulation.provider', version='1.0.0', artifact_hash='sha256:'+'e'*64)])
    monkeypatch.setattr(gateway, 'get_default_gateway', lambda: SimpleNamespace(catalog=lambda release_id: release))
    descriptor = release.descriptor('simulation.viewer.interaction.authorize', 1)
    return SimpleNamespace(repository=repository, connect=connect, association=association, release=release,
        context=SimpleNamespace(source='web', user_gid='11', team_gid='12', catalog_release=release.release_id,
            outcome_operation_id='op_authorization', capability_version_gid=descriptor.capability_version_gid,
            business_definition_hash=business_definition_hash(descriptor)))


def request(case, **overrides):
    return dict(workspace_gid='10', document_gid='20', source_association_id=case.association,
                session_nonce='a'*64, prior_grant_id=None, **overrides)


def authorize(case, signer, payload=None, context=None):
    from plugins.simulation.simulation_backend.application.viewer_interaction import authorize_interaction
    return authorize_interaction(context or case.context, payload or request(case), case.repository, signer, NOW)


@pytest.mark.parametrize('role', ['primary', 'inserted'])
def test_current_source_grant_and_monotonic_renewal(grant_case, signing, role):
    case = grant_case
    with case.connect() as conn, conn.cursor() as cur:
        cur.execute('UPDATE workmanship_sim_vm_documents SET document_role=%s', (role,))
    first = authorize(case, signing[0])
    assert first.document_session == 'sha256:'+'b'*64
    assert first.runtime_instance_id == 'runtime-1'
    assert first.expires_at == '2026-09-22T04:01:00Z'
    renewed = authorize(case, signing[0], {**request(case), 'prior_grant_id': first.grant_id})
    assert renewed.grant_generation == 2
    with pytest.raises(ValueError, match='interaction_renewal_stale'):
        authorize(case, signing[0], {**request(case), 'prior_grant_id': first.grant_id})
    with pytest.raises(ValueError, match='interaction_renewal_stale'):
        authorize(case, signing[0])


@pytest.mark.parametrize('context', [
    SimpleNamespace(source='web', user_gid='11', team_gid='99'),
    SimpleNamespace(source='web', user_gid='99', team_gid='12'),
    SimpleNamespace(source='agent', user_gid='11', team_gid='12'),
])
def test_other_actor_tenant_or_non_web_cannot_authorize(grant_case, signing, context):
    context = SimpleNamespace(**{**vars(grant_case.context), **vars(context)})
    with pytest.raises(ValueError, match='interaction_scope_denied'):
        authorize(grant_case, signing[0], context=context)


@pytest.mark.parametrize('sql', [
    "UPDATE workmanship_sim_connector_runtime_devices SET current_runtime_instance_id='new-runtime'",
    "UPDATE workmanship_sim_connector_runtime_devices SET runtime_generation=2",
    "UPDATE workmanship_sim_connector_runtime_devices SET session_token_hash=NULL",
    "UPDATE workmanship_sim_connector_runtime_devices SET session_expires_at='2026-09-22T03:59:59Z'",
    "UPDATE workmanship_sim_connector_runtime_devices SET status='revoked'",
    "UPDATE workmanship_sim_workspaces SET status='frozen'",
    "UPDATE workmanship_sim_viewer_source_associations SET active=0",
    "UPDATE workmanship_sim_connector_runtime_devices SET heartbeat_at='2026-09-22T03:57:59Z'",
    "UPDATE workmanship_sim_vm_documents SET content_sha256='changed'",
    "UPDATE workmanship_sim_live_document_bindings SET state='superseded'",
])
@pytest.mark.parametrize('role', ['primary', 'inserted'])
def test_current_association_fails_closed_after_scope_changes(grant_case, signing, sql, role):
    with grant_case.connect() as conn, conn.cursor() as cur:
        cur.execute('UPDATE workmanship_sim_vm_documents SET document_role=%s', (role,))
    first = authorize(grant_case, signing[0])
    with grant_case.connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
    with pytest.raises(ValueError, match='interaction_binding_stale'):
        authorize(grant_case, signing[0], {**request(grant_case), 'prior_grant_id': first.grant_id})


@pytest.mark.parametrize('change,expected', [
    ('', 'interaction_source_unassociated'),
    ("owner_gid='99'", 'interaction_scope_denied'),
    ("source_kind='local_file'", 'interaction_scope_denied'),
    ("document_role='unknown'", 'interaction_scope_denied'),
    ("removed_at='2026-09-22'", 'interaction_scope_denied'),
    ("gid='99'", 'interaction_scope_denied'),
])
def test_unassociated_inserted_scope_requires_owned_online_document(grant_case, change, expected):
    case = grant_case
    with case.connect() as conn, conn.cursor() as cur:
        cur.execute("UPDATE workmanship_sim_vm_documents SET document_role='inserted'")
        cur.execute('UPDATE workmanship_sim_viewer_source_associations SET active=0')
        if change:
            cur.execute('UPDATE workmanship_sim_vm_documents SET ' + change)
    with pytest.raises(ValueError, match='^' + expected + '$'):
        with case.repository.authorize_scope(case.context, SimpleNamespace(**request(case)), NOW, allocate=False):
            pytest.fail('unassociated source cannot authorize a session')
    with pytest.raises(ValueError):
        with case.repository.authorize_scope(case.context, SimpleNamespace(**request(case)), NOW):
            pytest.fail('unassociated source cannot allocate a grant')


def test_signing_failure_rolls_back_generation(grant_case, signing):
    signer, record, _ = signing
    record['revoked'] = True
    with pytest.raises(ValueError, match='signing_key_inactive'):
        authorize(grant_case, signer)
    record['revoked'] = False
    assert authorize(grant_case, signer).grant_generation == 1


@pytest.mark.parametrize('override', [{'runtime_instance_id':'other'}, {'operations':[]}, {'ttl':3600}, {'actor_id':'99'}])
def test_caller_cannot_expand_grant_scope(grant_case, signing, override):
    with pytest.raises(ValueError):
        authorize(grant_case, signing[0], {**request(grant_case), **override})

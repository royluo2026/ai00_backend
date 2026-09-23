"""Completion commits source binding and signed grant together, without a second connection."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import re
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext
from plugins.simulation.tests.test_viewer_opened_source_binding import database, opened
from plugins.simulation.tests.test_viewer_interaction_authorization import signing
from plugins.simulation.tests.test_teamcenter_launch_evidence import NOW
from plugins.simulation.tests.test_viewer_interaction_provider import registry
from plugins.simulation.simulation_backend.capabilities.live_documents import LiveDocumentProvider

KEY = ('simulation.environment.online_source.live_document.bind', 3)


def test_demand_driven_consumer_keeps_existing_capability_versions_and_policies():
    from backend.capability_v2.catalog import build_release, ProviderArtifact
    release = build_release([item[2] for item in registry().values()], [ProviderArtifact(
        plugin_id='official.simulation', module='simulation.provider', version='1.0.0',
        artifact_hash='sha256:'+'e'*64)])
    expected = {
        ('simulation.teamcenter.visualization.launch.request', 2): 'cv2_cce43b004671f2f8e0b4edfd',
        KEY: 'cv2_1f92da28d1c518cd7ca6b230',
        ('simulation.viewer.interaction.authorize', 1): 'cv2_59f6ec1e05ca6e2b8fdef576',
    }
    for key, version_gid in expected.items():
        assert release.descriptor(*key).capability_version_gid == version_gid
    binding = release.descriptor(*KEY)
    assert binding.confirmation_policy == 'user'
    assert binding.idempotency_policy == 'required'
    assert binding.input_schema['required'] == [
        'workspace_gid', 'document_gid', 'launch_operation_id',
        'expected_workspace_row_version', 'idempotency_key', 'session_nonce']
    assert binding.transaction_policy['idempotency'].endswith('immutable replay, nonce conflict rejected')


def test_atomic_completion_is_registered_alongside_legacy_binding():
    items = registry()
    assert KEY in items, 'atomic open completion major 3 is missing'
    assert (KEY[0], 1) in items and (KEY[0], 2) in items


@pytest.fixture
def completion(database, opened, signing, monkeypatch):
    items = registry()
    assert KEY in items, 'atomic open completion major 3 is missing'
    from backend.capability_v2.catalog import build_release, ProviderArtifact
    from backend.capability_v2.business_definition import business_definition_hash
    from backend.capability_v2 import gateway
    from plugins.simulation.simulation_backend.application.connector_protocol_v2 import PlanSigner
    ddl = (Path(__file__).parents[3] / 'backend/db/migrations/domains/simulation/0029_viewer_grant_evidence.sql').read_text()
    ddl = re.sub(r' CHARACTER SET \w+| COLLATE \w+', '', ddl)
    ddl = re.sub(r'\) ENGINE=InnoDB[^;]*;', ');', ddl)
    with sqlite3.connect(database) as db:
        db.executescript(ddl)
    record = signing[1]
    record.update(not_before=NOW-timedelta(days=1), not_after=NOW+timedelta(days=1))
    signer = PlanSigner(lambda _: record, key_id='test-key', clock=lambda: NOW)
    release = build_release([item[2] for item in items.values()], [ProviderArtifact(
        plugin_id='official.simulation', module='simulation.provider', version='1.0.0', artifact_hash='sha256:'+'e'*64)])
    monkeypatch.setattr(gateway, 'get_default_gateway', lambda: SimpleNamespace(catalog=lambda _: release))
    descriptor = release.descriptor(*KEY)
    context = CapabilityContext(source='web', user_gid='30', team_gid='20', catalog_release=release.release_id,
        outcome_operation_id='op_completion', capability_version_gid=descriptor.capability_version_gid,
        business_definition_hash=business_definition_hash(descriptor))
    provider = LiveDocumentProvider(object(), clock=lambda: NOW, signer=signer)
    payload = dict(workspace_gid='10', document_gid='11', launch_operation_id=opened['plan_id'],
        expected_workspace_row_version=1, idempotency_key='complete-open', session_nonce='a'*64)
    return SimpleNamespace(provider=provider, payload=payload, context=context, record=record, public=signing[2])


def complete(case, **changes):
    return case.provider.bind_online_v3({**case.payload, **changes}, case.context).data


def counts(database):
    with sqlite3.connect(database) as db:
        return [db.execute('SELECT COUNT(*) FROM workmanship_sim_' + table).fetchone()[0]
                for table in ('live_document_bindings', 'workspace_idempotency', 'viewer_source_associations',
                              'viewer_interaction_grants', 'viewer_grant_evidence')]


def test_completion_commits_one_signed_grant_and_replays_immutable_result(database, completion):
    from backend.contracts.viewer_interaction_v1 import SignedGrant
    result = complete(completion)
    assert result['binding']['workspace_row_version'] == 2
    assert SignedGrant.model_validate(result['grant']).verify_signature(completion.public)
    assert result['grant']['document_session'] == result['binding']['document_session']
    assert complete(completion) == result
    assert counts(database) == [1, 1, 1, 1, 1]
    with sqlite3.connect(database) as db:
        proof = json.loads(db.execute('SELECT proof_json FROM workmanship_sim_viewer_grant_evidence').fetchone()[0])
    assert proof['authorization_descriptor']['id'] == KEY[0]
    assert proof['authorization_descriptor']['major_version'] == 3


def test_completion_nonce_conflict_never_allocates_another_grant(database, completion):
    complete(completion)
    with pytest.raises(CapabilityBusinessError, match='idempotency_conflict'):
        complete(completion, session_nonce='b'*64)
    assert counts(database) == [1, 1, 1, 1, 1]


@pytest.mark.parametrize('failure', ['signer', 'proof'])
def test_completion_failure_rolls_back_binding_revision_and_grant(database, completion, failure):
    if failure == 'signer':
        completion.record['revoked'] = True
    else:
        with sqlite3.connect(database) as db:
            db.execute("CREATE TRIGGER proof_failure BEFORE INSERT ON workmanship_sim_viewer_grant_evidence BEGIN SELECT RAISE(ABORT, 'proof failure'); END")
    with pytest.raises((CapabilityBusinessError, sqlite3.IntegrityError)):
        complete(completion)
    assert counts(database) == [0, 0, 0, 0, 0]
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT row_version FROM workmanship_sim_workspaces').fetchone()[0] == 1


def test_expired_completion_replay_is_not_resigned_or_rebound(database, completion):
    result = complete(completion)
    completion.provider.clock = lambda: NOW + timedelta(hours=1)
    assert complete(completion) == result
    assert counts(database) == [1, 1, 1, 1, 1]


def test_concurrent_completion_returns_one_result(database, completion):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: complete(completion), range(2)))
    assert results[0] == results[1]
    assert counts(database) == [1, 1, 1, 1, 1]


def test_concurrent_distinct_nonces_cannot_share_completion(database, completion):
    def attempt(nonce):
        try: return complete(completion, session_nonce=nonce)
        except CapabilityBusinessError as error: return str(error)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ['a'*64, 'b'*64]))
    assert sum(isinstance(value, dict) for value in results) == 1
    assert sum('idempotency_conflict' in value for value in results if isinstance(value, str)) == 1
    assert counts(database) == [1, 1, 1, 1, 1]


def test_expired_uncommitted_receipt_cannot_complete(database, completion):
    completion.provider.clock = lambda: NOW + timedelta(hours=1)
    with pytest.raises(CapabilityBusinessError): complete(completion)
    assert counts(database) == [0, 0, 0, 0, 0]


def test_altered_signed_open_receipt_cannot_complete(database, completion):
    with sqlite3.connect(database) as db:
        outcome = json.loads(db.execute('SELECT outcome_json FROM workmanship_sim_connector_runtime_plans').fetchone()[0])
        outcome['steps'][0]['result']['document_identity']['document_session'] = 'sha256:'+'0'*64
        db.execute('UPDATE workmanship_sim_connector_runtime_plans SET outcome_json=?', (json.dumps(outcome),))
    with pytest.raises(CapabilityBusinessError): complete(completion)
    assert counts(database) == [0, 0, 0, 0, 0]


@pytest.mark.parametrize('sql', [
    "UPDATE workmanship_sim_workspaces SET status='frozen'",
    "UPDATE workmanship_sim_workspaces SET row_version=2",
    "UPDATE workmanship_sim_workspaces SET owner_gid='99'",
    "UPDATE workmanship_sim_workspaces SET tenant_gid='99'",
    "UPDATE workmanship_sim_connector_runtime_devices SET current_runtime_instance_id='changed'",
    "UPDATE workmanship_sim_connector_runtime_devices SET status='revoked'",
    "UPDATE workmanship_sim_vm_documents SET content_sha256='changed'",
    "UPDATE workmanship_sim_connector_runtime_plans SET actor_gid='99'",
])
def test_completion_rejects_stale_or_foreign_scope(database, completion, sql):
    with sqlite3.connect(database) as db: db.execute(sql)
    with pytest.raises(CapabilityBusinessError): complete(completion)
    assert counts(database) == [0, 0, 0, 0, 0]


@pytest.mark.parametrize('changes', [{'process_id':42}, {'session_nonce':'short'}, {'document_session':'forged'}])
def test_completion_closed_input_does_not_accept_renderer_identity(completion, changes):
    with pytest.raises(CapabilityBusinessError): complete(completion, **changes)

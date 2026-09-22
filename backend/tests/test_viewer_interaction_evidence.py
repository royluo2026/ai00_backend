import hashlib
import json

import pytest

from backend.contracts.connector_execution_plan_v2 import canonicalize_v2
from backend.tests.test_viewer_interaction_repository import grant_case, authorize
from plugins.simulation.tests.test_viewer_interaction_authorization import signing


def test_grant_retains_signed_proof_and_both_exact_operation_bindings(grant_case, signing):
    grant = authorize(grant_case, signing[0])
    with grant_case.connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT * FROM workmanship_sim_viewer_grant_evidence WHERE grant_id=%s', (grant.grant_id,))
        row = cur.fetchone()
    assert row['authorization_operation_id'] == 'op_authorization'
    proof = json.loads(row['proof_json'])
    assert proof['signed_grant'] == grant.model_dump(mode='json')
    assert row['proof_digest'] == hashlib.sha256(canonicalize_v2(proof)).hexdigest()
    assert proof['signed_grant_digest'] == 'sha256:' + hashlib.sha256(canonicalize_v2(grant)).hexdigest()
    bindings = proof['operation_bindings']
    assert [(b['operation_id'], b['descriptor']['id']) for b in bindings] == [
        ('vismockup.node.visibility.change@1', 'simulation.vismockup.node.visibility.change.apply'),
        ('vismockup.node.selection.change@1', 'simulation.vismockup.node.selection.change.apply')]
    assert all(b['descriptor']['capability_version_gid'] and b['business_definition_hash'].startswith('sha256:') for b in bindings)
    assert proof['provider_artifact']['plugin_id'] == 'official.simulation'


def test_missing_outcome_binding_rejects_before_allocation(grant_case, signing):
    grant_case.context.outcome_operation_id = None
    with pytest.raises(ValueError, match='interaction_catalog_binding_unavailable'):
        authorize(grant_case, signing[0])


@pytest.mark.parametrize('missing', ['operation', 'provider', 'release', 'definition'])
def test_missing_trusted_catalog_binding_rejects_without_grant(grant_case, signing, monkeypatch, missing):
    from backend.capability_v2 import gateway
    from backend.capability_v2.catalog import build_release
    from types import SimpleNamespace
    release = grant_case.release
    if missing in {'operation', 'provider'}:
        release = build_release([d for d in release.descriptors if missing != 'operation' or d.id != 'simulation.vismockup.node.selection.change.apply'],
            () if missing == 'provider' else release.provider_artifacts)
        grant_case.context.catalog_release = release.release_id
    if missing == 'release': grant_case.context.catalog_release = 'rel_'+'0'*32
    if missing == 'definition': grant_case.context.business_definition_hash = 'sha256:'+'0'*64
    monkeypatch.setattr(gateway, 'get_default_gateway', lambda: SimpleNamespace(catalog=lambda _: release))
    with pytest.raises(ValueError, match='interaction_catalog_binding_unavailable'):
        authorize(grant_case, signing[0])
    with grant_case.connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) AS n FROM workmanship_sim_viewer_interaction_grants')
        assert cur.fetchone()['n'] == 0


def test_evidence_insert_failure_rolls_back_grant(grant_case, signing):
    with grant_case.connect() as conn, conn.cursor() as cur:
        cur.execute("CREATE TRIGGER reject_proof BEFORE INSERT ON workmanship_sim_viewer_grant_evidence BEGIN SELECT RAISE(ABORT, 'proof unavailable'); END")
    with pytest.raises(Exception, match='proof unavailable'):
        authorize(grant_case, signing[0])
    with grant_case.connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) AS n FROM workmanship_sim_viewer_interaction_grants')
        assert cur.fetchone()['n'] == 0

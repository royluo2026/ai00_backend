"""Local viewer grants must not turn into an unrestricted execution ticket."""
import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from pydantic import ValidationError

from backend.contracts.connector_execution_plan_v2 import P256_ORDER, canonicalize_v2
from plugins.simulation.simulation_backend.application.connector_protocol_v2 import PlanSigner

NOW = datetime(2026, 9, 22, 4, 0, tzinfo=UTC)


def claims():
    return dict(
        protocol='ai00.viewer.interaction.grant.v1', grant_id='grant-1', grant_generation=1,
        session_nonce='a' * 64, actor_id='11', tenant_id='12', device_id='device-1',
        runtime_instance_id='runtime-1', workspace_gid='10', document_gid='20',
        source_association_id='association-1', document_session='sha256:' + 'b' * 64,
        operations=[dict(id='vismockup.node.visibility.change@1', contract_hash='sha256:' + 'c' * 64)],
        policy_version='viewer-interaction-v1', issued_at='2026-09-22T04:00:00Z',
        expires_at='2026-09-22T04:01:00Z', audience='ai00.connector.viewer-interaction',
    )


def test_cross_language_fixture_verifies_without_signing_at_test_time():
    from backend.contracts.viewer_interaction_v1 import SignedGrant
    vector = json.loads((Path(__file__).resolve().parents[3] / 'backend/tests/fixtures/viewer_interaction_v1.json').read_text())
    assert SignedGrant.model_validate(vector['grant']).verify_signature(vector['public_jwk'])


@pytest.fixture
def signing():
    key = ec.generate_private_key(ec.SECP256R1())
    record = dict(private_key=key, not_before=NOW-timedelta(days=1),
                  not_after=NOW+timedelta(days=1), revoked=False)
    signer = PlanSigner(lambda _: record, key_id='test-key', clock=lambda: NOW)
    numbers = key.public_key().public_numbers()
    b64 = lambda n: base64.urlsafe_b64encode(n.to_bytes(32, 'big')).rstrip(b'=').decode()
    return signer, record, dict(kty='EC', crv='P-256', x=b64(numbers.x), y=b64(numbers.y))


def test_signer_issues_domain_separated_grant_and_rejects_tampering(signing):
    signer, record, public = signing
    assert hasattr(signer, 'sign_interaction_grant'), 'dedicated viewer grant signing is missing'
    from backend.contracts.viewer_interaction_v1 import SignedGrant, grant_signature_bytes
    grant = signer.sign_interaction_grant(claims())
    raw = grant.model_dump(mode='json')
    unsigned = {k: v for k, v in raw.items() if k != 'signature'}
    assert grant.verify_signature(public)
    assert grant_signature_bytes(grant) == b'ai00.viewer.interaction.grant.v1\n' + canonicalize_v2(unsigned)
    assert not SignedGrant.model_validate({**raw, 'document_gid': '21'}).verify_signature(public)
    # Same valid key, wrong signature domain: must never be accepted as a grant.
    r, s = decode_dss_signature(record['private_key'].sign(canonicalize_v2(unsigned), ec.ECDSA(hashes.SHA256())))
    wrong = base64.urlsafe_b64encode(r.to_bytes(32, 'big') + min(s, P256_ORDER-s).to_bytes(32, 'big')).rstrip(b'=').decode()
    assert not SignedGrant.model_validate({**raw, 'signature': wrong}).verify_signature(public)


@pytest.mark.parametrize('change', [
    {'expires_at': '2026-09-22T04:01:01Z'}, {'expires_at': '2026-09-22T04:00:00Z'},
    {'issued_at': '2026-09-22T04:00:01Z'}, {'audience': 'ai00.connector.execution-plan'},
    {'grant_generation': True}, {'grant_generation': 0}, {'session_nonce': 'short'},
    {'operations': []}, {'operations': [dict(id='arbitrary.com@1', contract_hash='sha256:'+'c'*64)]},
    {'file_path': 'C:/secret.jt'},
])
def test_invalid_or_expanded_grants_are_not_signed(signing, change):
    signer, _, _ = signing
    assert hasattr(signer, 'sign_interaction_grant'), 'dedicated viewer grant signing is missing'
    with pytest.raises(ValueError):
        signer.sign_interaction_grant({**claims(), **change})


def test_grant_requires_every_field_and_closed_nested_operations(signing):
    signer, _, _ = signing
    assert hasattr(signer, 'sign_interaction_grant'), 'dedicated viewer grant signing is missing'
    from backend.contracts.viewer_interaction_v1 import SignedGrant
    raw = signer.sign_interaction_grant(claims()).model_dump(mode='json')
    for field in raw:
        with pytest.raises(ValidationError):
            SignedGrant.model_validate({k: v for k, v in raw.items() if k != field})
    with pytest.raises(ValidationError):
        SignedGrant.model_validate({**raw, 'operations': [{**raw['operations'][0], 'method': 'RunScript'}]})
    with pytest.raises(ValidationError):
        SignedGrant.model_validate({**raw, 'operations': raw['operations'] * 2})


def test_revoked_key_or_key_expiring_before_grant_fails_closed(signing):
    signer, record, _ = signing
    assert hasattr(signer, 'sign_interaction_grant'), 'dedicated viewer grant signing is missing'
    record['revoked'] = True
    with pytest.raises(ValueError, match='signing_key_inactive'):
        signer.sign_interaction_grant(claims())
    record['revoked'] = False
    record['not_after'] = NOW + timedelta(seconds=59)
    with pytest.raises(ValueError, match='grant_signing_interval_invalid'):
        signer.sign_interaction_grant(claims())

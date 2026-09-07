"""Cloud-only signing and verification policy for Connector v2."""
from __future__ import annotations

import base64
from datetime import UTC, datetime
import hashlib
import json

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from backend.contracts.connector_execution_plan_v2 import (
    ConnectorExecutionPlanV2, ConnectorPlanOutcomeV2, ConnectorStepResultV2, P256_ORDER,
    canonicalize_v2, compute_plan_hash, plan_signature_bytes,
)


def parse_plan(value):
    from backend.contracts.connector_execution_plan_v1 import ConnectorExecutionPlanV1
    model = ConnectorExecutionPlanV2 if value.get('protocol') == 'ai00.connector.execution-plan.v2' else ConnectorExecutionPlanV1
    return model.model_validate(value)


def projection_status(value):
    """Map verified wire results to existing Simulation aggregate states."""
    status = getattr(value, 'overall_status', None) or value.status
    return {'succeeded': 'completed', 'failed_without_effect': 'failed',
            'manual_review_required': 'outcome_unknown'}.get(status, status)


def projection_result(step):
    value = step.result
    if isinstance(step, ConnectorStepResultV2) and isinstance(value, dict) and 'nonce' in value:
        return value.get('observed_result')
    return value


class PlanSigner:
    """The injected cloud secret provider resolves key records by key ID.

    Records hold private_key (P-256 key object), not_before, not_after, revoked.
    No key export or Connector-supplied key import is supported.
    """
    def __init__(self, secret_provider, *, key_id, clock=lambda: datetime.now(UTC)):
        self._secret_provider = secret_provider
        self.key_id = key_id
        self.clock = clock

    @classmethod
    def from_jwk(cls, _jwk):
        raise ValueError('cloud_secret_provider_required')

    def sign(self, plan) -> ConnectorExecutionPlanV2:
        record = self._secret_provider(self.key_id)
        now = self.clock()
        if not record or record['revoked'] or not record['not_before'] <= now < record['not_after']:
            raise ValueError('signing_key_inactive')
        key = record['private_key']
        if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
            raise ValueError('private_key_required')
        raw = plan.model_dump(mode='json') if isinstance(plan, ConnectorExecutionPlanV2) else dict(plan)
        raw.update(key_id=self.key_id, signature_algorithm='ecdsa-p256-sha256')
        raw['plan_hash'] = compute_plan_hash(raw)
        # Validate the closed contract before signing, using a valid-shaped placeholder.
        raw['signature'] = base64.urlsafe_b64encode((1).to_bytes(32, 'big') * 2).rstrip(b'=').decode()
        parsed = ConnectorExecutionPlanV2.model_validate(raw)
        issued, expires = datetime.fromisoformat(parsed.issued_at), datetime.fromisoformat(parsed.expires_at)
        if not record['not_before'] <= issued <= now < expires <= record['not_after']:
            raise ValueError('plan_signing_interval_invalid')
        r, s = decode_dss_signature(key.sign(plan_signature_bytes(parsed), ec.ECDSA(hashes.SHA256())))
        raw['signature'] = base64.urlsafe_b64encode(r.to_bytes(32, 'big') + min(s, P256_ORDER-s).to_bytes(32, 'big')).rstrip(b'=').decode()
        return ConnectorExecutionPlanV2.model_validate(raw)


class OutcomeVerifier:
    @staticmethod
    def verify(outcome, device_jwk) -> ConnectorPlanOutcomeV2:
        value = ConnectorPlanOutcomeV2.model_validate(outcome)
        if not value.verify_signature(device_jwk):
            raise ValueError('outcome_signature_invalid')
        return value

    @staticmethod
    def verify_steps(plan, outcome):
        expected = [s.step_id for s in plan.steps]
        actual = [s.step_id for s in outcome.steps]
        statuses = [s.status for s in outcome.steps]
        if actual != expected[:len(actual)]:
            raise ValueError('plan_outcome_invalid')
        if outcome.overall_status == 'succeeded':
            valid = actual == expected and all(s == 'succeeded' for s in statuses)
        else:
            valid = statuses[-1] == outcome.overall_status and all(s == 'succeeded' for s in statuses[:-1])
            # A prior successful mutation means the overall operation did have an effect.
            if outcome.overall_status == 'failed_without_effect':
                valid = valid and all(s.side_effect_classification == 'read' for s in plan.steps[:len(actual)-1])
        if not valid:
            raise ValueError('plan_outcome_invalid')


def probe_context(plan_row, recovery):
    plan = json.loads(plan_row['plan_json']) if isinstance(plan_row['plan_json'], str) else plan_row['plan_json']
    context = dict(scope='read_only_post_condition_probe', plan_id=plan_row['plan_id'],
                   plan_hash=plan_row['plan_hash'], lease_id=plan_row['lease_id'],
                   runtime_instance_id=plan_row['runtime_instance_id'], runtime_generation=plan_row['runtime_generation'],
                   device_id=plan_row['device_id'], tenant_id=plan_row['tenant_gid'],
                   probes=[dict(step_id=s['step_id'], probe_id=s['post_condition_probe_id'])
                           for s in plan['steps'] if s['post_condition_probe_id']])
    # A server-held recovery token hash binds the nonce to this recovery session
    # and the original lease. The response contains no executable mutation.
    context['nonce'] = hashlib.sha256(canonicalize_v2(context) + recovery['token_hash'].encode()).hexdigest()
    return context


class ReconciliationService:
    def reconcile(self, plan_id, probe_result):
        if not probe_result:
            return 'manual_review_required'
        if probe_result.get('plan_id') != plan_id:
            raise ValueError('reconciliation_evidence_invalid')
        classifications = probe_result.get('classifications', [])
        if classifications and all(s == 'succeeded' for s in classifications):
            return 'succeeded'
        if classifications and all(s == 'failed_without_effect' for s in classifications):
            return 'failed_without_effect'
        return 'manual_review_required'

    def verify(self, plan_row, recovery, outcome):
        context = probe_context(plan_row, recovery)
        declared = {p['step_id']: p['probe_id'] for p in context['probes']}
        classifications = []
        for step in outcome.steps:
            result = step.result
            if not isinstance(result, dict) or result.get('nonce') != context['nonce']:
                raise ValueError('reconciliation_evidence_invalid')
            if step.step_id in declared:
                if result.get('probe_id') != declared[step.step_id]:
                    raise ValueError('reconciliation_evidence_invalid')
                classifications.append(result.get('classification'))
        if set(declared) - {s.step_id for s in outcome.steps}:
            classifications.append('inconclusive')
        status = self.reconcile(outcome.plan_id, dict(plan_id=outcome.plan_id, classifications=classifications))
        if outcome.overall_status != status:
            raise ValueError('reconciliation_evidence_invalid')
        return status

"""Cloud-only signing and verification policy for Connector v2."""
from __future__ import annotations

import base64
from datetime import UTC, datetime
import os
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from cryptography.exceptions import InvalidSignature

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature

from backend.contracts.connector_execution_plan_v2 import (
    ConnectorExecutionPlanV2, ConnectorPlanOutcomeV2, P256_ORDER,
    canonicalize_v2, compute_plan_hash, plan_signature_bytes,
    IDENTITY_PATTERN, Signature, Timestamp, JsonValue, _public_key, _decode_signature, outcome_signature_bytes,
)


class _ClosedEvidence(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True, revalidate_instances='always')


class ConnectorProbeEvidenceV2(_ClosedEvidence):
    step_id: str = Field(pattern=IDENTITY_PATTERN)
    probe_id: str = Field(pattern=IDENTITY_PATTERN)
    classification: Literal['succeeded', 'failed_without_effect', 'inconclusive']
    observed_result: JsonValue


class ConnectorReconciliationEvidenceV2(_ClosedEvidence):
    protocol: Literal['ai00.connector.reconciliation-evidence.v2']
    scope: Literal['read_only_post_condition_probe']
    plan_id: str = Field(pattern=IDENTITY_PATTERN)
    plan_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    lease_id: str = Field(pattern=IDENTITY_PATTERN)
    tenant_id: str = Field(pattern=IDENTITY_PATTERN)
    device_id: str = Field(pattern=IDENTITY_PATTERN)
    runtime_generation: int = Field(ge=1)
    runtime_instance_id: str = Field(pattern=IDENTITY_PATTERN)
    recovery_instance_id: str = Field(pattern=IDENTITY_PATTERN)
    recovery_session_id: str = Field(pattern=r'^[0-9a-f]{64}$')
    nonce: str = Field(pattern=r'^[0-9a-f]{64}$')
    probes: list[ConnectorProbeEvidenceV2] = Field(max_length=10_000)
    journal_sequence: int = Field(ge=1)
    reported_at: Timestamp
    device_key_id: str = Field(pattern=IDENTITY_PATTERN)
    signature_algorithm: Literal['ecdsa-p256-sha256']
    signature: Signature

    def verify_signature(self, jwk):
        try:
            r, s = _decode_signature(self.signature)
            _public_key(jwk).verify(encode_dss_signature(r, s), outcome_signature_bytes(self), ec.ECDSA(hashes.SHA256()))
            return True
        except (InvalidSignature, ValueError, TypeError):
            return False


class ReconciledStep(_ClosedEvidence):
    step_id: str
    status: Literal['succeeded', 'failed_without_effect', 'outcome_unknown', 'manual_review_required']
    result: JsonValue
    error_code: str | None


class ConnectorReconciledOutcomeV2(_ClosedEvidence):
    """Server projection facts retaining both authentic source records.

    This is deliberately not a device-signed normal execution Outcome.
    """
    protocol: Literal['ai00.connector.execution-plan.v2']
    record_type: Literal['server_reconciliation_v2']
    plan_id: str
    plan_hash: str
    lease_id: str
    tenant_id: str
    device_id: str
    runtime_generation: int
    runtime_instance_id: str
    overall_status: Literal['succeeded', 'failed_without_effect', 'manual_review_required']
    journal_sequence: int
    reported_at: Timestamp
    steps: list[ReconciledStep]
    original_outcome: ConnectorPlanOutcomeV2 | None
    evidence: ConnectorReconciliationEvidenceV2


def parse_v2_outcome(value):
    model = ConnectorReconciledOutcomeV2 if value.get('record_type') == 'server_reconciliation_v2' else ConnectorPlanOutcomeV2
    return model.model_validate(value)


def parse_plan(value):
    from backend.contracts.connector_execution_plan_v1 import ConnectorExecutionPlanV1
    model = ConnectorExecutionPlanV2 if value.get('protocol') == 'ai00.connector.execution-plan.v2' else ConnectorExecutionPlanV1
    return model.model_validate(value)


def projection_status(value):
    """Map verified wire results to existing Simulation aggregate states."""
    status = getattr(value, 'overall_status', None) or value.status
    return {'succeeded': 'completed', 'failed_without_effect': 'failed',
            'manual_review_required': 'outcome_unknown'}.get(status, status)


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

    @classmethod
    def configured_from_environment(cls, *, clock=lambda: datetime.now(UTC)):
        """Compose the cloud signer from secret-injected PEM; return None when unconfigured."""
        key_id = os.environ.get('AI00_CONNECTOR_PLAN_SIGNING_P256_KEY_ID', '').strip()
        private_pem = os.environ.get('AI00_CONNECTOR_PLAN_SIGNING_P256_PRIVATE_KEY', '').replace('\\n', '\n').strip()
        not_before_raw = os.environ.get('AI00_CONNECTOR_PLAN_SIGNING_P256_NOT_BEFORE', '').strip()
        not_after_raw = os.environ.get('AI00_CONNECTOR_PLAN_SIGNING_P256_NOT_AFTER', '').strip()
        if not any((key_id, private_pem, not_before_raw, not_after_raw)):
            return None
        if not all((key_id, private_pem, not_before_raw, not_after_raw)):
            raise ValueError('connector_plan_signing_configuration_incomplete')
        key = serialization.load_pem_private_key(private_pem.encode('utf-8'), password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
            raise ValueError('private_key_required')
        parse = lambda value: datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(UTC)
        record = dict(private_key=key, not_before=parse(not_before_raw),
                      not_after=parse(not_after_raw), revoked=False)
        return cls(lambda requested: record if requested == key_id else None, key_id=key_id, clock=clock)

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


def original_outcome(plan_row):
    raw = plan_row.get('outcome_json')
    if not raw:
        return None
    raw = json.loads(raw) if isinstance(raw, str) else raw
    value = parse_v2_outcome(raw)
    return value.original_outcome if isinstance(value, ConnectorReconciledOutcomeV2) else value


def probe_context(plan_row, recovery, *, last_journal_sequence):
    plan = json.loads(plan_row['plan_json']) if isinstance(plan_row['plan_json'], str) else plan_row['plan_json']
    original = original_outcome(plan_row)
    # A verified execution prefix proves later steps were never invoked. With
    # no original Outcome, every side effect needs a probe; read execution is unproven.
    invoked = plan['steps'][:len(original.steps)] if original else plan['steps']
    has_effects = any(s['side_effect_classification'] != 'read' for s in plan['steps'])
    required = []
    for step in invoked:
        if not step['post_condition_probe_id'] or not (
                step['side_effect_classification'] != 'read' or not has_effects):
            continue
        probe = dict(step_id=step['step_id'], probe_id=step['post_condition_probe_id'])
        payload = step.get('payload') or {}
        if (step['operation_id'] == 'vismockup.node.visibility.change@1'
                and payload.get('action') in {'show', 'hide'}):
            probe['probe_input'] = dict(node_key=payload['node_key'],
                expected_visible=payload['action'] == 'show')
        required.append(probe)
    probed = {p['step_id'] for p in required}
    completed = {s.step_id for s in original.steps if s.status == 'succeeded'} if original else set()
    coverage = dict(
        unprobeable_side_effect_step_ids=[s['step_id'] for s in invoked
            if s['side_effect_classification'] != 'read' and not s['post_condition_probe_id']],
        success_unproven_step_ids=[s['step_id'] for s in invoked
            if (s['step_id'] not in probed and s['step_id'] not in completed)
            or (not original and s['side_effect_classification'] == 'read')],
        uninvoked_step_ids=[s['step_id'] for s in plan['steps'][len(invoked):]])
    context = dict(scope='read_only_post_condition_probe', plan_id=plan_row['plan_id'],
        plan_hash=plan_row['plan_hash'], lease_id=plan_row['lease_id'],
        runtime_instance_id=plan_row['runtime_instance_id'], runtime_generation=plan_row['runtime_generation'],
        device_id=plan_row['device_id'], tenant_id=plan_row['tenant_gid'],
        recovery_instance_id=recovery.get('recovery_instance_id', plan_row['runtime_instance_id']),
        recovery_session_id=hashlib.sha256(('reconciliation-session:' + recovery['token_hash']).encode()).hexdigest(),
        required_probes=required, coverage=coverage, next_journal_sequence=last_journal_sequence + 1)
    context['nonce'] = hashlib.sha256(canonicalize_v2(context) + recovery['token_hash'].encode()).hexdigest()
    return context


class ReconciliationService:
    def reconcile(self, plan_id, probe_result):
        if not probe_result:
            return 'manual_review_required'
        if probe_result.get('plan_id') != plan_id:
            raise ValueError('reconciliation_evidence_invalid')
        coverage = probe_result.get('coverage')
        if coverage is None:
            return 'manual_review_required'
        classifications = probe_result.get('classifications', [])
        if (classifications and all(s == 'succeeded' for s in classifications)
                and not coverage['success_unproven_step_ids'] and not coverage['uninvoked_step_ids']):
            return 'succeeded'
        if (classifications and all(s == 'failed_without_effect' for s in classifications)
                and not coverage['unprobeable_side_effect_step_ids']):
            return 'failed_without_effect'
        return 'manual_review_required'

    def verify(self, plan_row, recovery, evidence, jwk, *, last_journal_sequence):
        evidence = ConnectorReconciliationEvidenceV2.model_validate(evidence)
        if not evidence.verify_signature(jwk):
            raise ValueError('outcome_signature_invalid')
        context = probe_context(plan_row, recovery, last_journal_sequence=last_journal_sequence)
        if evidence.journal_sequence != context['next_journal_sequence']:
            raise ValueError('journal_sequence_invalid')
        if any(getattr(evidence, key) != value for key, value in context.items()
                if key not in {'required_probes', 'coverage', 'next_journal_sequence'}):
            raise ValueError('reconciliation_evidence_invalid')
        required = [(p['step_id'], p['probe_id']) for p in context['required_probes']]
        actual = [(p.step_id, p.probe_id) for p in evidence.probes]
        # Ordered subsets are inconclusive; duplicate, unknown, or reordered
        # probes are malformed evidence and never advance the journal.
        if len(set(actual)) != len(actual) or any(p not in required for p in actual):
            raise ValueError('reconciliation_evidence_invalid')
        if actual != [p for p in required if p in actual]:
            raise ValueError('reconciliation_evidence_invalid')
        classifications = [p.classification for p in evidence.probes]
        if actual != required:
            classifications.append('inconclusive')
        status = self.reconcile(evidence.plan_id, dict(plan_id=evidence.plan_id,
            classifications=classifications, coverage=context['coverage']))
        plan = parse_plan(json.loads(plan_row['plan_json']) if isinstance(plan_row['plan_json'], str) else plan_row['plan_json'])
        original = original_outcome(plan_row)
        projected = {s.step_id: ReconciledStep(step_id=s.step_id, status=s.status, result=s.result, error_code=s.error_code)
                     for s in original.steps} if original else {}
        for probe in evidence.probes:
            step_status = {'inconclusive':'manual_review_required'}.get(probe.classification, probe.classification)
            projected[probe.step_id] = ReconciledStep(step_id=probe.step_id, status=step_status,
                result=probe.observed_result, error_code=None if step_status=='succeeded' else 'reconciliation_required')
        steps = [projected[s.step_id] for s in plan.steps if s.step_id in projected]
        if status == 'succeeded':
            try:
                from backend.capability_v2.contracts import ArtifactRef
                from .document_snapshots import _validate_snapshot
                for step in plan.steps:
                    if step.operation_id == 'vismockup.document.snapshot@1':
                        _validate_snapshot(projected[step.step_id].result)
                    if step.operation_id == 'vismockup.view.capture@1':
                        ArtifactRef.model_validate(projected[step.step_id].result['artifact'])
            except (ValueError, RuntimeError, KeyError, TypeError):
                status = 'manual_review_required'
        return ConnectorReconciledOutcomeV2(protocol=plan.protocol, record_type='server_reconciliation_v2',
            **{k:getattr(evidence,k) for k in ('plan_id','plan_hash','lease_id','tenant_id','device_id',
                'runtime_generation','runtime_instance_id','journal_sequence','reported_at')},
            overall_status=status, steps=steps, original_outcome=original, evidence=evidence)

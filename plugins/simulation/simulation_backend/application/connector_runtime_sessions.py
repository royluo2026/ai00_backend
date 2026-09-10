"""Authenticated App transport: server time, device proofs, and session fencing."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
import re
import secrets

from backend.contracts.connector_execution_plan_v2 import IDENTITY_PATTERN
from ..data.connector_repository import SimulationConnectorRepository, ConnectorRepositoryError
from ..domain.connector_pairing import verify_possession


class RuntimeSessionService:
    def __init__(self, repository, *, clock=lambda: datetime.now(UTC)):
        self.repository = repository
        self.clock = clock

    def _device(self, device_id, credential, runtime_type):
        row = self.repository.runtime_device(device_id)
        if runtime_type != 'electron' or row['runtime_type'] != runtime_type:
            raise ConnectorRepositoryError('runtime_type_invalid')
        if not credential or not secrets.compare_digest(row['device_credential_hash'] or '', hashlib.sha256(credential.encode()).hexdigest()):
            raise ConnectorRepositoryError('device_credential_invalid')
        return row

    def challenge(self, device_id, device_credential, generation, runtime_instance_id, *, runtime_type, plan_id=None):
        row = self._device(device_id, device_credential, runtime_type)
        if not isinstance(generation, int) or isinstance(generation, bool) or generation != row['runtime_generation']:
            raise ConnectorRepositoryError('runtime_generation_invalid')
        if not re.fullmatch(IDENTITY_PATTERN, runtime_instance_id) or (plan_id is not None and not re.fullmatch(IDENTITY_PATTERN, plan_id)):
            raise ConnectorRepositoryError('runtime_instance_invalid')
        challenge = 'ai00.runtime-possession.v2:' + secrets.token_urlsafe(32)
        expires_at = self.clock() + timedelta(seconds=60)
        self.repository.create_runtime_challenge(row, hashlib.sha256(challenge.encode()).hexdigest(), generation, runtime_instance_id, plan_id, expires_at)
        return {'challenge': challenge, 'expires_at': expires_at, 'device_key_id': row['device_key_id']}

    def _prove(self, device_id, generation, instance, credential, runtime_type, challenge, signature, plan_id=None):
        row = self._device(device_id, credential, runtime_type)
        key = json.loads(row['device_signing_jwk']) if isinstance(row['device_signing_jwk'], str) else row['device_signing_jwk']
        if generation != row['runtime_generation'] or not verify_possession(key, challenge, signature):
            raise ConnectorRepositoryError('runtime_proof_invalid')
        self.repository.consume_runtime_challenge(row, hashlib.sha256(challenge.encode()).hexdigest(), generation, instance, plan_id, self.clock())
        return row

    def register(self, device_id, generation, runtime_instance_id, *, device_credential, runtime_type, challenge, signature):
        self._prove(device_id, generation, runtime_instance_id, device_credential, runtime_type, challenge, signature)
        now = self.clock()
        return self.repository.register_runtime_session(device_id, generation, runtime_instance_id, now, now + timedelta(minutes=5))

    def authenticate(self, token, *, device_id, generation, runtime_instance_id, runtime_type):
        return self.repository.authenticate_runtime(device_id, generation, runtime_instance_id, token, self.clock(), runtime_type)

    def register_reconciliation(self, device_id, generation, runtime_instance_id, *, device_credential, runtime_type, challenge, signature, plan_id):
        self._prove(device_id, generation, runtime_instance_id, device_credential, runtime_type, challenge, signature, plan_id)
        token = secrets.token_urlsafe(32)
        now = self.clock()
        result = self.repository.register_reconciliation_session(device_id, generation, runtime_instance_id, plan_id,
            hashlib.sha256(token.encode()).hexdigest(), now + timedelta(minutes=5), now=now)
        return {**result, 'session_token': token}

    def authenticate_reconciliation(self, token, *, device_id, generation, runtime_instance_id, runtime_type, plan_id):
        return self.repository.authenticate_reconciliation(device_id, generation, runtime_instance_id, token, plan_id, self.clock(), runtime_type)

    def takeover(self, device_id, generation, runtime_instance_id, *, actor_id, tenant_id, reason):
        row = self.repository.runtime_device(device_id)
        if (row['owner_user_gid'], row['tenant_gid']) != (actor_id, tenant_id):
            raise ConnectorRepositoryError('runtime_owner_mismatch')
        if not reason.strip() or len(reason) > 1024:
            raise ConnectorRepositoryError('runtime_takeover_audit_required')
        now = self.clock()
        self.repository.force_takeover(device_id, generation, generation + 1, runtime_instance_id, now, now + timedelta(minutes=5),
            expected_runtime_instance_id=row['current_runtime_instance_id'], expected_session_token_hash=row['session_token_hash'],
            actor_id=actor_id, reason=reason, require_registration=True)
        return {'device_id': device_id, 'runtime_generation': generation + 1, 'runtime_instance_id': runtime_instance_id,
                'audit_ref': f'connector-runtime-takeover:{device_id}:{generation + 1}'}

    def heartbeat(self, token, **pins):
        # The repository authenticates under the same transaction as the write.
        self.repository.heartbeat_runtime(pins['device_id'], pins['generation'], pins['runtime_instance_id'], token, self.clock())
        return {'accepted': True}

    def renew(self, token, **pins):
        now = self.clock()
        return self.repository.renew_runtime(pins['device_id'], pins['generation'], pins['runtime_instance_id'], token, now, now + timedelta(minutes=5))

    def restart(self, new_runtime_instance_id, token, **pins):
        now = self.clock()
        return self.repository.restart_runtime_session(
            pins['device_id'], pins['generation'], pins['runtime_instance_id'], token,
            new_runtime_instance_id, now, now + timedelta(minutes=5),
        )

    def lease(self, token, *, lease_seconds=60, **pins):
        return self.repository.lease_v2_plan(pins['device_id'], pins['generation'], pins['runtime_instance_id'], token, self.clock(), lease_seconds)

    def has_queued_plan(self, token, **pins):
        return self.repository.has_v2_queued_plan(
            pins['device_id'], pins['generation'], pins['runtime_instance_id'],
            token, self.clock(), pins['runtime_type'],
        )

    def probe(self, token, *, plan_id, **pins):
        return self.repository.reconciliation_plan(pins['device_id'], pins['generation'], pins['runtime_instance_id'], token, plan_id, self.clock(), pins['runtime_type'])

    def outcome(self, token, outcome, *, reconcile=False, **pins):
        # The repository verifies the signature and registered key under the
        # same device lock as journal fencing, outcome, and projection intent.
        method = self.repository.mark_reconciled if reconcile else self.repository.complete_v2_plan
        method(pins['device_id'], pins['generation'], pins['runtime_instance_id'], token, outcome, self.clock())
        return {'accepted': True}

    def acknowledge(self, token, outcome, **pins):
        return self.repository.acknowledge_v2_outcome(pins['device_id'], pins['generation'],
            pins['runtime_instance_id'], token, outcome, self.clock())


runtime_session_service = RuntimeSessionService(SimulationConnectorRepository())

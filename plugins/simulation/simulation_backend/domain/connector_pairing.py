"""Browser device-code pairing for one Simulation Connector per AI00 user."""
from __future__ import annotations

import base64
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
import hashlib
import json
import secrets
from typing import Callable

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa, ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import Field, field_validator

from backend.capability_v2.contracts import FrozenModel
from backend.contracts.connector_execution_plan_v1 import canonical_hash
from backend.contracts.connector_execution_plan_v2 import PROTOCOL_V2, _public_key, _decode_signature


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def verify_possession(jwk: dict, challenge: str, signature: str) -> bool:
    try:
        r, s = _decode_signature(signature)
        _public_key(jwk).verify(encode_dss_signature(r, s), challenge.encode(), ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, TypeError, ValueError):
        return False


def bootstrap_public_key(jwk: dict):
    if set(jwk) != {'kty', 'alg', 'n', 'e'} or jwk['kty'] != 'RSA' or jwk['alg'] != 'RSA-OAEP-256':
        raise ValueError('bootstrap_key_invalid')
    def integer(value):
        decoded = base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
        if not decoded or decoded[0] == 0 or base64.urlsafe_b64encode(decoded).rstrip(b'=').decode() != value:
            raise ValueError('bootstrap_key_invalid')
        return int.from_bytes(decoded, 'big')
    key = rsa.RSAPublicNumbers(integer(jwk['e']), integer(jwk['n'])).public_key()
    if not 2048 <= key.key_size <= 4096:
        raise ValueError('bootstrap_key_invalid')
    return key


def encrypt_bootstrap(jwk: dict, plaintext: bytes) -> dict:
    key = AESGCM.generate_key(bit_length=256)
    nonce = secrets.token_bytes(12)
    encrypted = AESGCM(key).encrypt(nonce, plaintext, None)
    wrapped = bootstrap_public_key(jwk).encrypt(key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    encode = lambda value: base64.urlsafe_b64encode(value).rstrip(b'=').decode()
    return {'algorithm': 'RSA-OAEP-256+A256GCM', 'encrypted_key': encode(wrapped), 'nonce': encode(nonce), 'ciphertext': encode(encrypted)}


class PairingError(RuntimeError):
    pass


class PairingRequest(FrozenModel):
    bootstrap_token: str = Field(min_length=1, max_length=512)
    installation_id: str = Field(min_length=1, max_length=191)
    verifier_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    device_name: str = Field(min_length=1, max_length=255)
    runtime_version: str = Field(min_length=1, max_length=64)
    windows_sid_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    masked_windows_user: str = Field(min_length=1, max_length=255)
    ephemeral_public_key: str = Field(min_length=64, max_length=8192)

    @field_validator("ephemeral_public_key")
    @classmethod
    def validate_ephemeral_public_key(cls, value: str) -> str:
        try:
            key = serialization.load_pem_public_key(value.encode("ascii"))
        except (UnicodeEncodeError, ValueError, TypeError) as exc:
            raise ValueError("ephemeral_public_key_invalid") from exc
        if not isinstance(key, rsa.RSAPublicKey) or key.key_size < 2048:
            raise ValueError("ephemeral_public_key_invalid")
        return value

    @classmethod
    def from_verifier(cls, *, verifier: str, **values):
        return cls(verifier_hash=_hash(verifier), **values)


class PairingCreated(FrozenModel):
    pairing_id: str
    user_code: str
    verification_uri: str
    status: str
    expires_at: datetime
    resource_version: int
    bootstrap_id: str | None = None


class BootstrapTicket(FrozenModel):
    bootstrap_id: str
    bootstrap_token: str
    status: str
    expires_at: datetime
    resource_version: int


class BootstrapSummary(FrozenModel):
    bootstrap_id: str
    status: str
    pairing_id: str | None = None
    expires_at: datetime
    resource_version: int


class PairingSummary(FrozenModel):
    pairing_id: str
    user_code: str
    device_name: str
    runtime_version: str
    masked_windows_user: str
    status: str
    expires_at: datetime
    resource_version: int


class PairingCompletion(FrozenModel):
    connector_id: str
    encrypted_credential_envelope: str
    envelope_hash: str
    activation_challenge: str


@dataclass
class PairingRecord:
    pairing_id: str
    user_code: str
    installation_id: str
    verifier_hash: str
    device_name: str
    runtime_version: str
    windows_sid_hash: str
    masked_windows_user: str
    ephemeral_public_key: str
    status: str
    expires_at: datetime
    resource_version: int = 1
    approved_user_gid: str | None = None
    team_gid: str | None = None
    connector_id: str | None = None
    encrypted_envelope: str | None = None
    envelope_hash: str | None = None
    activation_challenge_hash: str | None = None
    activation_status: str = "not_issued"


@dataclass
class BootstrapRecord:
    bootstrap_id: str
    owner_user_gid: str
    team_gid: str
    token_hash: str
    status: str
    expires_at: datetime
    pairing_id: str | None = None
    resource_version: int = 1


class InMemoryPairingRepository:
    def __init__(self):
        self.pairings: dict[str, PairingRecord] = {}
        self.codes: dict[str, str] = {}
        self.bindings: dict[str, dict] = {}
        self.bootstraps: dict[str, BootstrapRecord] = {}

    def create_pairing(self, record: PairingRecord) -> None:
        if record.pairing_id in self.pairings or record.user_code in self.codes:
            raise PairingError("pairing_identity_conflict")
        self.pairings[record.pairing_id] = record
        self.codes[record.user_code] = record.pairing_id

    def by_code(self, user_code: str) -> PairingRecord | None:
        pairing_id = self.codes.get(user_code)
        return self.pairings.get(pairing_id) if pairing_id else None

    def by_id(self, pairing_id: str) -> PairingRecord | None:
        return self.pairings.get(pairing_id)

    def binding_for_user(self, user_gid: str, team_gid: str | None = None) -> dict | None:
        binding = self.bindings.get(user_gid)
        return binding if binding and (team_gid is None or binding.get("team_gid") == team_gid) else None

    def create_bootstrap(self, record: BootstrapRecord) -> None:
        if record.bootstrap_id in self.bootstraps:
            raise PairingError("pairing_bootstrap_conflict")
        self.bootstraps[record.bootstrap_id] = record

    def bootstrap_by_id(self, bootstrap_id: str) -> BootstrapRecord | None:
        return self.bootstraps.get(bootstrap_id)

    def claim_bootstrap(self, token_hash: str, now: datetime) -> BootstrapRecord:
        record = next((item for item in self.bootstraps.values() if item.token_hash == token_hash), None)
        if record is None:
            raise PairingError("pairing_bootstrap_not_found")
        if record.expires_at <= now:
            self.bootstraps[record.bootstrap_id] = replace(record, status="expired")
            raise PairingError("pairing_bootstrap_expired")
        if record.status != "created":
            raise PairingError("pairing_bootstrap_reused")
        claimed = replace(record, status="claimed", resource_version=record.resource_version + 1)
        self.bootstraps[record.bootstrap_id] = claimed
        return claimed

    def create_pairing_from_bootstrap(
        self, token_hash: str, now: datetime, record: PairingRecord,
    ) -> BootstrapRecord:
        pairings_before = dict(self.pairings)
        codes_before = dict(self.codes)
        bootstraps_before = dict(self.bootstraps)
        bootstrap = self.claim_bootstrap(token_hash, now)
        try:
            self.create_pairing(record)
            self.link_bootstrap_pairing(bootstrap.bootstrap_id, record.pairing_id)
        except Exception:
            self.pairings = pairings_before
            self.codes = codes_before
            self.bootstraps = bootstraps_before
            raise
        return self.bootstraps[bootstrap.bootstrap_id]

    def link_bootstrap_pairing(self, bootstrap_id: str, pairing_id: str) -> None:
        record = self.bootstraps.get(bootstrap_id)
        if record is None:
            raise PairingError("pairing_bootstrap_not_found")
        self.bootstraps[bootstrap_id] = replace(record, pairing_id=pairing_id)

    def bootstrap_for_pairing(self, pairing_id: str) -> BootstrapRecord | None:
        return next((item for item in self.bootstraps.values() if item.pairing_id == pairing_id), None)

    def expire_bootstrap(self, bootstrap_id: str, expected_version: int) -> BootstrapRecord:
        record = self.bootstraps.get(bootstrap_id)
        if record is None or record.status != "created" or record.resource_version != expected_version:
            raise PairingError("pairing_bootstrap_version_conflict")
        expired = replace(record, status="expired", resource_version=record.resource_version + 1)
        self.bootstraps[bootstrap_id] = expired
        return expired

    def expire_pairing(self, pairing_id: str, expected_version: int) -> PairingRecord:
        record = self.pairings.get(pairing_id)
        if record is None or record.status not in {"pending", "approved"} or record.resource_version != expected_version:
            raise PairingError("pairing_version_conflict")
        expired = replace(record, status="expired", resource_version=record.resource_version + 1)
        self.pairings[pairing_id] = expired
        return expired

    def cancel_bootstrap(
        self, bootstrap_id: str, owner_user_gid: str, team_gid: str, expected_version: int,
    ) -> BootstrapRecord:
        record = self.bootstraps.get(bootstrap_id)
        if record is None or record.owner_user_gid != owner_user_gid or record.team_gid != team_gid:
            raise PairingError("pairing_bootstrap_not_found")
        if record.status == "active":
            raise PairingError("pairing_bootstrap_active")
        if record.resource_version != expected_version or record.status not in {"created", "claimed"}:
            raise PairingError("pairing_bootstrap_version_conflict")
        if record.pairing_id:
            pairing = self.pairings.get(record.pairing_id)
            if pairing and pairing.status == "pending":
                self.pairings[pairing.pairing_id] = replace(
                    pairing, status="rejected", resource_version=pairing.resource_version + 1,
                )
        cancelled = replace(record, status="cancelled", resource_version=record.resource_version + 1)
        self.bootstraps[bootstrap_id] = cancelled
        return cancelled

    def approve_pairing(self, record: PairingRecord, *, expected_version: int) -> None:
        current = self.pairings.get(record.pairing_id)
        bootstrap = self.bootstrap_for_pairing(record.pairing_id)
        if current is None:
            raise PairingError("pairing_not_found")
        if current.status != "pending" or current.resource_version != expected_version:
            raise PairingError("pairing_version_conflict")
        if bootstrap is None or bootstrap.status != "claimed":
            raise PairingError("pairing_bootstrap_version_conflict")
        self.pairings[record.pairing_id] = record
        self.bootstraps[bootstrap.bootstrap_id] = replace(bootstrap, status="approved", resource_version=bootstrap.resource_version + 1)

    def issue_credential(self, record: PairingRecord, user_gid: str, binding: dict) -> PairingRecord:
        current = self.pairings.get(record.pairing_id)
        if current is None:
            raise PairingError("pairing_not_found")
        if current.activation_status in {"credential_issued", "active"}:
            return current
        existing = self.bindings.get(user_gid)
        if existing and (
            existing["connector_id"] != binding["connector_id"]
            or existing["installation_id"] != binding["installation_id"]
            or existing.get("team_gid") != binding.get("team_gid")
        ):
            raise PairingError("connector_binding_conflict")
        bootstrap = self.bootstrap_for_pairing(record.pairing_id)
        if bootstrap is None or bootstrap.status != "approved":
            raise PairingError("pairing_bootstrap_version_conflict")
        self.bindings[user_gid] = binding
        self.pairings[record.pairing_id] = record
        self.bootstraps[bootstrap.bootstrap_id] = replace(
            bootstrap, status="credential_issued", resource_version=bootstrap.resource_version + 1,
        )
        return record

    def activate_pairing(self, record: PairingRecord, *, expected_version: int) -> None:
        current = self.pairings.get(record.pairing_id)
        if (
            current is None or current.status != "completing"
            or current.activation_status != "credential_issued"
            or current.resource_version != expected_version
        ):
            raise PairingError("pairing_version_conflict")
        binding = self.bindings.get(current.approved_user_gid or "")
        if (
            not binding or binding["connector_id"] != current.connector_id
            or binding.get("pending_pairing_id") != current.pairing_id
        ):
            raise PairingError("connector_binding_conflict")
        bootstrap = self.bootstrap_for_pairing(current.pairing_id)
        if bootstrap is None or bootstrap.status != "credential_issued":
            raise PairingError("pairing_bootstrap_version_conflict")
        self.bindings[current.approved_user_gid or ""] = {
            **binding, "status": "offline",
        }
        self.pairings[current.pairing_id] = replace(
            current, status="completed", activation_status="active",
            resource_version=current.resource_version + 1,
        )
        self.bootstraps[bootstrap.bootstrap_id] = replace(
            bootstrap, status="active", resource_version=bootstrap.resource_version + 1,
        )


class PairingService:
    def __init__(
        self, repository, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        id_factory: Callable[[str], str] | None = None,
        extra_credential_factory: Callable[[str], dict] | None = None,
        verification_uri: str = "/web/simulation_connector/pair.html",
    ):
        self.repository = repository
        self.clock = clock
        self.id_factory = id_factory or self._random_id
        self.extra_credential_factory = extra_credential_factory or (lambda _connector_id: {})
        self.verification_uri = verification_uri

    @staticmethod
    def _random_id(kind: str) -> str:
        if kind == "code":
            return secrets.token_hex(4).upper()
        return f"{kind}-" + secrets.token_hex(16)

    def _v2_attempt(self, pairing_id, actor, call):
        try:
            return call()
        except PairingError as exc:
            self.repository.audit_pairing(pairing_id, 'pairing_rejected', self.clock(), actor=actor, reason=str(exc))
            raise

    def request_v2(self, device_signing_jwk, bootstrap_encryption_jwk, nonce):
        def create():
            try:
                _public_key(device_signing_jwk)
                encryption_key = bootstrap_public_key(bootstrap_encryption_jwk)
            except (ValueError, TypeError, KeyError) as exc:
                raise PairingError('pairing_key_invalid') from exc
            if not isinstance(nonce, str) or not 16 <= len(nonce) <= 512:
                raise PairingError('pairing_nonce_invalid')
            now = self.clock()
            pairing_id = self.id_factory('pairing')
            signing_challenge = 'ai00.app-pairing.v2:' + pairing_id + ':' + secrets.token_urlsafe(32)
            encryption_challenge = secrets.token_urlsafe(32)
            encrypted = encryption_key.encrypt(encryption_challenge.encode(), padding.OAEP(
                mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
            key_id = 'device-key-' + _hash(json.dumps(device_signing_jwk, sort_keys=True, separators=(',', ':')))
            record = dict(pairing_id=pairing_id, protocol=PROTOCOL_V2, device_signing_jwk=device_signing_jwk,
                bootstrap_encryption_jwk=bootstrap_encryption_jwk, bootstrap_nonce_hash=_hash(nonce), device_key_id=key_id,
                signing_challenge_hash=_hash(signing_challenge), activation_challenge_hash=_hash(encryption_challenge),
                status='created', resource_version=1, runtime_type='electron', expires_at=now + timedelta(minutes=5),
                challenge_expires_at=now + timedelta(minutes=5))
            self.repository.create_pairing(record, now)
            return dict(pairing_id=pairing_id, status='created', resource_version=1, expires_at=record['expires_at'],
                        signing_challenge=signing_challenge, encrypted_challenge=base64.urlsafe_b64encode(encrypted).rstrip(b'=').decode())
        return self._v2_attempt(None, None, create)

    @staticmethod
    def _v2_summary(row):
        return {k: row[k] for k in ('pairing_id', 'status', 'resource_version', 'expires_at', 'device_key_id')}

    def bind_v2(self, pairing_id, user_id, tenant_id, *, expected_version):
        if not user_id or not tenant_id:
            raise PairingError('pairing_owner_mismatch')
        return self._v2_attempt(pairing_id, user_id, lambda: self._v2_summary(
            self.repository.bind_pairing(pairing_id, user_id, tenant_id, expected_version, self.clock())))

    def summary_v2(self, pairing_id, user_id, tenant_id):
        def summary():
            row = self.repository.get_pairing(pairing_id)
            if not row or (row['owner_user_gid'], row['tenant_gid']) != (user_id, tenant_id):
                raise PairingError('pairing_owner_mismatch')
            return self._v2_summary(row)
        return self._v2_attempt(pairing_id, user_id, summary)

    def cancel_v2(self, pairing_id, user_id, tenant_id, *, expected_version):
        return self._v2_attempt(pairing_id, user_id, lambda: self._v2_summary(self.repository.close_pairing(
            pairing_id, 'cancelled', self.clock(), user_id=user_id, tenant_id=tenant_id, expected_version=expected_version)))

    def activate_v2(self, pairing_id, signing_challenge, signature, decrypted_challenge):
        def activate():
            row = self.repository.get_pairing(pairing_id)
            if not row:
                raise PairingError('pairing_not_found')
            if row['status'] in ('activated', 'cancelled'):
                raise PairingError('pairing_consumed')
            now = self.clock()
            if row['expires_at'] <= now or row['challenge_expires_at'] <= now:
                if row['status'] != 'expired':
                    self.repository.close_pairing(pairing_id, 'expired', now)
                raise PairingError('pairing_expired')
            if row['status'] != 'user_bound':
                raise PairingError('pairing_not_approved')
            if (not secrets.compare_digest(row['signing_challenge_hash'] or '', _hash(signing_challenge))
                    or not secrets.compare_digest(row['activation_challenge_hash'] or '', _hash(decrypted_challenge))
                    or not verify_possession(row['device_signing_jwk'], signing_challenge, signature)):
                raise PairingError('pairing_proof_invalid')
            device_id = 'app-device-' + secrets.token_hex(16)
            credential = secrets.token_urlsafe(32)
            envelope = encrypt_bootstrap(row['bootstrap_encryption_jwk'], json.dumps(dict(
                device_id=device_id, device_credential=credential, credential_generation=1, runtime_generation=1,
                owner_user_gid=row['owner_user_gid'], tenant_gid=row['tenant_gid'], device_key_id=row['device_key_id'],
                protocol=PROTOCOL_V2, runtime_type=row['runtime_type']), sort_keys=True, separators=(',', ':')).encode())
            self.repository.activate_pairing(row, device_id, _hash(credential), now)
            return dict(device_id=device_id, device_key_id=row['device_key_id'], status='activated',
                bootstrap_key_retained=False, encrypted_credential_envelope=envelope)
        return self._v2_attempt(pairing_id, None, activate)

    def request(self, request: PairingRequest) -> PairingCreated:
        now = self.clock()
        record = PairingRecord(
            pairing_id=self.id_factory("pairing"), user_code=self.id_factory("code"),
            installation_id=request.installation_id,
            verifier_hash=request.verifier_hash,
            device_name=request.device_name, runtime_version=request.runtime_version,
            windows_sid_hash=request.windows_sid_hash,
            masked_windows_user=request.masked_windows_user,
            ephemeral_public_key=request.ephemeral_public_key,
            status="pending", expires_at=now + timedelta(minutes=5),
        )
        bootstrap = self.repository.create_pairing_from_bootstrap(
            _hash(request.bootstrap_token), now, record,
        )
        return PairingCreated(
            pairing_id=record.pairing_id, user_code=record.user_code,
            verification_uri=self.verification_uri, status=record.status,
            expires_at=record.expires_at, resource_version=record.resource_version,
            bootstrap_id=bootstrap.bootstrap_id,
        )

    def bootstrap_create(self, owner_user_gid: str, team_gid: str) -> BootstrapTicket:
        now = self.clock()
        token = secrets.token_urlsafe(32)
        record = BootstrapRecord(
            bootstrap_id=self.id_factory("bootstrap"), owner_user_gid=owner_user_gid,
            team_gid=team_gid, token_hash=_hash(token), status="created",
            expires_at=now + timedelta(minutes=2),
        )
        self.repository.create_bootstrap(record)
        return BootstrapTicket(
            bootstrap_id=record.bootstrap_id, bootstrap_token=token, status=record.status,
            expires_at=record.expires_at, resource_version=record.resource_version,
        )

    def bootstrap_get(self, bootstrap_id: str, owner_user_gid: str, team_gid: str) -> BootstrapSummary:
        record = self.repository.bootstrap_by_id(bootstrap_id)
        if record is None or record.owner_user_gid != owner_user_gid or record.team_gid != team_gid:
            raise PairingError("pairing_bootstrap_not_found")
        if record.expires_at <= self.clock() and record.status == "created":
            record = self.repository.expire_bootstrap(record.bootstrap_id, record.resource_version)
        return BootstrapSummary(
            bootstrap_id=record.bootstrap_id, status=record.status, pairing_id=record.pairing_id,
            expires_at=record.expires_at, resource_version=record.resource_version,
        )

    def bootstrap_cancel(
        self, bootstrap_id: str, owner_user_gid: str, team_gid: str, *, expected_version: int,
    ) -> BootstrapSummary:
        record = self.repository.cancel_bootstrap(
            bootstrap_id, owner_user_gid, team_gid, expected_version,
        )
        return BootstrapSummary(
            bootstrap_id=record.bootstrap_id, status=record.status, pairing_id=record.pairing_id,
            expires_at=record.expires_at, resource_version=record.resource_version,
        )

    def _active(self, record: PairingRecord | None) -> PairingRecord:
        if record is None:
            raise PairingError("pairing_not_found")
        if record.expires_at <= self.clock() and record.status in {"pending", "approved"}:
            self.repository.expire_pairing(record.pairing_id, record.resource_version)
            raise PairingError("pairing_expired")
        return record

    def get_summary(self, user_code: str, actor_user_gid: str, team_gid: str) -> PairingSummary:
        return self._get_summary(self.repository.by_code(user_code), actor_user_gid, team_gid)

    def get_summary_by_pairing_id(
        self, pairing_id: str, actor_user_gid: str, team_gid: str,
    ) -> PairingSummary:
        return self._get_summary(self.repository.by_id(pairing_id), actor_user_gid, team_gid)

    def _get_summary(
        self, value: PairingRecord | None, actor_user_gid: str, team_gid: str,
    ) -> PairingSummary:
        record = self._active(value)
        bootstrap = self.repository.bootstrap_for_pairing(record.pairing_id)
        if bootstrap is None or bootstrap.owner_user_gid != actor_user_gid or bootstrap.team_gid != team_gid:
            raise PairingError("pairing_not_found")
        return PairingSummary(
            pairing_id=record.pairing_id, user_code=record.user_code,
            device_name=record.device_name, runtime_version=record.runtime_version,
            masked_windows_user=record.masked_windows_user,
            status=record.activation_status if record.activation_status != "not_issued" else record.status,
            expires_at=record.expires_at, resource_version=record.resource_version,
        )

    def approve(
        self, user_code: str, actor_user_gid: str, team_gid: str,
        *, expected_version: int,
    ) -> PairingSummary:
        return self._approve(
            self.repository.by_code(user_code), actor_user_gid, team_gid,
            expected_version=expected_version,
        )

    def approve_by_pairing_id(
        self, pairing_id: str, actor_user_gid: str, team_gid: str,
        *, expected_version: int,
    ) -> PairingSummary:
        return self._approve(
            self.repository.by_id(pairing_id), actor_user_gid, team_gid,
            expected_version=expected_version,
        )

    def _approve(
        self, value: PairingRecord | None, actor_user_gid: str, team_gid: str,
        *, expected_version: int,
    ) -> PairingSummary:
        record = self._active(value)
        if record.resource_version != expected_version or record.status != "pending":
            raise PairingError("pairing_version_conflict")
        bootstrap = self.repository.bootstrap_for_pairing(record.pairing_id)
        if bootstrap is None:
            raise PairingError("pairing_bootstrap_not_found")
        if bootstrap.owner_user_gid != actor_user_gid or bootstrap.team_gid != team_gid:
            raise PairingError("pairing_bootstrap_owner_mismatch")
        existing = self.repository.binding_for_user(actor_user_gid, team_gid)
        any_existing = self.repository.binding_for_user(actor_user_gid)
        if any_existing and existing is None:
            raise PairingError("connector_binding_conflict")
        if existing and (
            existing["installation_id"] != record.installation_id
            or existing.get("team_gid") != team_gid
        ):
            raise PairingError("connector_binding_conflict")
        approved = replace(
            record, approved_user_gid=actor_user_gid, team_gid=team_gid,
            status="approved", resource_version=record.resource_version + 1,
        )
        self.repository.approve_pairing(approved, expected_version=expected_version)
        return self._get_summary(approved, actor_user_gid, team_gid)

    def complete(
        self, pairing_id: str, installation_id: str, verifier: str,
    ) -> PairingCompletion:
        record = self._active(self.repository.by_id(pairing_id))
        if record.installation_id != installation_id or not secrets.compare_digest(
            record.verifier_hash, _hash(verifier),
        ):
            raise PairingError("pairing_proof_invalid")
        if record.activation_status in {"credential_issued", "active"}:
            return self._stored_completion(record)
        if record.status != "approved" or not record.approved_user_gid:
            raise PairingError("pairing_not_approved")
        existing = self.repository.binding_for_user(record.approved_user_gid, record.team_gid)
        any_existing = self.repository.binding_for_user(record.approved_user_gid)
        if any_existing and existing is None:
            raise PairingError("connector_binding_conflict")
        if existing and (
            existing["installation_id"] != installation_id
            or existing.get("team_gid") != record.team_gid
        ):
            raise PairingError("connector_binding_conflict")
        connector_id = existing["connector_id"] if existing else self.id_factory("connector")
        connector_token = self.id_factory("token")
        activation_challenge = secrets.token_urlsafe(32)
        plaintext = json.dumps({
            "connector_id": connector_id,
            "installation_id": installation_id,
            "connector_token": connector_token,
            "activation_proof": activation_challenge,
            "bound_user_id": record.approved_user_gid,
            "team_id": record.team_gid,
            **self.extra_credential_factory(connector_id),
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
        public_key = serialization.load_pem_public_key(record.ephemeral_public_key.encode("ascii"))
        envelope_key = AESGCM.generate_key(bit_length=256)
        nonce = secrets.token_bytes(12)
        encrypted_payload = AESGCM(envelope_key).encrypt(nonce, plaintext, None)
        encrypted_key = public_key.encrypt(
            envelope_key,
            padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
        )
        envelope_value = {
            "encrypted_key": base64.b64encode(encrypted_key).decode("ascii"),
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(encrypted_payload[:-16]).decode("ascii"),
            "tag": base64.b64encode(encrypted_payload[-16:]).decode("ascii"),
        }
        envelope = base64.b64encode(json.dumps(
            envelope_value, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).decode("ascii")
        envelope_hash = canonical_hash({"ciphertext": envelope})
        binding = {
            "connector_id": connector_id, "installation_id": installation_id,
            "team_gid": record.team_gid, "token_hash": _hash(connector_token),
            "windows_sid_hash": record.windows_sid_hash,
            "display_name": record.device_name,
            "runtime_version": record.runtime_version,
            "pending_pairing_id": record.pairing_id,
        }
        issued = replace(
            record, connector_id=connector_id, encrypted_envelope=envelope,
            envelope_hash=envelope_hash, activation_challenge_hash=_hash(activation_challenge),
            activation_status="credential_issued", status="completing",
            resource_version=record.resource_version + 1,
        )
        binding["status"] = "pending_activation"
        stored = self.repository.issue_credential(issued, record.approved_user_gid, binding)
        if stored.envelope_hash != issued.envelope_hash:
            return self._stored_completion(stored)
        return PairingCompletion(
            connector_id=connector_id, encrypted_credential_envelope=envelope,
            envelope_hash=envelope_hash, activation_challenge=activation_challenge,
        )

    @staticmethod
    def _stored_completion(record: PairingRecord) -> PairingCompletion:
        return PairingCompletion(
            connector_id=record.connector_id or "",
            encrypted_credential_envelope=record.encrypted_envelope or "",
            envelope_hash=record.envelope_hash or "", activation_challenge="",
        )

    def activate(
        self, pairing_id: str, connector_id: str, activation_proof: str,
    ) -> PairingSummary:
        record = self.repository.by_id(pairing_id)
        if record is None or record.connector_id != connector_id:
            raise PairingError("pairing_not_found")
        if not secrets.compare_digest(record.activation_challenge_hash or "", _hash(activation_proof)):
            raise PairingError("pairing_activation_proof_invalid")
        self.repository.activate_pairing(record, expected_version=record.resource_version)
        activated = self.repository.by_id(pairing_id)
        if activated is None:
            raise PairingError("pairing_not_found")
        return PairingSummary(
            pairing_id=activated.pairing_id, user_code=activated.user_code,
            device_name=activated.device_name, runtime_version=activated.runtime_version,
            masked_windows_user=activated.masked_windows_user, status=activated.activation_status,
            expires_at=activated.expires_at, resource_version=activated.resource_version,
        )


__all__ = [
    "BootstrapRecord", "BootstrapSummary", "BootstrapTicket", "InMemoryPairingRepository", "PairingCompletion", "PairingCreated",
    "PairingError", "PairingRequest", "PairingService", "PairingSummary",
]

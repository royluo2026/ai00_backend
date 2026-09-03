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
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import Field, field_validator

from backend.capability_v2.contracts import FrozenModel
from backend.contracts.connector_execution_plan_v1 import canonical_hash


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class PairingError(RuntimeError):
    pass


class PairingRequest(FrozenModel):
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


class InMemoryPairingRepository:
    def __init__(self):
        self.pairings: dict[str, PairingRecord] = {}
        self.codes: dict[str, str] = {}
        self.bindings: dict[str, dict] = {}

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

    def binding_for_user(self, user_gid: str) -> dict | None:
        return self.bindings.get(user_gid)

    def save_pairing(self, record: PairingRecord) -> None:
        self.pairings[record.pairing_id] = record

    def approve_pairing(self, record: PairingRecord, *, expected_version: int) -> None:
        current = self.pairings.get(record.pairing_id)
        if current is None:
            raise PairingError("pairing_not_found")
        if current.status != "pending" or current.resource_version != expected_version:
            raise PairingError("pairing_version_conflict")
        self.pairings[record.pairing_id] = record

    def complete_pairing(self, record: PairingRecord, user_gid: str, binding: dict) -> None:
        existing = self.bindings.get(user_gid)
        if existing and existing["connector_id"] != binding["connector_id"]:
            raise PairingError("connector_binding_conflict")
        self.bindings[user_gid] = binding
        self.pairings[record.pairing_id] = record


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
        self.repository.create_pairing(record)
        return PairingCreated(
            pairing_id=record.pairing_id, user_code=record.user_code,
            verification_uri=self.verification_uri, status=record.status,
            expires_at=record.expires_at, resource_version=record.resource_version,
        )

    def _active(self, record: PairingRecord | None) -> PairingRecord:
        if record is None:
            raise PairingError("pairing_not_found")
        if record.expires_at <= self.clock() and record.status != "completed":
            record.status = "expired"
            self.repository.save_pairing(record)
            raise PairingError("pairing_expired")
        return record

    def get_summary(self, user_code: str, _actor_user_gid: str) -> PairingSummary:
        record = self._active(self.repository.by_code(user_code))
        return PairingSummary(
            pairing_id=record.pairing_id, user_code=record.user_code,
            device_name=record.device_name, runtime_version=record.runtime_version,
            masked_windows_user=record.masked_windows_user, status=record.status,
            expires_at=record.expires_at, resource_version=record.resource_version,
        )

    def approve(
        self, user_code: str, actor_user_gid: str, team_gid: str,
        *, expected_version: int,
    ) -> PairingSummary:
        record = self._active(self.repository.by_code(user_code))
        if record.resource_version != expected_version or record.status != "pending":
            raise PairingError("pairing_version_conflict")
        existing = self.repository.binding_for_user(actor_user_gid)
        if existing and existing["installation_id"] != record.installation_id:
            raise PairingError("connector_binding_conflict")
        approved = replace(
            record, approved_user_gid=actor_user_gid, team_gid=team_gid,
            status="approved", resource_version=record.resource_version + 1,
        )
        self.repository.approve_pairing(approved, expected_version=expected_version)
        return self.get_summary(user_code, actor_user_gid)

    def complete(
        self, pairing_id: str, installation_id: str, verifier: str,
    ) -> PairingCompletion:
        record = self._active(self.repository.by_id(pairing_id))
        if record.installation_id != installation_id or not secrets.compare_digest(
            record.verifier_hash, _hash(verifier),
        ):
            raise PairingError("pairing_proof_invalid")
        if record.status == "completed":
            return PairingCompletion(
                connector_id=record.connector_id or "",
                encrypted_credential_envelope=record.encrypted_envelope or "",
                envelope_hash=record.envelope_hash or "",
            )
        if record.status != "approved" or not record.approved_user_gid:
            raise PairingError("pairing_not_approved")
        existing = self.repository.binding_for_user(record.approved_user_gid)
        if existing and existing["installation_id"] != installation_id:
            raise PairingError("connector_binding_conflict")
        connector_id = self.id_factory("connector")
        connector_token = self.id_factory("token")
        plaintext = json.dumps({
            "connector_id": connector_id,
            "connector_token": connector_token,
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
        }
        record.connector_id = connector_id
        record.encrypted_envelope = envelope
        record.envelope_hash = envelope_hash
        record.status = "completed"
        record.resource_version += 1
        self.repository.complete_pairing(record, record.approved_user_gid, binding)
        return PairingCompletion(
            connector_id=connector_id, encrypted_credential_envelope=envelope,
            envelope_hash=envelope_hash,
        )


__all__ = [
    "InMemoryPairingRepository", "PairingCompletion", "PairingCreated",
    "PairingError", "PairingRequest", "PairingService", "PairingSummary",
]

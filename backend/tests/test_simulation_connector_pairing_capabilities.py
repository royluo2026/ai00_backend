from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from plugins.simulation.simulation_backend.domain.connector_pairing import (
    InMemoryPairingRepository,
    PairingError,
    PairingRequest,
    PairingService,
)


NOW = datetime(2026, 9, 3, 8, 0, tzinfo=UTC)


def _request(installation_id="install-1", verifier="proof-1"):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    return PairingRequest.from_verifier(
        installation_id=installation_id,
        verifier=verifier,
        device_name="工位 A",
        runtime_version="1.0.0",
        windows_sid_hash="a" * 64,
        masked_windows_user="DOMAIN\\l***",
        ephemeral_public_key=public_key,
    )


def _service():
    counters = {}

    def identifier(kind):
        counters[kind] = counters.get(kind, 0) + 1
        values = {
            "pairing": f"pair-{counters[kind]}",
            "code": f"CODE-{counters[kind]}",
            "connector": f"connector-{counters[kind]}",
            "token": "token-secret" if counters[kind] == 1 else f"token-{counters[kind]}",
        }
        return values[kind]

    return PairingService(
        InMemoryPairingRepository(), clock=lambda: NOW,
        id_factory=identifier,
    )


def test_pairing_rejects_invalid_ephemeral_public_key_before_approval():
    with pytest.raises(ValidationError, match="ephemeral_public_key_invalid"):
        PairingRequest.from_verifier(
            installation_id="install-1", verifier="proof-1", device_name="工位 A",
            runtime_version="1.0.0", windows_sid_hash="a" * 64,
            masked_windows_user="DOMAIN\\l***", ephemeral_public_key="x" * 64,
        )


def test_user_code_cannot_complete_without_verifier():
    service = _service()
    request = _request()
    created = service.request(request)
    service.approve(created.user_code, "user-1", "team-1", expected_version=1)

    with pytest.raises(PairingError, match="pairing_proof_invalid"):
        service.complete(created.pairing_id, request.installation_id, "wrong-proof")


def test_pairing_summary_contains_only_safe_display_fields():
    service = _service()
    created = service.request(_request())

    summary = service.get_summary(created.user_code, "user-1")

    assert set(summary.model_dump()) == {
        "pairing_id", "user_code", "device_name", "runtime_version",
        "masked_windows_user", "status", "expires_at", "resource_version",
    }


def test_one_user_cannot_silently_replace_binding():
    service = _service()
    first = service.request(_request("install-1", "proof-1"))
    service.approve(first.user_code, "user-1", "team-1", expected_version=1)
    service.complete(first.pairing_id, "install-1", "proof-1")
    second = service.request(_request("install-2", "proof-2"))

    with pytest.raises(PairingError, match="connector_binding_conflict"):
        service.approve(second.user_code, "user-1", "team-1", expected_version=1)


def test_completion_retry_returns_same_encrypted_envelope():
    service = _service()
    created = service.request(_request())
    service.approve(created.user_code, "user-1", "team-1", expected_version=1)

    first = service.complete(created.pairing_id, "install-1", "proof-1")
    second = service.complete(created.pairing_id, "install-1", "proof-1")

    assert second.envelope_hash == first.envelope_hash
    assert second.encrypted_credential_envelope == first.encrypted_credential_envelope
    assert "token-secret" not in second.encrypted_credential_envelope


def test_completion_persists_binding_and_pairing_through_one_repository_operation():
    class AtomicRepository(InMemoryPairingRepository):
        def __init__(self):
            super().__init__()
            self.atomic_completion_called = False

        def create_binding(self, *_args, **_kwargs):
            raise AssertionError("completion must not persist the binding separately")

        def complete_pairing(self, record, user_gid, binding):
            self.atomic_completion_called = True
            super().complete_pairing(record, user_gid, binding)

    repository = AtomicRepository()
    service = PairingService(
        repository,
        clock=lambda: NOW,
        id_factory=lambda kind: {
            "pairing": "pair-atomic",
            "code": "CODE-ATOMIC",
            "connector": "connector-atomic",
            "token": "token-atomic",
        }[kind],
    )
    created = service.request(_request())
    service.approve(created.user_code, "user-1", "team-1", expected_version=1)

    service.complete(created.pairing_id, "install-1", "proof-1")

    assert repository.atomic_completion_called is True
    assert repository.binding_for_user("user-1")["connector_id"] == "connector-atomic"
    assert repository.by_id(created.pairing_id).status == "completed"

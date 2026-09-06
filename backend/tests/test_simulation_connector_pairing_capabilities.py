from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import base64
import json

import pytest
from pydantic import ValidationError
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from plugins.simulation.simulation_backend.domain.connector_pairing import (
    InMemoryPairingRepository,
    PairingError,
    PairingRequest,
    PairingService,
)
from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext
from backend.capabilities.registry_next import CapabilityRegistry
from backend.capability_v2.catalog import CatalogResolver, build_release
from backend.capability_v2.catalog_store import InMemoryCatalogStore
from backend.capability_v2.contracts import (
    ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType,
    InvocationEnvelope, TenantIdentity,
)
from backend.capability_v2.gateway import CapabilityGatewayService
from backend.capability_v2.outcomes import InMemoryOutcomeStore
from backend.capability_v2.reliability import InMemoryRateLimiter, ReliabilityCoordinator
from plugins.simulation.simulation_backend.capabilities.connector_pairing import (
    ConnectorPairingProvider,
    specs,
)
from plugins.simulation.simulation_backend.capabilities.provider import descriptor_for, register


NOW = datetime(2026, 9, 3, 8, 0, tzinfo=UTC)


def _request(installation_id="install-1", verifier="proof-1"):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    return PairingRequest.from_verifier(
        bootstrap_token="placeholder",
        installation_id=installation_id,
        verifier=verifier,
        device_name="工位 A",
        runtime_version="1.0.0",
        windows_sid_hash="a" * 64,
        masked_windows_user="DOMAIN\\l***",
        ephemeral_public_key=public_key,
    )


def _request_with_private_key(installation_id="install-1", verifier="proof-1"):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    return PairingRequest.from_verifier(
        bootstrap_token="placeholder",
        installation_id=installation_id, verifier=verifier, device_name="工位 A",
        runtime_version="1.0.0", windows_sid_hash="a" * 64,
        masked_windows_user="DOMAIN\\l***", ephemeral_public_key=public_key,
    ), key


def _activation_proof(envelope: str, private_key) -> str:
    value = json.loads(base64.b64decode(envelope))
    key = private_key.decrypt(
        base64.b64decode(value["encrypted_key"]),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None,
        ),
    )
    plaintext = AESGCM(key).decrypt(
        base64.b64decode(value["nonce"]),
        base64.b64decode(value["ciphertext"]) + base64.b64decode(value["tag"]), None,
    )
    return json.loads(plaintext)["activation_proof"]


def _service():
    counters = {}

    def identifier(kind):
        counters[kind] = counters.get(kind, 0) + 1
        values = {
            "pairing": f"pair-{counters[kind]}",
            "code": f"CODE-{counters[kind]}",
            "connector": f"connector-{counters[kind]}",
            "token": "token-secret" if counters[kind] == 1 else f"token-{counters[kind]}",
            "bootstrap": f"bootstrap-{counters[kind]}",
        }
        return values[kind]

    return PairingService(
        InMemoryPairingRepository(), clock=lambda: NOW,
        id_factory=identifier,
    )


def _provider_contexts():
    provider = ConnectorPairingProvider(_service())
    return (
        provider,
        CapabilityContext(user_gid="user-1", team_gid="team-1", source="web"),
        CapabilityContext(user_gid="connector-1", source="local_runtime"),
    )


def _request_for(service, installation_id="install-1", verifier="proof-1", *, user="user-1", team="team-1"):
    ticket = service.bootstrap_create(user, team)
    return _request(installation_id, verifier).model_copy(update={"bootstrap_token": ticket.bootstrap_token})


def test_bootstrap_is_user_scoped_and_pair_request_claims_it_once():
    provider, web, local = _provider_contexts()

    ticket = provider.bootstrap_create({}, web).data
    request = _request().model_copy(update={"bootstrap_token": ticket["bootstrap_token"]})

    claimed = provider.request(request.model_dump(), local).data

    assert claimed["bootstrap_id"] == ticket["bootstrap_id"]
    with pytest.raises(CapabilityBusinessError, match="pairing_bootstrap_reused"):
        provider.request(request.model_dump(), local)


def test_bootstrap_projection_is_owner_scoped_and_never_exposes_secret_material():
    provider, web, _local = _provider_contexts()
    ticket = provider.bootstrap_create({}, web).data

    value = provider.bootstrap_get({"bootstrap_id": ticket["bootstrap_id"]}, web).data

    assert not ({"bootstrap_token", "token_hash", "verifier_hash", "ephemeral_public_key"} & value.keys())
    with pytest.raises(CapabilityBusinessError, match="pairing_bootstrap_not_found"):
        provider.bootstrap_get(
            {"bootstrap_id": ticket["bootstrap_id"]},
            CapabilityContext(user_gid="user-2", team_gid="team-1", source="web"),
        )


def test_bootstrap_projection_and_cancel_require_the_original_team_scope():
    provider, web, _local = _provider_contexts()
    ticket = provider.bootstrap_create({}, web).data
    other_team = CapabilityContext(user_gid="user-1", team_gid="team-2", source="web")

    with pytest.raises(CapabilityBusinessError, match="pairing_bootstrap_not_found"):
        provider.bootstrap_get({"bootstrap_id": ticket["bootstrap_id"]}, other_team)
    with pytest.raises(CapabilityBusinessError, match="pairing_bootstrap_not_found"):
        provider.cancel({
            "bootstrap_id": ticket["bootstrap_id"],
            "expected_version": ticket["resource_version"],
        }, other_team)


def test_pairing_request_claims_ticket_and_creates_pairing_through_one_repository_operation():
    class AtomicRequestRepository(InMemoryPairingRepository):
        def __init__(self):
            super().__init__()
            self.atomic_request_called = False

        def create_pairing_from_bootstrap(self, token_hash, now, record):
            self.atomic_request_called = True
            return super().create_pairing_from_bootstrap(token_hash, now, record)

    repository = AtomicRequestRepository()
    service = PairingService(repository, clock=lambda: NOW)
    request = _request_for(service)

    service.request(request)

    assert repository.atomic_request_called is True


def test_active_bootstrap_cannot_be_cancelled():
    service = _service()
    ticket = service.bootstrap_create("user-1", "team-1")
    created = service.request(_request().model_copy(update={"bootstrap_token": ticket.bootstrap_token}))
    service.approve(created.user_code, "user-1", "team-1", expected_version=1)
    issued = service.complete(created.pairing_id, "install-1", "proof-1")
    service.activate(created.pairing_id, issued.connector_id, issued.activation_challenge)
    bootstrap = service.bootstrap_get(ticket.bootstrap_id, "user-1", "team-1")

    with pytest.raises(PairingError, match="pairing_bootstrap_active"):
        service.bootstrap_cancel(
            ticket.bootstrap_id, "user-1", "team-1", expected_version=bootstrap.resource_version,
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
    request = _request_for(service)
    created = service.request(request)
    service.approve(created.user_code, "user-1", "team-1", expected_version=1)

    with pytest.raises(PairingError, match="pairing_proof_invalid"):
        service.complete(created.pairing_id, request.installation_id, "wrong-proof")


def test_pairing_summary_contains_only_safe_display_fields():
    service = _service()
    created = service.request(_request_for(service))

    summary = service.get_summary(created.user_code, "user-1")

    assert set(summary.model_dump()) == {
        "pairing_id", "user_code", "device_name", "runtime_version",
        "masked_windows_user", "status", "expires_at", "resource_version",
    }


def test_read_providers_return_required_governance_evidence():
    service = _service()
    created = service.request(_request_for(service))
    provider = ConnectorPairingProvider(service)
    context = CapabilityContext(user_gid="user-1", source="web")

    summary = provider.summary({"user_code": created.user_code}, context)
    binding = provider.binding({}, context)

    assert summary.evidence and summary.evidence[0].digest
    assert binding.evidence and binding.evidence[0].digest


def test_one_user_cannot_silently_replace_binding():
    service = _service()
    first = service.request(_request_for(service, "install-1", "proof-1"))
    service.approve(first.user_code, "user-1", "team-1", expected_version=1)
    service.complete(first.pairing_id, "install-1", "proof-1")
    second = service.request(_request_for(service, "install-2", "proof-2"))

    with pytest.raises(PairingError, match="connector_binding_conflict"):
        service.approve(second.user_code, "user-1", "team-1", expected_version=1)


def test_concurrent_pairing_approval_cannot_overwrite_first_feishu_user():
    class RacingRepository(InMemoryPairingRepository):
        def approve_pairing(self, record, *, expected_version):
            current = self.pairings[record.pairing_id]
            if current.status == "pending":
                self.pairings[record.pairing_id] = type(current)(
                    **{**current.__dict__, "status": "approved", "resource_version": 2,
                       "approved_user_gid": "user-winner", "team_gid": "team-winner"}
                )
            super().approve_pairing(record, expected_version=expected_version)

    repository = RacingRepository()
    service = PairingService(repository, clock=lambda: NOW)
    created = service.request(_request_for(service, user="user-loser", team="team-loser"))

    with pytest.raises(PairingError, match="pairing_version_conflict"):
        service.approve(created.user_code, "user-loser", "team-loser", expected_version=1)

    stored = repository.by_id(created.pairing_id)
    assert stored.approved_user_gid == "user-winner"
    assert stored.team_gid == "team-winner"


def test_completion_retry_returns_same_encrypted_envelope():
    service = _service()
    created = service.request(_request_for(service))
    service.approve(created.user_code, "user-1", "team-1", expected_version=1)

    first = service.complete(created.pairing_id, "install-1", "proof-1")
    second = service.complete(created.pairing_id, "install-1", "proof-1")

    assert second.envelope_hash == first.envelope_hash
    assert second.encrypted_credential_envelope == first.encrypted_credential_envelope
    assert "token-secret" not in second.encrypted_credential_envelope


def test_credential_issue_does_not_claim_active_until_connector_ack():
    service = _service()
    created = service.request(_request_for(service))
    service.approve(created.user_code, "user-1", "team-1", expected_version=1)

    issued = service.complete(created.pairing_id, "install-1", "proof-1")

    assert issued.activation_challenge
    assert service.repository.by_id(created.pairing_id).activation_status == "credential_issued"
    assert service.repository.binding_for_user("user-1")["status"] == "pending_activation"


def test_same_installation_retry_returns_same_envelope_without_second_binding():
    service = _service()
    created = service.request(_request_for(service))
    service.approve(created.user_code, "user-1", "team-1", expected_version=1)

    first = service.complete(created.pairing_id, "install-1", "proof-1")
    second = service.complete(created.pairing_id, "install-1", "proof-1")

    assert second.encrypted_credential_envelope == first.encrypted_credential_envelope
    assert len(service.repository.bindings) == 1


def test_replayed_envelope_recovers_activation_proof_after_lost_first_response():
    service = _service()
    request, private_key = _request_with_private_key()
    request = request.model_copy(update={
        "bootstrap_token": service.bootstrap_create("user-1", "team-1").bootstrap_token,
    })
    created = service.request(request)
    service.approve(created.user_code, "user-1", "team-1", expected_version=1)
    service.complete(created.pairing_id, "install-1", "proof-1")

    replay = service.complete(created.pairing_id, "install-1", "proof-1")
    proof = _activation_proof(replay.encrypted_credential_envelope, private_key)
    summary = service.activate(created.pairing_id, replay.connector_id, proof)

    assert replay.activation_challenge == ""
    assert summary.status == "active"


def test_completion_returns_the_envelope_that_won_a_repository_race():
    class RacingRepository(InMemoryPairingRepository):
        def issue_credential(self, record, user_gid, binding):
            winner = type(record)(
                **{**record.__dict__, "encrypted_envelope": "winner-envelope", "envelope_hash": "sha256:winner"}
            )
            super().issue_credential(winner, user_gid, binding)
            return super().issue_credential(record, user_gid, binding)

    service = PairingService(RacingRepository(), clock=lambda: NOW, id_factory=lambda kind: {
        "pairing": "pair-race", "code": "CODE-RACE", "connector": "connector-race", "token": "token-race", "bootstrap": "bootstrap-race",
    }[kind])
    created = service.request(_request_for(service))
    service.approve(created.user_code, "user-1", "team-1", expected_version=1)

    completed = service.complete(created.pairing_id, "install-1", "proof-1")

    assert completed.encrypted_credential_envelope == "winner-envelope"
    assert completed.envelope_hash == "sha256:winner"


def test_activation_acknowledgement_marks_the_binding_active():
    service = _service()
    created = service.request(_request_for(service))
    service.approve(created.user_code, "user-1", "team-1", expected_version=1)
    issued = service.complete(created.pairing_id, "install-1", "proof-1")

    summary = service.activate(created.pairing_id, issued.connector_id, issued.activation_challenge)

    assert summary.status == "active"
    assert service.repository.by_id(created.pairing_id).activation_status == "active"
    assert service.repository.binding_for_user("user-1")["status"] == "offline"


def test_activation_rejects_invalid_bootstrap_before_mutating_pairing_or_binding():
    service = _service()
    created = service.request(_request_for(service))
    service.approve(created.user_code, "user-1", "team-1", expected_version=1)
    issued = service.complete(created.pairing_id, "install-1", "proof-1")
    bootstrap = service.repository.bootstrap_for_pairing(created.pairing_id)
    service.repository.bootstraps[bootstrap.bootstrap_id] = type(bootstrap)(
        **{**bootstrap.__dict__, "status": "cancelled"}
    )

    with pytest.raises(PairingError, match="pairing_bootstrap_version_conflict"):
        service.activate(created.pairing_id, issued.connector_id, issued.activation_challenge)

    assert service.repository.by_id(created.pairing_id).activation_status == "credential_issued"
    assert service.repository.binding_for_user("user-1")["status"] == "pending_activation"


def test_pairing_browser_capabilities_are_not_exposed_to_api_agents_or_mcp():
    descriptors = {spec.id: descriptor_for(spec) for spec, _handler in specs(ConnectorPairingProvider(_service()))}

    for capability_id in {
        "simulation.connector.pairing.bootstrap.create",
        "simulation.connector.pairing.bootstrap.get",
        "simulation.connector.pairing.summary.get",
        "simulation.connector.pairing.approve",
        "simulation.connector.pairing.cancel",
        "simulation.connector.binding.get",
    }:
        exposure = descriptors[capability_id].exposure
        assert exposure.web is True
        assert exposure.api is False
        assert exposure.agent is False
        assert exposure.mcp is False


def test_registered_pairing_completion_passes_the_real_gateway_output_contract():
    service = _service()
    request = _request_for(service)
    created = service.request(request)
    service.approve(created.user_code, "user-1", "team-1", expected_version=1)
    registry = CapabilityRegistry()
    for spec, handler in specs(ConnectorPairingProvider(service)):
        register(registry, spec, handler)
    registered = registry.get("simulation.connector.pairing.complete", 1)
    release = build_release([registered.descriptor])
    store = InMemoryCatalogStore()
    store.publish(release)

    class Policy:
        def authorize(self, *_args): return None
        def approve(self, *_args): return None
        def project(self, _descriptor, _identity, data): return data

    gateway = CapabilityGatewayService(
        CatalogResolver(store, registry), Policy(),
        reliability=ReliabilityCoordinator(InMemoryOutcomeStore(), InMemoryRateLimiter(limit=10)),
    ).bind_release(release.release_id)
    result = asyncio.run(gateway.invoke(InvocationEnvelope(
        capability_id=registered.spec.id, major_version=registered.spec.version,
        catalog_release=release.release_id,
        payload={
            "pairing_id": created.pairing_id,
            "installation_id": request.installation_id,
            "verifier": "proof-1",
        },
        identity=ConsumerIdentity(
            actor=ActorIdentity(
                user_id="connector-installer", authentication_method="connector_bootstrap",
                authenticated_at=NOW,
            ),
            tenant=TenantIdentity(tenant_id="team-1", membership="member"),
            consumer=ConsumerDescriptor(
                type=ConsumerType.LOCAL_RUNTIME, consumer_id="ai00.connector.service",
            ),
        ),
        request_id="req-pairing-complete", trace_id="trace-pairing-complete",
        idempotency_key="idem-pairing-complete",
    )))

    assert result.ok is True
    assert result.data["activation_challenge"]
    assert result.evidence and result.evidence[0].kind == "simulation.connector.binding"


def test_credential_issue_persists_binding_and_pairing_through_one_repository_operation():
    class AtomicRepository(InMemoryPairingRepository):
        def __init__(self):
            super().__init__()
            self.atomic_completion_called = False

        def create_binding(self, *_args, **_kwargs):
            raise AssertionError("completion must not persist the binding separately")

        def issue_credential(self, record, user_gid, binding):
            self.atomic_completion_called = True
            return super().issue_credential(record, user_gid, binding)

    repository = AtomicRepository()
    service = PairingService(
        repository,
        clock=lambda: NOW,
        id_factory=lambda kind: {
            "pairing": "pair-atomic",
            "code": "CODE-ATOMIC",
            "connector": "connector-atomic",
            "token": "token-atomic",
            "bootstrap": "bootstrap-atomic",
        }[kind],
    )
    created = service.request(_request_for(service))
    service.approve(created.user_code, "user-1", "team-1", expected_version=1)

    service.complete(created.pairing_id, "install-1", "proof-1")

    assert repository.atomic_completion_called is True
    assert repository.binding_for_user("user-1")["connector_id"] == "connector-atomic"
    assert repository.by_id(created.pairing_id).activation_status == "credential_issued"

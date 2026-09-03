"""Cross-language acceptance tests for Local Integration protocol V2."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.capabilities.validation_next import validate_payload
from backend.domain_ports.local_integration import (
    LocalOperationEnvelope, LocalOperationOutcome, canonical_json_bytes,
    sign_operation_envelope, sign_operation_outcome, verify_operation_outcome,
)
from plugins.device.device_backend.capabilities.contracts import INPUT_SCHEMAS
from plugins.device.device_backend.capabilities import register_capabilities
from plugins.device.device_backend import control_plane
from backend.capabilities.registry_next import CapabilityRegistry
from backend.domain_ports.local_integration import verify_operation_signature
from backend.domain_ports.resource_authorization import ResourceAuthorizerRegistry
from backend.capability_v2.contracts import ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType, InvocationEnvelope, OperationRef, OperationStatus, TenantIdentity
from backend.capability_v2.operations import InMemoryOperationStore, OperationRecord, TrustedExternalOperationReconciler
from backend.capability_v2.authorization import AuthorizationGrants
from backend.capability_v2.policies import LegacyServerGatewayPolicy


ROOT = Path(__file__).resolve().parents[2]
VECTORS = json.loads((Path(__file__).with_name("fixtures") / "device_protocol_vectors.json").read_text(encoding="utf-8"))["vectors"]


def test_python_canonical_signature_matches_shared_dotnet_vector():
    vector = VECTORS[0]
    envelope = LocalOperationEnvelope.model_validate(vector["envelope"])
    assert envelope.payload_hash == vector["payload_hash"]
    assert sign_operation_envelope(envelope, vector["secret"]) == vector["signature"]
    outcome = LocalOperationOutcome.model_validate(vector["outcome"])
    assert sign_operation_outcome(outcome, vector["secret"]) == vector["outcome_signature"]
    canonical = canonical_json_bytes(envelope.model_dump(mode="json")).decode("utf-8")
    assert canonical.startswith('{"capability_id":"vismockup.model.open"')
    assert " " not in canonical


def test_local_model_open_accepts_only_artifact_refs_and_rejects_paths():
    payload = VECTORS[0]["envelope"]["payload"]
    validate_payload(INPUT_SCHEMAS["vismockup.model.open"], payload)
    for field, value in (("file_path", "C:\\secret.jt"), ("path", "/srv/model.jt"), ("uri", "file:///secret.jt")):
        with pytest.raises(ValueError, match="unknown field"):
            validate_payload(INPUT_SCHEMAS["vismockup.model.open"], {**payload, field: value})


def test_envelope_is_closed_and_payload_hash_is_verified():
    vector = VECTORS[0]
    with pytest.raises(ValueError):
        LocalOperationEnvelope.model_validate({**vector["envelope"], "secret": vector["secret"]})
    with pytest.raises(ValueError, match="payload_hash_mismatch"):
        LocalOperationEnvelope.model_validate({**vector["envelope"], "payload": {"device_id": "other"}})


def test_dotnet_contract_declares_canonical_json_key_rotation_and_crash_recovery():
    contracts = (ROOT / "local-runtime/src/Ai00.Connector.Contracts/Contracts.cs").read_text(encoding="utf-8")
    ledger = (ROOT / "local-runtime/src/Ai00.Connector.SessionHost/CommandLedger.cs").read_text(encoding="utf-8")
    worker = (ROOT / "local-runtime/src/Ai00.Connector.Service/RuntimeWorker.cs").read_text(encoding="utf-8")
    pipe_host = (ROOT / "local-runtime/src/Ai00.Connector.SessionHost/CommandPipeHost.cs").read_text(encoding="utf-8")
    gateway = (ROOT / "local-runtime/src/Ai00.Connector.Service/DeviceGatewayClient.cs").read_text(encoding="utf-8")
    dispatcher = (ROOT / "local-runtime/src/Ai00.Connector.SessionHost/CommandDispatcher.cs").read_text(encoding="utf-8")
    assert "CanonicalJson" in contracts
    assert "KeyId" in contracts
    assert "ai00.local-operation.v2" in contracts
    assert "outcome_unknown" in ledger
    assert "started" in ledger
    assert "outcome_unknown" in worker
    assert "PipeOptions.CurrentUserOnly" in pipe_host
    assert "IncrementalHash" in gateway and "artifact_integrity_failed" in gateway
    assert "Path.GetFullPath(artifactCacheRoot)" in dispatcher
    assert "SHA256.HashData(stream)" in dispatcher
    for capability_id in (
        "vismockup.status", "vismockup.launch", "vismockup.model.open", "vismockup.tree",
        "vismockup.highlight", "vismockup.visibility", "vismockup.capture",
    ):
        assert capability_id in dispatcher
    assert "result-artifact" in gateway and "artifact_ref" in gateway


def test_cloud_lease_is_signed_and_binds_lease_to_operation(monkeypatch):
    monkeypatch.setenv("AI00_LOCAL_OPERATION_SIGNING_KEY_ID", "key-2026-08")
    monkeypatch.setenv("AI00_LOCAL_OPERATION_SIGNING_SECRET", "shared-test-secret-at-least-32-bytes-long")
    vector = VECTORS[0]["envelope"]
    row = {
        "gid": "operation_local_1", "requested_by": "user-1", "team_gid": "tenant-a",
        "capability_id": "vismockup.model.open", "payload": json.dumps(vector["payload"]),
        "expires_at": "2026-08-10T12:05:00Z",
    }
    # Database drivers return datetime; this also proves transport code never accepts caller paths.
    from datetime import datetime, timezone
    row["expires_at"] = datetime(2026, 8, 10, 12, 5, tzinfo=timezone.utc)
    lease = control_plane.build_signed_lease(row, "lease-1", now=datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc))
    operation = LocalOperationEnvelope.model_validate(lease["operation"])
    assert lease["lease_id"] == "lease-1"
    assert operation.operation_id == "operation_local_1"
    assert operation.tenant_id == "tenant-a"
    assert verify_operation_signature(operation, lease["signature"], {"key-2026-08": "shared-test-secret-at-least-32-bytes-long"})
    with pytest.raises(RuntimeError, match="queued_payload_integrity_failed"):
        control_plane.build_signed_lease({**row, "payload_hash": "0" * 64}, "lease-2")


def test_native_local_provider_deprecates_direct_vismockup_exposure():
    registry = CapabilityRegistry()
    register_capabilities(registry)
    registrations = {item.spec.id: item for item in registry.snapshot()}
    assert set(registrations) == set(INPUT_SCHEMAS)
    for capability_id, registration in registrations.items():
        descriptor = registration.descriptor
        assert descriptor.owner_domain == "device"
        if capability_id.startswith("local.device."):
            assert descriptor.lifecycle_status.value == "deprecated"
            assert descriptor.input_schema["properties"]["operation"]["enum"] == []
        elif capability_id.startswith("vismockup."):
            assert descriptor.lifecycle_status.value == "deprecated"
            assert not any(descriptor.exposure.model_dump().values())
        elif capability_id.startswith("device.connector."):
            assert descriptor.lifecycle_status.value == "deprecated"
            assert not any(descriptor.exposure.model_dump().values())
        else:
            assert descriptor.lifecycle_status.value == "stable"
            assert descriptor.exposure.plugin and descriptor.exposure.agent and descriptor.exposure.mcp
        expected_operation_policy = (
            "none"
            if capability_id in {
                "local.command.get", "local.device.read", "device.connector.health.get",
            }
            else "optional"
            if capability_id in {
                "local.device.change.apply", "device.connector.plan.queue",
            }
            else "required"
        )
        assert descriptor.operation_policy == expected_operation_policy


@pytest.mark.parametrize("status,error_code", [
    ("failed", ""), ("outcome_unknown", ""), ("succeeded", ""), ("failed", "raw error with spaces"),
])
def test_completion_contract_rejects_ambiguous_or_unsanitized_outcomes(status, error_code):
    with pytest.raises(ValueError):
        control_plane.complete_command("device-1", "operation-1", "lease-1", status, error_code=error_code)


def test_completion_result_rejects_local_paths_before_storage():
    with pytest.raises(ValueError, match="forbidden_transport_field"):
        control_plane.complete_command(
            "device-1", "operation-1", "lease-1", "completed",
            result={"path": "C:\\secret\\capture.png"},
        )


def test_authenticated_device_reconciler_advances_operation_without_unsafe_replay():
    from datetime import datetime, timezone
    now = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    store = InMemoryOperationStore()
    store.create(OperationRecord(
        ref=OperationRef(operation_id="operation-local-1", status=OperationStatus.ACCEPTED),
        kind="vismockup.model.open", tenant_id="tenant-a", actor_id="user-1",
        consumer_id="ai00.agent", created_at=now, updated_at=now,
    ))
    reconciler = TrustedExternalOperationReconciler(store, allowed_kind_prefix="vismockup.")
    claimed = reconciler.reconcile("operation-local-1", OperationStatus.CLAIMED)
    assert claimed.status is OperationStatus.CLAIMED
    unknown = reconciler.reconcile("operation-local-1", OperationStatus.OUTCOME_UNKNOWN, error_code="session_host_unavailable")
    assert unknown.status is OperationStatus.OUTCOME_UNKNOWN
    completed = reconciler.reconcile("operation-local-1", OperationStatus.COMPLETED)
    assert completed.status is OperationStatus.COMPLETED


def test_device_outcome_is_closed_signed_and_requires_explicit_unknown_error():
    from datetime import datetime, timezone
    secret = "device-token-at-least-thirty-two-bytes-long"
    outcome = LocalOperationOutcome(
        protocol="ai00.local-operation.v2", operation_id="operation-local-1",
        status="outcome_unknown", error_code="session_host_unavailable",
        reported_at=datetime(2026, 8, 10, 12, 5, tzinfo=timezone.utc),
    )
    signature = sign_operation_outcome(outcome, secret)
    assert verify_operation_outcome(outcome, signature, secret)
    assert not verify_operation_outcome(outcome, signature, secret + "-wrong")
    with pytest.raises(ValueError, match="error_code_required"):
        LocalOperationOutcome(
            protocol="ai00.local-operation.v2", operation_id="operation-local-1",
            status="outcome_unknown", reported_at=datetime.now(timezone.utc),
        )


def test_legacy_vismockup_tombstone_has_no_device_resource_selector():
    registry = CapabilityRegistry()
    register_capabilities(registry)
    provider = next(item for item in registry.snapshot() if item.spec.id == "vismockup.model.open")
    identity = ConsumerIdentity(
        actor=ActorIdentity(user_id="user-1", authentication_method="jwt", authenticated_at=VECTORS[0]["envelope"]["issued_at"]),
        tenant=TenantIdentity(tenant_id="tenant-a", membership="member"),
        consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id="ai00.web"),
    )
    envelope = InvocationEnvelope(
        capability_id="vismockup.model.open", major_version=1, catalog_release="rel-test",
        payload=VECTORS[0]["envelope"]["payload"], identity=identity,
        request_id="request-1", trace_id="trace-1",
    )
    policy = LegacyServerGatewayPolicy(
        user_loader=lambda _user_id: {"gid": "user-1", "is_active": True},
        grants_resolver=lambda _identity, _user: AuthorizationGrants(
            permissions=("agent.run",), resource_scopes=(), data_scopes=("confidential",),
            policy_version="test", tenant_id="tenant-a",
        ),
        resource_authorizer=lambda ref, _identity, _user: ref in {"device:device_1", "artifact:artifact_model_1"},
    )
    decision = policy.authorize(provider.descriptor, envelope, provider)
    assert decision.allowed
    assert decision.resource_refs == ()
    assert not any(provider.descriptor.exposure.model_dump().values())


def test_legacy_vismockup_tombstone_cannot_retain_device_ownership_policy():
    registry = CapabilityRegistry()
    register_capabilities(registry)
    provider = next(item for item in registry.snapshot() if item.spec.id == "vismockup.model.open")
    identity = ConsumerIdentity(
        actor=ActorIdentity(user_id="user-1", authentication_method="jwt", authenticated_at=VECTORS[0]["envelope"]["issued_at"]),
        tenant=TenantIdentity(tenant_id="tenant-a", membership="member"),
        consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id="ai00.web"),
    )
    envelope = InvocationEnvelope(
        capability_id="vismockup.model.open", major_version=1, catalog_release="rel-test",
        payload=VECTORS[0]["envelope"]["payload"], identity=identity,
        request_id="request-2", trace_id="trace-2",
    )
    policy = LegacyServerGatewayPolicy(
        user_loader=lambda _user_id: {"gid": "user-1", "is_active": True},
        grants_resolver=lambda _identity, _user: AuthorizationGrants(
            permissions=("agent.run",), resource_scopes=(), data_scopes=("confidential",),
            policy_version="test", tenant_id="tenant-a",
        ),
        resource_authorizer=lambda ref, _identity, _user: ref == "device:device_1",
    )
    decision = policy.authorize(provider.descriptor, envelope, provider)
    assert decision.resource_refs == ()
    assert provider.descriptor.resource_selectors == ()


def test_resource_authorizer_registration_is_idempotent_but_cannot_be_overwritten():
    registry = ResourceAuthorizerRegistry()

    def owner(_resource_id, _identity):
        return True

    registry.register("artifact", owner)
    registry.register("artifact", owner)
    with pytest.raises(ValueError, match="already registered"):
        registry.register("artifact", lambda _resource_id, _identity: False)

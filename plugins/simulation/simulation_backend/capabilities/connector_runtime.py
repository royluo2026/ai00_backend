"""Simulation-owned AI00 Connector control plane and VisMockup atoms."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
import os
import secrets

from backend.capability_v2.contracts import OperationRef, OperationStatus
from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError,
    CapabilityContext,
    CapabilityOutput,
    CapabilityRisk,
    CapabilitySpec,
    EvidenceRef,
)
from backend.contracts.connector_execution_plan_v1 import (
    ConnectorExecutionPlanV1,
    ConnectorPlanOutcomeV1,
    ConnectorStepV1,
    ConnectorTargetProductV1,
    canonical_hash,
)
from backend.domain_ports.local_integration import canonical_json_bytes
from backend.contracts.connector_execution_plan_v2 import canonicalize_v2
from plugins.simulation.simulation_backend.application.connector_wakeup import connector_wake_broker
from plugins.simulation.simulation_backend.application.connector_protocol_v2 import PlanSigner
from backend.domain_ports.simulation_runtime import (
    ConnectorOutcomePortProxy,
    GovernedSimulationRuntimeClient,
)

from ..data.connector_repository import (
    ConnectorRepositoryError,
    SimulationConnectorRepository,
)
from .connector_contracts import AdapterAdvertisement, AdapterOperation, ConnectorHealth


class ConnectorError(RuntimeError):
    pass


# Consumer declarations do not add authorization or change existing versions.
DESKTOP_CAPABILITY_BINDINGS = (
    ("simulation.connector.runtime.takeover", 1),
    ("simulation.connector.health.get", 1),
    ("simulation.connector.health.get", 2),
    ("simulation.connector.plan.queue", 2),
    ("simulation.connector.plan.queue", 3),
    ("simulation.environment.preflight", 1),
    ("simulation.vismockup.application.attach.request", 1),
    ("simulation.vismockup.application.launch.request", 1),
    ("simulation.vismockup.model.open.request", 1),
    ("simulation.environment.runtime_package.open.request", 1),
    ("simulation.vismockup.model.insert.request", 1),
    ("simulation.vismockup.model.close.request", 1),
    ("simulation.vismockup.visibility.change.request", 1),
    ("simulation.vismockup.node.visibility.change.request", 1),
    ("simulation.vismockup.node.selection.change.request", 1),
    ("simulation.vismockup.tree.read.request", 1),
    ("simulation.vismockup.command.get", 1),
)

# Device-authenticated protocol adapters are Simulation-owned transports, not
# independent business Capabilities and not Renderer-callable providers.
DESKTOP_TRANSPORT_BINDINGS = tuple(dict(method=method,
    route="/api/v1/simulation/connectors/v2/" + route, handler=handler,
    owner="simulation", provider_ref="simulation.provider", consumer_id="ai00.connector",
    authentication=authentication) for method, route, handler, authentication in (
    ("POST", "pairings", "app_pairing_request", "possession_pairing_bootstrap"),
    ("POST", "pairings/{pairing_id}/activate", "app_pairing_activate", "two_key_possession"),
    ("POST", "runtime/challenge", "runtime_challenge", "device_credential"),
    ("POST", "runtime/register", "runtime_register", "device_credential_and_signature"),
    ("POST", "runtime/reconciliation/register", "runtime_reconciliation_register", "device_credential_and_signature"),
    ("POST", "heartbeat", "runtime_heartbeat", "runtime_session"),
    ("POST", "runtime/renew", "runtime_renew", "runtime_session"),
    ("POST", "plans/lease", "runtime_lease", "runtime_session"),
    ("GET", "plans/{plan_id}/artifacts/{artifact_id}", "runtime_artifact_grant", "runtime_session_and_plan_lease"),
    ("GET", "plans/{plan_id}/artifacts/{artifact_id}/content", "runtime_artifact_content", "runtime_session_and_plan_lease"),
    ("WEBSOCKET", "plans/wake", "runtime_wake", "runtime_session"),
    ("POST", "plans/{plan_id}/outcome", "runtime_outcome", "runtime_session_and_signed_outcome"),
    ("POST", "plans/{plan_id}/acknowledge", "runtime_outcome_acknowledge", "plan_scoped_session_and_exact_stored_outcome"),
    ("GET", "plans/{plan_id}/probe", "runtime_probe", "plan_scoped_reconciliation_session"),
    ("POST", "plans/{plan_id}/reconcile", "runtime_reconcile", "plan_scoped_session_and_signed_evidence"),
))


DIRECT_VISMOCKUP_OPERATIONS = {
    "attach": ("vismockup.application.probe@1", "sha256:197cfad8bc3453030fdc288ea78c3abc21699274dd48d4482444af4f62380a37"),
    "launch": ("vismockup.application.probe@1", "sha256:197cfad8bc3453030fdc288ea78c3abc21699274dd48d4482444af4f62380a37"),
    "open": ("vismockup.model.open@1", "sha256:aabd43bb066794c250f7eeed41def7c147a4da7263e813f192efa59a0cb40e34"),
    "insert": ("vismockup.model.insert@1", "sha256:70e68f565989a75406fabb5ffcc5b6f87233f2e55be9a011b202671a26f7c370"),
    "close": ("vismockup.model.close@1", "sha256:a1a27969ab8638c9868b384ccb546aed1ece56219ded7c7ec3bb3d6b19861771"),
    "visibility": ("vismockup.visibility.change@1", "sha256:6ecb8dd2239a2ca881bfc8d40463778f2b80f15f66f1be50a3ceb91a90bff201"),
    "node_visibility": ("vismockup.node.visibility.change@1", "sha256:b93246b1bb189e3f7e488c4ec0528378cbbf97cd2c3fdd547daf0f2007f05f6c"),
    "node_selection": ("vismockup.node.selection.change@1", "sha256:4ca8699ef27b5de3691dc8e2b6252350e001263e23e805489d16b435b575a539"),
    "tree": ("vismockup.tree.read@1", "sha256:b3c6a014ac8853a3b6689286ce514b7997bb450f6394253d813308afa8863af0"),
}
DIRECT_VISMOCKUP_OPERATION_IDS = frozenset(value[0] for value in DIRECT_VISMOCKUP_OPERATIONS.values())
DIRECT_VISMOCKUP_CAPABILITIES = {
    "attach": "simulation.vismockup.application.attach.request",
    "launch": "simulation.vismockup.application.launch.request",
    "open": "simulation.vismockup.model.open.request",
    "insert": "simulation.vismockup.model.insert.request",
    "close": "simulation.vismockup.model.close.request",
    "visibility": "simulation.vismockup.visibility.change.request",
    "node_visibility": "simulation.vismockup.node.visibility.change.request",
    "node_selection": "simulation.vismockup.node.selection.change.request",
    "tree": "simulation.vismockup.tree.read.request",
}


def connector_plan_signing_material(connector_id: str) -> tuple[str, str]:
    configured_key_id = os.environ.get("AI00_CONNECTOR_PLAN_SIGNING_KEY_ID", "")
    master_secret = os.environ.get("AI00_CONNECTOR_PLAN_SIGNING_SECRET", "")
    if not configured_key_id or len(master_secret.encode("utf-8")) < 32 or not connector_id:
        raise ConnectorError("connector_plan_signing_key_unavailable")
    connector_tag = hashlib.sha256(connector_id.encode("utf-8")).hexdigest()[:16]
    derived = hmac.new(
        master_secret.encode("utf-8"),
        f"ai00.connector.plan.v1:{connector_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    # execution-plan.v1 names this wire identity ``device``; retain it until v2.
    return f"{configured_key_id}.device.{connector_tag}", derived


def sign_connector_plan_lease(
    plan: ConnectorExecutionPlanV1, key_id: str | None = None,
) -> dict[str, str]:
    configured_key_id, secret = connector_plan_signing_material(plan.device_id)
    if key_id is not None and key_id != configured_key_id:
        raise ConnectorError("connector_plan_signing_key_mismatch")
    digest = hmac.new(
        secret.encode("utf-8"),
        canonical_json_bytes(plan.model_dump(mode="json")),
        hashlib.sha256,
    ).hexdigest()
    return {"key_id": configured_key_id, "signature": "hmac-sha256:" + digest}


def _version(value: str) -> tuple[int, ...]:
    try:
        parts = tuple(int(part) for part in value.split("."))
        return parts + (0,) * (4 - len(parts))
    except ValueError as exc:
        raise ConnectorError("connector_version_incompatible") from exc


def require_compatible(plan: ConnectorExecutionPlanV1, health: ConnectorHealth) -> None:
    if plan.protocol not in health.protocol_versions:
        raise ConnectorError("connector_version_incompatible")
    if plan.user_id != health.bound_user_id:
        raise ConnectorError("bound_user_mismatch")
    if not health.user_session_present or not health.session_host_ready:
        raise ConnectorError("interactive_session_missing")
    if not health.system_awake:
        raise ConnectorError("connector_offline")
    adapter = next((
        item for item in health.adapters
        if item.adapter_id == plan.adapter_id and item.adapter_major == plan.adapter_major
    ), None)
    if adapter is None:
        raise ConnectorError("adapter_unavailable")
    target = plan.target_product
    if (
        adapter.product_id != target.product_id
        or _version(adapter.product_version) < _version(target.minimum_version)
        or _version(adapter.product_version) >= _version(target.maximum_version_exclusive)
    ):
        raise ConnectorError("connector_version_incompatible")
    advertised = {item.operation_id: item.contract_hash for item in adapter.operations}
    for step in plan.steps:
        if advertised.get(step.operation_id) != step.contract_hash:
            raise ConnectorError("adapter_contract_mismatch")


class ConnectorControlPlane:
    def __init__(
        self, repository, *, outcome_port=None, clock=lambda: datetime.now(UTC),
        wake_notifier=None, plan_signer=None,
    ):
        self.repository = repository
        self.outcome_port = outcome_port
        self.clock = clock
        self.wake_notifier = wake_notifier
        self.plan_signer = plan_signer

    def queue_v2(
        self, plan, context: CapabilityContext, session_token: str | None = None,
        *, runtime_row: dict | None = None,
    ) -> OperationRef:
        from backend.contracts.connector_execution_plan_v2 import ConnectorExecutionPlanV2
        raw = plan.model_dump(mode='json') if isinstance(plan, ConnectorExecutionPlanV2) else dict(plan)
        if (raw['actor_id'], raw['tenant_id']) != (context.user_gid, context.team_gid):
            raise ConnectorError('plan_identity_mismatch')
        if self.plan_signer is None:
            raise ConnectorError('connector_plan_signing_key_unavailable')
        try:
            row = runtime_row or self.repository.runtime_device(raw['device_id'])
            if (row['owner_user_gid'], row['tenant_gid']) != (context.user_gid, context.team_gid):
                raise ConnectorError('plan_identity_mismatch')
            if row['runtime_type'] != 'electron':
                raise ConnectorError('runtime_type_invalid')
            if session_token is not None:
                self.repository.authenticate_runtime(raw['device_id'], row['runtime_generation'],
                    row['current_runtime_instance_id'], session_token, self.clock(), 'electron')
            raw.update(runtime_generation=row['runtime_generation'], runtime_instance_id=row['current_runtime_instance_id'])
            signed = self.plan_signer.sign(raw)
            self.repository.insert_v2_plan(signed, session_token, self.clock(),
                expected_session_token_hash=row['session_token_hash'])
        except (ConnectorRepositoryError, ValueError) as exc:
            raise ConnectorError(str(exc)) from exc
        if self.wake_notifier is not None:
            self.wake_notifier.notify(signed.device_id)
        return OperationRef(operation_id=signed.plan_id, status=OperationStatus.ACCEPTED)

    def complete_v2(self, session_token, outcome, **pins):
        from ..application.connector_runtime_sessions import RuntimeSessionService
        try:
            return RuntimeSessionService(self.repository, clock=self.clock).outcome(session_token, outcome, **pins)
        except ConnectorRepositoryError as exc:
            raise ConnectorError(str(exc)) from exc

    def record_heartbeat(
        self, connector_id: str, expected_user_id: str, health: ConnectorHealth,
    ) -> None:
        if health.bound_user_id != expected_user_id:
            raise ConnectorError("bound_user_mismatch")
        current = self.repository.get_health(connector_id)
        if (
            current is not None
            and current.reported_at > self.clock() - timedelta(minutes=2)
            and current.user_session_present
            and health.user_session_present
            and current.session_id != health.session_id
        ):
            raise ConnectorError("interactive_session_conflict")
        self.repository.save_health(connector_id, health)

    def get_health(self, connector_id: str, context: CapabilityContext) -> ConnectorHealth:
        find_runtime = getattr(self.repository, "bound_runtime_for_user", None)
        runtime = find_runtime(context.user_gid, context.team_gid) if find_runtime else None
        if runtime and runtime.get("device_id") == connector_id:
            now = self.clock()
            heartbeat = runtime.get("heartbeat_at")
            expiry = runtime.get("session_expires_at")
            current_instance = runtime.get("current_runtime_instance_id")
            if not heartbeat or not expiry or not current_instance:
                raise ConnectorError("connector_offline")
            heartbeat = heartbeat.replace(tzinfo=UTC) if heartbeat.tzinfo is None else heartbeat.astimezone(UTC)
            expiry = expiry.replace(tzinfo=UTC) if expiry.tzinfo is None else expiry.astimezone(UTC)
            if heartbeat <= now - timedelta(minutes=2) or expiry <= now:
                raise ConnectorError("connector_offline")
            raw = runtime.get("adapter_health_json")
            advertisement = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(advertisement, dict) or (
                advertisement.get("runtime_generation"), advertisement.get("runtime_instance_id")
            ) != (runtime.get("runtime_generation"), current_instance):
                raise ConnectorError("adapter_health_unavailable")
            try:
                adapter = AdapterAdvertisement.model_validate(advertisement["adapter"])
                observed = advertisement["health"]
                adapter = adapter.model_copy(update={"product_version": observed.get("product_version") or "0.0.0"})
                return ConnectorHealth(
                    connector_version="AppHost-2", protocol_versions=("ai00.connector.execution-plan.v2",),
                    bound_user_id=context.user_gid, session_id=current_instance,
                    user_session_present=bool(observed["ready"]),
                    session_host_ready=bool(observed["ready"] and observed["document_ready"]),
                    system_awake=True, adapters=(adapter,), reported_at=heartbeat,
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ConnectorError("adapter_health_unavailable") from exc
        health = self.repository.get_health(connector_id)
        if health is None:
            raise ConnectorError("connector_offline")
        if health.bound_user_id != context.user_gid:
            raise ConnectorError("bound_user_mismatch")
        return health

    def queue_plan(
        self, plan: ConnectorExecutionPlanV1, context: CapabilityContext,
    ) -> OperationRef:
        if plan.user_id != context.user_gid or plan.tenant_id != context.team_gid:
            raise ConnectorError("plan_identity_mismatch")
        health = self.repository.get_health(plan.device_id)
        if health is None or health.reported_at <= self.clock() - timedelta(minutes=2):
            raise ConnectorError("connector_offline")
        require_compatible(plan, health)
        try:
            self.repository.insert_plan(plan)
        except ConnectorRepositoryError as exc:
            raise ConnectorError(str(exc)) from exc
        if self.wake_notifier is not None:
            self.wake_notifier.notify(plan.device_id)
        return OperationRef(operation_id=plan.plan_id, status=OperationStatus.ACCEPTED)

    def lease_plan(self, connector_id: str, lease_seconds: int = 60):
        health = self.repository.get_health(connector_id)
        if health is None or health.reported_at <= self.clock() - timedelta(minutes=2):
            raise ConnectorError("connector_offline")
        if not health.user_session_present or not health.session_host_ready:
            raise ConnectorError("interactive_session_missing")
        if not health.system_awake:
            raise ConnectorError("connector_offline")
        lease = self.repository.lease_plan(connector_id, lease_seconds)
        if lease is None:
            return None
        plan = ConnectorExecutionPlanV1.model_validate(lease["plan"])
        return {**lease, **sign_connector_plan_lease(plan)}

    async def complete_plan(
        self, connector_id: str, plan_id: str, lease_id: str,
        outcome: ConnectorPlanOutcomeV1,
    ) -> None:
        if outcome.plan_id != plan_id:
            raise ConnectorError("plan_identity_mismatch")
        try:
            plan = self.repository.get_plan(
                plan_id, connector_id=connector_id, lease_id=lease_id,
            )
        except ConnectorRepositoryError as exc:
            raise ConnectorError(str(exc)) from exc
        expected = [step.step_id for step in plan.steps]
        actual = [step.step_id for step in outcome.steps]
        if len(actual) != len(set(actual)) or actual != expected[:len(actual)]:
            raise ConnectorError("plan_outcome_invalid")
        if outcome.status == "completed" and (
            actual != expected or any(step.status != "completed" for step in outcome.steps)
        ):
            raise ConnectorError("plan_outcome_invalid")
        if outcome.status in {"failed", "outcome_unknown", "cancelled"}:
            reconciliation_unknown = outcome.status == "outcome_unknown" and not outcome.steps
            if not reconciliation_unknown and (
                not outcome.steps or outcome.steps[-1].status != outcome.status
            ):
                raise ConnectorError("plan_outcome_invalid")
            if any(step.status != "completed" for step in outcome.steps[:-1]):
                raise ConnectorError("plan_outcome_invalid")
        if plan.plan_id.startswith("vismockup-command-") and {
            step.operation_id for step in plan.steps
        } <= DIRECT_VISMOCKUP_OPERATION_IDS:
            try:
                self.repository.complete_plan(connector_id, plan_id, lease_id, outcome)
            except ConnectorRepositoryError as exc:
                raise ConnectorError(str(exc)) from exc
            return
        target = (
            self.outcome_port.target(plan)
            if self.outcome_port is not None and hasattr(self.outcome_port, "target")
            else GovernedSimulationRuntimeClient.connector_outcome_target(plan)[0]
        )
        try:
            self.repository.complete_with_projection_intent(
                connector_id, plan_id, lease_id, outcome, target,
            )
        except ConnectorRepositoryError as exc:
            raise ConnectorError(str(exc)) from exc


connector_control_plane = ConnectorControlPlane(
    SimulationConnectorRepository(), outcome_port=ConnectorOutcomePortProxy(),
    wake_notifier=connector_wake_broker,
    plan_signer=PlanSigner.configured_from_environment(),
)


def _direct_vismockup_plan(
    *, action: str, connector_id: str, payload: dict, context: CapabilityContext,
    now: datetime,
) -> ConnectorExecutionPlanV1:
    # execution-plan.v1 canonicalizes timestamps to whole UTC seconds in the
    # Windows runtime.  Match that wire contract before computing the hash.
    now = now.astimezone(UTC).replace(microsecond=0)
    capability_version_gid = str(getattr(context, "capability_version_gid", "") or "")
    definition_hash = str(getattr(context, "business_definition_hash", "") or "")
    if not context.team_gid or not capability_version_gid.startswith("cv2_") or not definition_hash.startswith("sha256:"):
        raise ConnectorError("capability_provenance_required")
    operation_id, contract_hash = DIRECT_VISMOCKUP_OPERATIONS[action]
    step_payload = {"allow_launch": action == "launch"} if action in {"attach", "launch"} else payload
    step = ConnectorStepV1(
        step_id="step-00001", operation_id=operation_id, contract_hash=contract_hash,
        depends_on=(), payload=step_payload, payload_hash=canonical_hash(step_payload),
        timeout_seconds=120,
    )
    raw = {
        "protocol": "ai00.connector.execution-plan.v1",
        "plan_id": "vismockup-command-" + secrets.token_hex(16),
        "tenant_id": context.team_gid, "user_id": context.user_gid,
        "device_id": connector_id, "capability_version_gid": capability_version_gid,
        "business_definition_hash": definition_hash,
        "adapter_id": "ai00.vismockup", "adapter_major": 1,
        "target_product": ConnectorTargetProductV1(
            product_id="siemens.vismockup", minimum_version="14.0.0",
            maximum_version_exclusive="15.0.0",
        ),
        "steps": (step,), "issued_at": now, "expires_at": now + timedelta(minutes=15),
    }
    draft = ConnectorExecutionPlanV1.model_construct(**raw, plan_hash="sha256:" + "0" * 64)
    return ConnectorExecutionPlanV1(**raw, plan_hash=draft.compute_hash())


def _direct_vismockup_plan_v2(
    *, action: str, connector_id: str, payload: dict, context: CapabilityContext,
    now: datetime, capability_id: str | None = None, readback: bool = False,
) -> dict:
    """Build the unsigned App-runtime plan; queue_v2 pins the live runtime then signs it."""
    now = now.astimezone(UTC).replace(microsecond=0)
    capability_version_gid = str(getattr(context, "capability_version_gid", "") or "")
    definition_hash = str(getattr(context, "business_definition_hash", "") or "")
    catalog_release = str(getattr(context, "catalog_release", "") or "")
    request_id = str(getattr(context, "request_id", "") or "")
    idempotency_key = str(getattr(context, "idempotency_key", "") or request_id)
    normalized_input_hash = str(getattr(context, "normalized_input_hash", "") or "")
    if (
        not context.team_gid or not capability_version_gid.startswith("cv2_")
        or not definition_hash.startswith("sha256:") or not catalog_release.startswith("rel_")
        or not idempotency_key or not normalized_input_hash.startswith("sha256:")
    ):
        raise ConnectorError("capability_provenance_required")
    operation_id, contract_hash = DIRECT_VISMOCKUP_OPERATIONS[action]
    step_payload = {"allow_launch": action == "launch"} if action in {"attach", "launch"} else payload
    classification = "read" if action in {"attach", "tree"} else "write"
    probe_id = None if classification == "read" else (
        "vismockup.application.probe@1" if action in {"launch", "close"}
        else "vismockup.document.snapshot@1"
    )
    digest = lambda value: "sha256:" + hashlib.sha256(canonicalize_v2(value)).hexdigest()
    plan_identity = hashlib.sha256(canonicalize_v2({
        "capability_id": capability_id or DIRECT_VISMOCKUP_CAPABILITIES[action],
        "tenant_id": context.team_gid,
        "actor_id": context.user_gid,
        "device_id": connector_id,
        "idempotency_key": idempotency_key,
        "normalized_input_hash": normalized_input_hash,
    })).hexdigest()
    steps = [{
        "step_id": "step-00001",
        "operation_id": operation_id,
        "contract_hash": contract_hash,
        "depends_on": [],
        "payload": step_payload,
        "payload_hash": digest(step_payload),
        "timeout_seconds": 600 if action == "tree" else 120,
        "side_effect_classification": classification,
        "post_condition_probe_id": probe_id,
    }]
    if readback:
        readback_payload = {"max_depth": 8, "force_refresh": True}
        readback_operation, readback_contract = DIRECT_VISMOCKUP_OPERATIONS["tree"]
        steps.append({
            "step_id": "step-00002",
            "operation_id": readback_operation,
            "contract_hash": readback_contract,
            "depends_on": ["step-00001"],
            "payload": readback_payload,
            "payload_hash": digest(readback_payload),
            "timeout_seconds": 600,
            "side_effect_classification": "read",
            "post_condition_probe_id": None,
        })
    return {
        "protocol": "ai00.connector.execution-plan.v2",
        "plan_id": "vismockup-command-" + plan_identity,
        "capability_id": capability_id or DIRECT_VISMOCKUP_CAPABILITIES[action],
        "major_version": 1,
        "capability_version_gid": capability_version_gid,
        "business_definition_hash": definition_hash,
        "catalog_release": catalog_release,
        "tenant_id": context.team_gid,
        "actor_id": context.user_gid,
        "device_id": connector_id,
        # queue_v2 replaces both values from the authenticated runtime row before signing.
        "runtime_generation": 1,
        "runtime_instance_id": "runtime-pending",
        "adapter_id": "ai00.vismockup",
        "adapter_major": 1,
        "target_product": {
            "product_id": "siemens.vismockup",
            "minimum_version": "14.0.0",
            "maximum_version_exclusive": "15.0.0",
        },
        "normalized_input_hash": normalized_input_hash,
        "confirmation_receipt_id": getattr(context, "confirmation_token", None),
        "idempotency_key": idempotency_key,
        "steps": steps,
        "issued_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(minutes=15)).isoformat().replace("+00:00", "Z"),
    }


def record_connector_heartbeat(
    connector_id: str, owner_user_id: str, health: ConnectorHealth,
) -> None:
    connector_control_plane.record_heartbeat(connector_id, owner_user_id, health)


def queue_connector_plan(plan: ConnectorExecutionPlanV1, context: CapabilityContext) -> OperationRef:
    return connector_control_plane.queue_plan(plan, context)


def lease_connector_plan(connector_id: str, lease_seconds: int = 60):
    return connector_control_plane.lease_plan(connector_id, lease_seconds)


async def complete_connector_plan(connector_id, plan_id, lease_id, outcome):
    await connector_control_plane.complete_plan(connector_id, plan_id, lease_id, outcome)


def get_leased_connector_plan(connector_id, plan_id, lease_id):
    return connector_control_plane.repository.get_plan(
        plan_id, connector_id=connector_id, lease_id=lease_id,
    )


_VISMOCKUP_ATOMS = (
    ("simulation.vismockup.status.get", "Read VisMockup connection state.", CapabilityRisk.READ),
    ("simulation.vismockup.application.launch", "Launch or connect to VisMockup.", CapabilityRisk.WRITE),
    ("simulation.vismockup.model.open", "Open one authorized model artifact in VisMockup.", CapabilityRisk.WRITE),
    ("simulation.vismockup.model.insert", "Insert one authorized model artifact into the active VisMockup document.", CapabilityRisk.WRITE),
    ("simulation.vismockup.tree.get", "Read the active VisMockup product tree.", CapabilityRisk.READ),
    ("simulation.vismockup.selection.highlight", "Highlight VisMockup occurrences.", CapabilityRisk.WRITE),
    ("simulation.vismockup.visibility.change.apply", "Change VisMockup view visibility.", CapabilityRisk.WRITE),
    ("simulation.vismockup.node.visibility.change.apply", "Change one VisMockup node's visibility.", CapabilityRisk.WRITE),
    ("simulation.vismockup.node.selection.change.apply", "Change one VisMockup node's selection highlight.", CapabilityRisk.WRITE),
    ("simulation.vismockup.capture.create", "Create a VisMockup-internal screenshot artifact.", CapabilityRisk.WRITE),
)


def register_connector_runtime_capabilities(
    registry, control_plane: ConnectorControlPlane,
) -> None:
    from .provider import register

    def takeover(payload, context):
        from ..application.connector_runtime_sessions import RuntimeSessionService
        if context.source != 'web' or not context.user_gid or not context.team_gid:
            raise CapabilityBusinessError('runtime_owner_mismatch', 'Takeover requires an authenticated user and tenant.')
        try:
            data = RuntimeSessionService(control_plane.repository, clock=control_plane.clock).takeover(
                payload['device_id'], payload['expected_generation'], payload['runtime_instance_id'],
                actor_id=context.user_gid, tenant_id=context.team_gid, reason=payload['reason'])
        except ConnectorRepositoryError as exc:
            raise CapabilityBusinessError(str(exc), str(exc)) from exc
        return CapabilityOutput(data=data, evidence=(EvidenceRef(kind='simulation.connector.runtime.takeover',
            reference=data['audit_ref'], digest=canonical_hash(data)),))

    register(registry, CapabilitySpec(
        id='simulation.connector.runtime.takeover', owner='simulation', version=1,
        description='Reserve a new App runtime generation for a user-confirmed replacement instance.',
        use_when='The device owner confirms replacement of a stale App instance.',
        do_not_use_when='Work is unresolved or device identity does not match the authenticated owner.',
        risk=CapabilityRisk.WRITE, confirmation='user', permissions=('simulation.use',),
        input_schema={}, output_schema={}, tags=('simulation', 'connector', 'runtime'),
    ), takeover)

    def get_health(payload, context):
        health = control_plane.get_health(payload["connector_id"], context)
        data = health.model_dump(mode="json")
        return CapabilityOutput(data=data, evidence=(EvidenceRef(
            kind="simulation.connector.health",
            reference=f"connector-health:{payload['connector_id']}",
            digest=canonical_hash(data),
        ),))

    def queue_plan(payload, context):
        plan = ConnectorExecutionPlanV1.model_validate(payload["plan"])
        runtime = control_plane.repository.bound_runtime_for_user(context.user_gid, context.team_gid)
        try:
            if runtime and runtime.get("runtime_type") == "electron":
                from ..application.connector_workflow_v2 import workflow_plan_v2_draft
                draft = workflow_plan_v2_draft(
                    plan, catalog_release=str(getattr(context, "catalog_release", "") or ""),
                    confirmation_receipt_id=getattr(context, "confirmation_token", None),
                    now=control_plane.clock(),
                )
                operation = control_plane.queue_v2(draft, context, runtime_row=runtime)
            else:
                operation = control_plane.queue_plan(plan, context)
        except (ConnectorError, ValueError) as exc:
            raise CapabilityBusinessError(str(exc), str(exc)) from exc
        return CapabilityOutput(data=operation.model_dump(mode="json"), evidence=(EvidenceRef(
            kind="simulation.connector.plan",
            reference=f"connector-plan:{plan.plan_id}",
            digest=plan.plan_hash,
        ),))

    def request_direct(action):
        def handler(payload, context):
            runtime = control_plane.repository.bound_runtime_for_user(
                context.user_gid, context.team_gid,
            )
            binding = None
            if runtime:
                connector_id = runtime["device_id"]
            else:
                binding = control_plane.repository.binding_for_user(
                    context.user_gid, context.team_gid,
                )
                if not binding or not binding.get("connector_id"):
                    raise CapabilityBusinessError(
                        "connector_binding_not_found", "connector_binding_not_found",
                    )
                connector_id = binding["connector_id"]
            plan_payload = (
                {"artifact_ref": payload["artifact_ref"]} if action in {"open", "insert"}
                else {"action": payload["action"]} if action == "visibility"
                else {"node_key": payload["node_key"], "action": payload["action"]}
                if action in {"node_visibility", "node_selection"}
                else {
                    "max_depth": payload["max_depth"],
                    "force_refresh": bool(payload.get("force_refresh", False)),
                } if action == "tree"
                else {}
            )
            try:
                if runtime and runtime.get("runtime_type") == "electron":
                    plan = _direct_vismockup_plan_v2(
                        action=action, connector_id=connector_id, payload=plan_payload,
                        context=context, now=control_plane.clock(),
                    )
                    operation = control_plane.queue_v2(plan, context, runtime_row=runtime)
                    evidence_digest = canonical_hash(plan)
                else:
                    plan = _direct_vismockup_plan(
                        action=action, connector_id=connector_id, payload=plan_payload,
                        context=context, now=control_plane.clock(),
                    )
                    operation = control_plane.queue_plan(plan, context)
                    evidence_digest = plan.plan_hash
            except ConnectorError as exc:
                code = str(exc)
                raise CapabilityBusinessError(code, code) from exc
            return CapabilityOutput(data=operation.model_dump(mode="json"), evidence=(EvidenceRef(
                kind="simulation.vismockup.command",
                reference=f"connector-plan:{operation.operation_id}", digest=evidence_digest,
            ),))
        return handler

    def open_runtime_package(payload, context):
        runtime = control_plane.repository.bound_runtime_for_user(context.user_gid, context.team_gid)
        if not runtime or runtime.get("runtime_type") != "electron":
            raise ConnectorError("runtime_v2_required")
        from .plmxml_environments import PlmxmlEnvironmentProvider
        prepared = PlmxmlEnvironmentProvider().prepare_runtime_package(
            payload, context, connector_device_id=runtime["device_id"],
        ).data
        plan = _direct_vismockup_plan_v2(
            action="open", connector_id=runtime["device_id"], payload=prepared["open_payload"],
            context=context, now=control_plane.clock(),
            capability_id="simulation.environment.runtime_package.open.request",
            readback=True,
        )
        PlmxmlEnvironmentProvider().repository.save_runtime_package_projection(
            workspace_gid=payload["workspace_gid"], version_gid=payload["version_gid"],
            connector_plan_id=plan["plan_id"], manifest_hash=prepared["manifest_hash"],
            report={"manifest": prepared["manifest"], "semantic_verification": "pending"},
            tenant_gid=str(context.team_gid or ""), actor_gid=str(context.user_gid or ""),
            runtime_package_artifact_ref=prepared["top_level_artifact_ref"],
            connector_device_id=runtime["device_id"],
        )
        operation = control_plane.queue_v2(plan, context, runtime_row=runtime)
        return CapabilityOutput(data=operation.model_dump(mode="json"), evidence=(EvidenceRef(
            kind="simulation.environment.runtime_package",
            reference=f"simulation://workspace/{payload['workspace_gid']}/version/{payload['version_gid']}",
            digest=prepared["manifest_hash"],
        ),))

    def get_direct(payload, context):
        value = control_plane.repository.get_plan_result(
            payload["operation_id"], context.user_gid, context.team_gid,
        )
        if value is None:
            raise ConnectorError("connector_command_not_found")
        return CapabilityOutput(data=value, evidence=(EvidenceRef(
            kind="simulation.vismockup.command",
            reference=f"connector-plan:{payload['operation_id']}",
            digest=canonical_hash(value),
        ),))

    def local_atom_only(_payload, _context):
        raise CapabilityBusinessError(
            "provider_unavailable",
            "Direct VisMockup atoms execute only inside a signed Connector plan.",
        )

    register(registry, CapabilitySpec(
        id="simulation.connector.health.get", owner="simulation", version=1,
        description="Read the latest authenticated AI00 Connector health advertisement.",
        use_when="A Simulation workflow must preflight its bound Connector.",
        do_not_use_when="The caller needs to execute VisMockup work.",
        risk=CapabilityRisk.READ, confirmation="none", permissions=("agent.run",),
        input_schema={}, output_schema={}, tags=("simulation", "connector", "health"),
    ), get_health)
    register(registry, CapabilitySpec(
        id="simulation.connector.health.get", owner="simulation", version=2,
        description="Read the bound Simulation workstation runtime and adapter health.",
        use_when="A Simulation workflow preflights a bound desktop runtime.",
        do_not_use_when="The caller needs to execute VisMockup work.",
        risk=CapabilityRisk.READ, confirmation="none", permissions=("simulation.use",),
        input_schema={}, output_schema={}, tags=("simulation", "connector", "health"),
    ), get_health)
    register(registry, CapabilitySpec(
        id="simulation.connector.plan.queue", owner="simulation", version=1,
        description="Queue one immutable compatible execution plan for the bound AI00 Connector.",
        use_when="A Simulation workflow has an exact version-pinned local plan.",
        do_not_use_when="Connector compatibility or session preflight has not passed.",
        risk=CapabilityRisk.WRITE, confirmation="user", permissions=("agent.run",),
        input_schema={}, output_schema={}, tags=("simulation", "connector", "plan"),
    ), queue_plan)
    register(registry, CapabilitySpec(
        id="simulation.connector.plan.queue", owner="simulation", version=2,
        description="Queue one immutable compatible execution plan for the bound AI00 Connector as a Simulation user.",
        use_when="A Simulation workflow has an exact version-pinned local plan.",
        do_not_use_when="Connector compatibility or session preflight has not passed.",
        risk=CapabilityRisk.WRITE, confirmation="user", permissions=("simulation.use",),
        input_schema={}, output_schema={}, tags=("simulation", "connector", "plan"),
    ), queue_plan)
    register(registry, CapabilitySpec(
        id="simulation.connector.plan.queue", owner="simulation", version=3,
        description="Queue one confirmed materialization or capture plan for a Simulation workstation.",
        use_when="A Simulation workflow has prepared an exact workstation plan with its own user confirmation.",
        do_not_use_when="The plan, runtime session, or confirmation is not current.",
        risk=CapabilityRisk.WRITE, confirmation="user", permissions=("simulation.use",),
        input_schema={}, output_schema={}, tags=("simulation", "connector", "plan"),
    ), queue_plan)
    for capability_id, action, description in (
        ("simulation.vismockup.application.attach.request", "attach", "Queue a signed attach-only probe for an already-running VisMockup application."),
        ("simulation.vismockup.application.launch.request", "launch", "Queue a signed request to launch or attach to VisMockup."),
        ("simulation.vismockup.model.open.request", "open", "Queue a signed request to open one governed model artifact."),
        ("simulation.vismockup.model.insert.request", "insert", "Queue a signed request to insert one governed model artifact into the active document."),
        ("simulation.vismockup.model.close.request", "close", "Queue a signed request to close all models in the connected VisMockup application."),
        ("simulation.vismockup.visibility.change.request", "visibility", "Queue a signed request to show or hide all nodes in the active VisMockup document."),
        ("simulation.vismockup.node.visibility.change.request", "node_visibility", "Queue a signed request to change one tree node's visibility in the active VisMockup document."),
        ("simulation.vismockup.node.selection.change.request", "node_selection", "Queue a signed request to change one tree node's selection highlight in the active VisMockup document."),
        ("simulation.vismockup.tree.read.request", "tree", "Queue a signed bounded read of the active VisMockup product tree."),
    ):
        register(registry, CapabilitySpec(
            id=capability_id, owner="simulation", version=1, description=description,
            use_when="The signed-in user requests one direct action on the bound workstation Connector.",
            do_not_use_when="No current user-scoped Connector binding exists.",
            risk=CapabilityRisk.WRITE,
            confirmation="none" if action in {"attach", "visibility", "node_visibility", "node_selection", "tree"} else "user",
            permissions=("simulation.use",),
            input_schema={}, output_schema={}, tags=("simulation", "connector", "vismockup", "workflow"),
        ), request_direct(action))
    register(registry, CapabilitySpec(
        id="simulation.environment.runtime_package.open.request", owner="simulation", version=1,
        description="Prepare and queue one frozen environment package, opening only its generated top-level PLMXML.",
        use_when="A user replays one exact frozen Simulation environment in the bound AI00 App runtime.",
        do_not_use_when="The environment is editable, not frozen, or the runtime is not the App v2 Connector.",
        risk=CapabilityRisk.WRITE, confirmation="user", permissions=("simulation.use",),
        input_schema={}, output_schema={}, tags=("simulation","connector","environment","workflow","experimental"),
    ), open_runtime_package)
    register(registry, CapabilitySpec(
        id="simulation.vismockup.command.get", owner="simulation", version=1,
        description="Read one caller-scoped direct VisMockup command outcome.",
        use_when="The caller needs authoritative progress for a queued direct VisMockup command.",
        do_not_use_when="The command belongs to another user or tenant.",
        risk=CapabilityRisk.READ, confirmation="none", permissions=("simulation.use",),
        input_schema={}, output_schema={}, tags=("simulation", "connector", "vismockup", "workflow"),
    ), get_direct)
    for capability_id, description, risk in _VISMOCKUP_ATOMS:
        register(registry, CapabilitySpec(
            id=capability_id, owner="simulation", version=1,
            description=description,
            use_when="A signed Simulation Connector plan invokes this exact VisMockup atom.",
            do_not_use_when="The caller is outside the trusted local Connector runtime.",
            risk=risk, confirmation="none", permissions=("agent.run",),
            input_schema={}, output_schema={}, execution="local",
            tags=("simulation", "connector", "vismockup", "atomic"),
        ), local_atom_only)


__all__ = [
    "AdapterAdvertisement", "AdapterOperation", "ConnectorControlPlane",
    "ConnectorError", "ConnectorHealth", "SimulationConnectorRepository",
    "complete_connector_plan", "connector_control_plane",
    "connector_plan_signing_material", "get_leased_connector_plan",
    "lease_connector_plan", "queue_connector_plan", "record_connector_heartbeat",
    "register_connector_runtime_capabilities", "require_compatible",
    "sign_connector_plan_lease",
]

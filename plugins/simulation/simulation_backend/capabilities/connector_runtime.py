"""Simulation-owned AI00 Connector control plane and VisMockup atoms."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import hmac
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
from plugins.simulation.simulation_backend.application.connector_wakeup import connector_wake_broker
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


DIRECT_VISMOCKUP_OPERATIONS = {
    "attach": ("vismockup.application.probe@1", "sha256:197cfad8bc3453030fdc288ea78c3abc21699274dd48d4482444af4f62380a37"),
    "launch": ("vismockup.application.probe@1", "sha256:197cfad8bc3453030fdc288ea78c3abc21699274dd48d4482444af4f62380a37"),
    "open": ("vismockup.model.open@1", "sha256:aabd43bb066794c250f7eeed41def7c147a4da7263e813f192efa59a0cb40e34"),
    "close": ("vismockup.model.close@1", "sha256:a1a27969ab8638c9868b384ccb546aed1ece56219ded7c7ec3bb3d6b19861771"),
    "visibility": ("vismockup.visibility.change@1", "sha256:6ecb8dd2239a2ca881bfc8d40463778f2b80f15f66f1be50a3ceb91a90bff201"),
    "tree": ("vismockup.tree.read@1", "sha256:25ac87b341ef76d657c627b45bc0c4de129f55b92e01401dd6f2cd8649dd2f16"),
}
DIRECT_VISMOCKUP_OPERATION_IDS = frozenset(value[0] for value in DIRECT_VISMOCKUP_OPERATIONS.values())


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
        wake_notifier=None,
    ):
        self.repository = repository
        self.outcome_port = outcome_port
        self.clock = clock
        self.wake_notifier = wake_notifier

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
    ("simulation.vismockup.tree.get", "Read the active VisMockup product tree.", CapabilityRisk.READ),
    ("simulation.vismockup.selection.highlight", "Highlight VisMockup occurrences.", CapabilityRisk.WRITE),
    ("simulation.vismockup.visibility.change.apply", "Change VisMockup view visibility.", CapabilityRisk.WRITE),
    ("simulation.vismockup.capture.create", "Create a VisMockup-internal screenshot artifact.", CapabilityRisk.WRITE),
)


def register_connector_runtime_capabilities(
    registry, control_plane: ConnectorControlPlane,
) -> None:
    from .provider import register

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
        operation = control_plane.queue_plan(plan, context)
        return CapabilityOutput(data=operation.model_dump(mode="json"), evidence=(EvidenceRef(
            kind="simulation.connector.plan",
            reference=f"connector-plan:{plan.plan_id}",
            digest=plan.plan_hash,
        ),))

    def request_direct(action):
        def handler(payload, context):
            binding = control_plane.repository.binding_for_user(context.user_gid, context.team_gid)
            if not binding or not binding.get("connector_id"):
                raise ConnectorError("connector_binding_not_found")
            plan_payload = (
                {"artifact_ref": payload["artifact_ref"]} if action == "open"
                else {"action": payload["action"]} if action == "visibility"
                else {"max_depth": payload["max_depth"]} if action == "tree"
                else {}
            )
            plan = _direct_vismockup_plan(
                action=action, connector_id=binding["connector_id"], payload=plan_payload,
                context=context, now=control_plane.clock(),
            )
            operation = control_plane.queue_plan(plan, context)
            return CapabilityOutput(data=operation.model_dump(mode="json"), evidence=(EvidenceRef(
                kind="simulation.vismockup.command",
                reference=f"connector-plan:{plan.plan_id}", digest=plan.plan_hash,
            ),))
        return handler

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
    for capability_id, action, description in (
        ("simulation.vismockup.application.attach.request", "attach", "Queue a signed attach-only probe for an already-running VisMockup application."),
        ("simulation.vismockup.application.launch.request", "launch", "Queue a signed request to launch or attach to VisMockup."),
        ("simulation.vismockup.model.open.request", "open", "Queue a signed request to open one governed model artifact."),
        ("simulation.vismockup.model.close.request", "close", "Queue a signed request to close all models in the connected VisMockup application."),
        ("simulation.vismockup.visibility.change.request", "visibility", "Queue a signed request to show or hide all nodes in the active VisMockup document."),
        ("simulation.vismockup.tree.read.request", "tree", "Queue a signed bounded read of the active VisMockup product tree."),
    ):
        register(registry, CapabilitySpec(
            id=capability_id, owner="simulation", version=1, description=description,
            use_when="The signed-in user requests one direct action on the bound workstation Connector.",
            do_not_use_when="No current user-scoped Connector binding exists.",
            risk=CapabilityRisk.WRITE,
            confirmation="none" if action in {"attach", "visibility", "tree"} else "user",
            permissions=("simulation.use",),
            input_schema={}, output_schema={}, tags=("simulation", "connector", "vismockup", "workflow"),
        ), request_direct(action))
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

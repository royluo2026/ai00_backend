"""Simulation-owned AI00 Connector control plane and VisMockup atoms."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import os

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
    canonical_hash,
)
from backend.domain_ports.local_integration import canonical_json_bytes
from backend.domain_ports.simulation_runtime import ConnectorOutcomePortProxy

from ..data.connector_repository import (
    ConnectorRepositoryError,
    SimulationConnectorRepository,
)
from .connector_contracts import AdapterAdvertisement, AdapterOperation, ConnectorHealth


class ConnectorError(RuntimeError):
    pass


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
    def __init__(self, repository, *, outcome_port=None, clock=lambda: datetime.now(UTC)):
        self.repository = repository
        self.outcome_port = outcome_port
        self.clock = clock

    def record_heartbeat(
        self, connector_id: str, expected_user_id: str, health: ConnectorHealth,
    ) -> None:
        if health.bound_user_id != expected_user_id:
            raise ConnectorError("bound_user_mismatch")
        current = self.repository.get_health(connector_id)
        if (
            current is not None
            and current.reported_at > self.clock() - timedelta(minutes=2)
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
        try:
            self.repository.complete_plan(connector_id, plan_id, lease_id, outcome)
        except ConnectorRepositoryError as exc:
            raise ConnectorError(str(exc)) from exc
        if self.outcome_port is not None:
            target = (
                self.outcome_port.target(plan)
                if hasattr(self.outcome_port, "target")
                else "simulation.connector_outcome.apply"
            )
            attempt = 1
            if hasattr(self.repository, "begin_projection"):
                attempt = self.repository.begin_projection(
                    plan_id, canonical_hash(outcome.model_dump(mode="json")), target,
                )
                if attempt is None:
                    return
            try:
                await self.outcome_port.apply(plan, outcome, attempt=attempt)
            except Exception as exc:
                if hasattr(self.repository, "fail_projection"):
                    self.repository.fail_projection(
                        plan_id, attempt,
                        retryable=bool(getattr(exc, "retryable", True)),
                        error_code=str(exc)[:128],
                    )
                raise
            if hasattr(self.repository, "complete_projection"):
                self.repository.complete_projection(plan_id, attempt)


connector_control_plane = ConnectorControlPlane(
    SimulationConnectorRepository(), outcome_port=ConnectorOutcomePortProxy(),
)


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

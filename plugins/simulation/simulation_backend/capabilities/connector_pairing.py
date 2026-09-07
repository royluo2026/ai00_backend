"""Simulation Capability provider for browser-assisted Connector pairing."""
from __future__ import annotations

from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError,
    CapabilityOutput,
    CapabilityRisk,
    CapabilitySpec,
    EvidenceRef,
)
from backend.contracts.connector_execution_plan_v1 import canonical_hash

from ..data.connector_repository import SqlPairingRepository
from ..data.connector_app_pairing_repository import SqlAppPairingRepository
from ..domain.connector_pairing import PairingError, PairingRequest, PairingService
from .connector_runtime import connector_plan_signing_material


def _plan_credentials(connector_id: str) -> dict:
    key_id, secret = connector_plan_signing_material(connector_id)
    return {"plan_signing_key_id": key_id, "plan_signing_secret": secret}


default_service = PairingService(
    SqlPairingRepository(), extra_credential_factory=_plan_credentials,
)


app_pairing_service = PairingService(SqlAppPairingRepository())


def _translate(call):
    try:
        return call()
    except PairingError as exc:
        raise CapabilityBusinessError(str(exc), str(exc)) from exc


class ConnectorPairingProvider:
    def __init__(self, service=default_service):
        self.service = service

    def request(self, payload, _context):
        result = _translate(lambda: self.service.request(PairingRequest.model_validate(payload)))
        data = result.model_dump(mode="json")
        return CapabilityOutput(data=data, evidence=(EvidenceRef(
            kind="simulation.connector.pairing",
            reference=f"connector-pairing:{result.pairing_id}", digest=canonical_hash(data),
        ),))

    def summary(self, payload, context):
        result = _translate(lambda: (
            self.service.get_summary_by_pairing_id(
                payload["pairing_id"], context.user_gid, self._team_scope(context),
            ) if payload.get("pairing_id") else self.service.get_summary(
                payload["user_code"], context.user_gid, self._team_scope(context),
            )
        ))
        data = result.model_dump(mode="json")
        return CapabilityOutput(data=data, evidence=(EvidenceRef(
            kind="simulation.connector.pairing_summary",
            reference=f"connector-pairing:{result.pairing_id}",
            digest=canonical_hash(data),
        ),))

    def bootstrap_create(self, _payload, context):
        self._require_web_user(context)
        result = _translate(lambda: self.service.bootstrap_create(
            context.user_gid, self._team_scope(context),
        ))
        data = result.model_dump(mode="json")
        return CapabilityOutput(data=data, evidence=(EvidenceRef(
            kind="simulation.connector.pairing_bootstrap",
            reference=f"connector-bootstrap:{result.bootstrap_id}", digest=canonical_hash({
                key: value for key, value in data.items() if key != "bootstrap_token"
            }),
        ),))

    def bootstrap_get(self, payload, context):
        self._require_web_user(context)
        result = _translate(lambda: self.service.bootstrap_get(
            payload["bootstrap_id"], context.user_gid, self._team_scope(context),
        ))
        data = result.model_dump(mode="json")
        return CapabilityOutput(data=data, evidence=(EvidenceRef(
            kind="simulation.connector.pairing_bootstrap",
            reference=f"connector-bootstrap:{result.bootstrap_id}", digest=canonical_hash(data),
        ),))

    def approve(self, payload, context):
        self._require_web_user(context)
        result = _translate(lambda: (
            self.service.approve_by_pairing_id(
                payload["pairing_id"], context.user_gid, self._team_scope(context),
                expected_version=payload["expected_version"],
            ) if payload.get("pairing_id") else self.service.approve(
                payload["user_code"], context.user_gid, self._team_scope(context),
                expected_version=payload["expected_version"],
            )
        ))
        data = result.model_dump(mode="json")
        return CapabilityOutput(data=data, evidence=(EvidenceRef(
            kind="simulation.connector.pairing_approval",
            reference=f"connector-pairing:{result.pairing_id}", digest=canonical_hash(data),
        ),))

    def complete(self, payload, _context):
        result = _translate(lambda: self.service.complete(
            payload["pairing_id"], payload["installation_id"], payload["verifier"],
        ))
        return CapabilityOutput(data=result.model_dump(mode="json"), evidence=(EvidenceRef(
            kind="simulation.connector.binding",
            reference=f"simulation-connector:{result.connector_id}",
            digest=result.envelope_hash,
        ),))

    def binding(self, _payload, context):
        row = self.service.repository.binding_for_user(context.user_gid, self._team_scope(context))
        data = {
            "connector_id": row["connector_id"] if row else None,
            "installation_id": row["installation_id"] if row else None,
        }
        return CapabilityOutput(data=data, evidence=(EvidenceRef(
            kind="simulation.connector.binding_summary",
            reference=f"simulation-connector-binding:{context.user_gid}",
            digest=canonical_hash(data),
        ),))

    def activate(self, payload, _context):
        result = _translate(lambda: self.service.activate(
            payload["pairing_id"], payload["connector_id"], payload["activation_proof"],
        ))
        data = result.model_dump(mode="json")
        return CapabilityOutput(data=data, evidence=(EvidenceRef(
            kind="simulation.connector.pairing_activation",
            reference=f"connector-pairing:{result.pairing_id}", digest=canonical_hash(data),
        ),))

    def cancel(self, payload, context):
        self._require_web_user(context)
        result = _translate(lambda: self.service.bootstrap_cancel(
            payload["bootstrap_id"], context.user_gid, self._team_scope(context),
            expected_version=payload["expected_version"],
        ))
        data = result.model_dump(mode="json")
        return CapabilityOutput(data=data, evidence=(EvidenceRef(
            kind="simulation.connector.pairing_bootstrap",
            reference=f"connector-bootstrap:{result.bootstrap_id}", digest=canonical_hash(data),
        ),))

    @staticmethod
    def _require_web_user(context):
        if context.source != "web" or not context.user_gid:
            raise CapabilityBusinessError(
                "feishu_login_required",
                "Pairing approval requires the user's Feishu-authenticated AI00 Web session.",
            )

    @staticmethod
    def _team_scope(context):
        return context.team_gid or f"personal:{context.user_gid}"


def specs(provider: ConnectorPairingProvider | None = None):
    selected = provider or ConnectorPairingProvider()
    common = {
        "owner": "simulation", "version": 1, "permissions": ("simulation.use",),
        "input_schema": {}, "output_schema": {},
        "tags": ("simulation", "connector", "pairing"),
    }
    def app_action(action):
        def handler(payload, context):
            selected._require_web_user(context)
            method = getattr(app_pairing_service, action + '_v2')
            kwargs = {} if action == 'summary' else {'expected_version': payload['expected_version']}
            data = _translate(lambda: method(payload['pairing_id'], context.user_gid, selected._team_scope(context), **kwargs))
            # Normalize timestamps for the closed Capability wire schema.
            data = {key: value.isoformat() if hasattr(value, 'isoformat') else value for key, value in data.items()}
            return CapabilityOutput(data=data, evidence=(EvidenceRef(kind='simulation.connector.app_pairing',
                reference='connector-pairing:' + payload['pairing_id'], digest=canonical_hash(data)),))
        return handler

    app_specs = tuple((CapabilitySpec(
        id='simulation.connector.pairing.' + suffix, owner='simulation', version=2,
        description=description, use_when='The signed-in user manages App possession pairing.',
        do_not_use_when='The caller is a device transport or belongs to another tenant.',
        risk=CapabilityRisk.READ if action == 'summary' else CapabilityRisk.WRITE,
        confirmation='user' if action == 'bind' else 'none', permissions=('simulation.use',),
        input_schema={}, output_schema={}, tags=('simulation', 'connector', 'pairing'),
    ), app_action(action)) for suffix, action, description in (
        ('approve', 'bind', 'Bind one App pairing to the authenticated user and tenant.'),
        ('summary.get', 'summary', 'Read an owned App pairing state.'),
        ('cancel', 'cancel', 'Cancel an owned unfinished App pairing.'),
    ))
    return app_specs + (
        (CapabilitySpec(
            id="simulation.connector.pairing.bootstrap.create",
            description="Create a short-lived one-time Connector bootstrap ticket for the signed-in user.",
            use_when="The Simulation page is starting a local Connector handoff.",
            do_not_use_when="A Connector is submitting device proof.",
            risk=CapabilityRisk.WRITE, confirmation="none", **common,
        ), selected.bootstrap_create),
        (CapabilitySpec(
            id="simulation.connector.pairing.bootstrap.get",
            description="Read the signed-in user's safe bootstrap ticket state.",
            use_when="The Simulation page is showing Connector handoff progress.",
            do_not_use_when="Secret bootstrap material is required.",
            risk=CapabilityRisk.READ, confirmation="none", **common,
        ), selected.bootstrap_get),
        (CapabilitySpec(
            id="simulation.connector.pairing.request",
            description="Request a five-minute Connector browser pairing code.",
            use_when="An unpaired Connector installation needs an AI00 user binding.",
            do_not_use_when="The installation already has a valid binding.",
            risk=CapabilityRisk.WRITE, confirmation="none", **common,
        ), selected.request),
        (CapabilitySpec(
            id="simulation.connector.pairing.summary.get",
            description="Read safe display fields for one Connector pairing code.",
            use_when="The signed-in user is reviewing a pairing request.",
            do_not_use_when="The Connector is requesting credential material.",
            risk=CapabilityRisk.READ, confirmation="none", **common,
        ), selected.summary),
        (CapabilitySpec(
            id="simulation.connector.pairing.approve",
            description="Bind one pending Connector to the current AI00 user.",
            use_when="A Feishu-authenticated user confirms the displayed Connector.",
            do_not_use_when="The user or resource version does not match.",
            risk=CapabilityRisk.WRITE, confirmation="user", **common,
        ), selected.approve),
        (CapabilitySpec(
            id="simulation.connector.pairing.complete",
            description="Exchange the Connector proof for one encrypted credential envelope.",
            use_when="An approved installation proves the original verifier.",
            do_not_use_when="Only the public user code is available.",
            risk=CapabilityRisk.WRITE, confirmation="none", **common,
        ), selected.complete),
        (CapabilitySpec(
            id="simulation.connector.pairing.activate",
            description="A credentialed Connector acknowledges durable credential activation.",
            use_when="The Connector has persisted and verified its issued credential.",
            do_not_use_when="Only a bootstrap ticket or user session is available.",
            risk=CapabilityRisk.WRITE, confirmation="none", **common,
        ), selected.activate),
        (CapabilitySpec(
            id="simulation.connector.pairing.cancel",
            description="Cancel the signed-in user's unfinished Connector bootstrap ticket.",
            use_when="The user cancels a pending Connector handoff.",
            do_not_use_when="The Connector binding is already active.",
            risk=CapabilityRisk.WRITE, confirmation="none", **common,
        ), selected.cancel),
        (CapabilitySpec(
            id="simulation.connector.binding.get",
            description="Read the current user's single Connector binding.",
            use_when="AI00 Web needs to display or select the user's Connector.",
            do_not_use_when="A new Connector must be paired.",
            risk=CapabilityRisk.READ, confirmation="none", **common,
        ), selected.binding),
    )


__all__ = ["ConnectorPairingProvider", "default_service", "specs"]

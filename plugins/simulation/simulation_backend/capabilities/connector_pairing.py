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
from ..domain.connector_pairing import PairingError, PairingRequest, PairingService
from .connector_runtime import connector_plan_signing_material


def _plan_credentials(connector_id: str) -> dict:
    key_id, secret = connector_plan_signing_material(connector_id)
    return {"plan_signing_key_id": key_id, "plan_signing_secret": secret}


default_service = PairingService(
    SqlPairingRepository(), extra_credential_factory=_plan_credentials,
)


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
        result = _translate(lambda: self.service.get_summary(payload["user_code"], context.user_gid))
        return CapabilityOutput(data=result.model_dump(mode="json"))

    def approve(self, payload, context):
        if context.source != "web" or not context.user_gid:
            raise CapabilityBusinessError(
                "feishu_login_required",
                "Pairing approval requires the user's Feishu-authenticated AI00 Web session.",
            )
        result = _translate(lambda: self.service.approve(
            payload["user_code"], context.user_gid, context.team_gid or "",
            expected_version=payload["expected_version"],
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
        row = self.service.repository.binding_for_user(context.user_gid)
        return CapabilityOutput(data={
            "connector_id": row["connector_id"] if row else None,
            "installation_id": row["installation_id"] if row else None,
        })


def specs(provider: ConnectorPairingProvider | None = None):
    selected = provider or ConnectorPairingProvider()
    common = {
        "owner": "simulation", "version": 1, "permissions": ("agent.run",),
        "input_schema": {}, "output_schema": {},
        "tags": ("simulation", "connector", "pairing"),
    }
    return (
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
            id="simulation.connector.binding.get",
            description="Read the current user's single Connector binding.",
            use_when="AI00 Web needs to display or select the user's Connector.",
            do_not_use_when="A new Connector must be paired.",
            risk=CapabilityRisk.READ, confirmation="none", **common,
        ), selected.binding),
    )


__all__ = ["ConnectorPairingProvider", "default_service", "specs"]

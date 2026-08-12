from __future__ import annotations

from backend.capability_v2.provider_contracts import CapabilityBusinessError


class AgentApplication:
    def __init__(self, repository): self.repository = repository

    def invoke(self, capability_id: str, payload: dict, context):
        actor = getattr(context, "user_gid", None) or getattr(context, "actor_gid", None)
        tenant = getattr(context, "team_gid", None) or getattr(context, "tenant_gid", None)
        if not actor or not tenant:
            raise CapabilityBusinessError("permission_denied", "Agent access requires actor and tenant context")
        family = capability_id.split(".")[1]
        data = {**payload, "owner_gid": str(actor), "tenant_gid": str(tenant), "resource_type": family}
        if capability_id.endswith(".read"):
            return self.repository.read(data)
        if capability_id == "agent.interaction.request":
            return self.repository.request_interaction(data)
        return self.repository.apply(data)

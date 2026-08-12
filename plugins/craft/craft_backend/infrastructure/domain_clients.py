from __future__ import annotations

from backend.capability_v2.domain_client import DomainCapabilityClient, DomainInvocation


class CraftDomainClients:
    def __init__(self, gateway): self.client = DomainCapabilityClient(gateway)

    async def read_factory_resource(self, resource_ref, identity, correlation, deadline=None):
        return await self.client.invoke(
            DomainInvocation(capability_id="factory.resource.read", major_version=1, payload={"resource_ref": resource_ref}),
            identity=identity, correlation=correlation, deadline=deadline,
        )


__all__ = ["CraftDomainClients", "DomainCapabilityClient", "DomainInvocation"]

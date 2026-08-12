from __future__ import annotations

from backend.capability_v2.domain_client import DomainInvocation

from ..domain.bop import FactoryResourceUnavailable


class BopService:
    def __init__(self, domain_client, bindings): self.domain_client, self.bindings = domain_client, bindings

    async def bind_factory_resource(self, bop_ref, resource_ref, identity, correlation, deadline=None):
        try:
            result = await self.domain_client.invoke(
                DomainInvocation(capability_id="factory.resource.read", major_version=1, payload={"resource_ref": resource_ref}),
                identity=identity, correlation=correlation, deadline=deadline,
            )
        except TimeoutError as exc:
            raise FactoryResourceUnavailable("factory_resource_timeout") from exc
        if not result.ok:
            code = getattr(result.error, "code", "factory_resource_unavailable")
            public = "factory_resource_denied" if code in {"permission_denied", "authorization_denied"} else "factory_resource_unavailable"
            raise FactoryResourceUnavailable(public)
        data = result.data or {}
        version = data.get("version")
        if version is None:
            raise FactoryResourceUnavailable("factory resource version missing")
        self.bindings.bind_factory_resource(bop_ref, resource_ref, int(version))
        return {"bop_ref": bop_ref, "resource_ref": resource_ref, "provider_version": int(version)}


__all__ = ["BopService"]

"""Deterministic Agent tools generated only from one pinned Catalog release."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.capability_v2.domain_client import DomainCapabilityClient, DomainInvocation


def tool_name_for(capability_id: str, major_version: int) -> str:
    name = f"cap__{str(capability_id).replace('.', '__')}__v{int(major_version)}"
    if len(name) > 128:
        raise ValueError("generated Agent tool name exceeds 128 characters")
    return name


@dataclass(frozen=True)
class CatalogTool:
    name: str
    capability_id: str
    major_version: int
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    side_effect_level: str
    automation_level: str
    confirmation_policy: str
    resource_selectors: tuple[tuple[str, str, bool], ...]

    def resource_scopes(self, payload: dict[str, Any]) -> tuple[str, ...]:
        scopes = []
        for resource_type, path, _required in self.resource_selectors:
            current: Any = payload
            found = True
            for part in path.split("."):
                if not part or not isinstance(current, dict) or part not in current:
                    found = False
                    break
                current = current[part]
            if found and current not in (None, "") and not isinstance(current, (dict, list, tuple, set, bool)):
                scopes.append(f"{resource_type}:{current}")
        return tuple(scopes)


class CatalogToolRegistry:
    def __init__(self, release, *, client: DomainCapabilityClient | None = None):
        self.release = release
        self.client = client
        self._tools = {
            tool_name_for(item.id, item.major_version): CatalogTool(
                name=tool_name_for(item.id, item.major_version), capability_id=item.id,
                major_version=item.major_version, description=item.description,
                input_schema=dict(item.input_schema), output_schema=dict(item.agent_output_schema or item.output_schema),
                side_effect_level=str(item.side_effect_level.value), automation_level=str(item.automation_level.value),
                confirmation_policy=item.confirmation_policy,
                resource_selectors=tuple(
                    (selector.resource_type, selector.payload_path, selector.required)
                    for selector in item.resource_selectors
                ),
            )
            for item in release.descriptors if item.exposure.agent
        }

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def tools(self) -> tuple[CatalogTool, ...]:
        return tuple(self._tools[name] for name in self.names())

    def resolve(self, name: str) -> CatalogTool:
        tool = self._tools.get(name)
        if tool is None:
            raise ValueError("unknown Catalog-generated Agent tool")
        return tool

    async def execute(self, name: str, payload: dict, *, identity, correlation, idempotency_key: str | None = None):
        if self.client is None:
            raise RuntimeError("Agent DomainCapabilityClient is unavailable")
        tool = self.resolve(name)
        invocation = DomainInvocation(
            capability_id=tool.capability_id, major_version=tool.major_version,
            payload=dict(payload), idempotency_key=idempotency_key,
        )
        return await self.client.invoke(invocation, identity, correlation)


__all__ = ["CatalogTool", "CatalogToolRegistry", "tool_name_for"]

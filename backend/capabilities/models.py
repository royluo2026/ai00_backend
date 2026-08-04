"""Stable data contracts for the Capability Kernel."""

from __future__ import annotations

from enum import Enum
from typing import Any, Awaitable, Callable, Mapping

from pydantic import BaseModel, ConfigDict, Field


class CapabilityExecution(str, Enum):
    CLOUD = "cloud"
    LOCAL = "local"


class CapabilityRisk(str, Enum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


class CapabilitySpec(BaseModel):
    """Machine-readable capability metadata.

    ``id`` and ``version`` form the public identity.  Schemas are represented
    as JSON-Schema dictionaries now so the same object can later be exported
    to OpenAPI, Pi tools and MCP tools without another translation layer.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}$")
    version: int = Field(default=1, ge=1)
    description: str = ""
    execution: CapabilityExecution = CapabilityExecution.CLOUD
    risk: CapabilityRisk = CapabilityRisk.READ
    confirmation: str = Field(default="none", pattern=r"^(none|user|admin)$")
    idempotent: bool = True
    permissions: tuple[str, ...] = ()
    input_schema: Mapping[str, Any] = Field(default_factory=dict)
    output_schema: Mapping[str, Any] = Field(default_factory=dict)
    device_capability: str | None = None
    tags: tuple[str, ...] = ()


class CapabilityContext(BaseModel):
    """Execution context propagated across all capability consumers."""

    model_config = ConfigDict(extra="allow")

    user_gid: str
    source: str = "web"
    request_id: str | None = None
    team_gid: str | None = None
    confirmation_token: str | None = None


class CapabilityResult(BaseModel):
    """Normalized result envelope for REST, Agent and MCP adapters."""

    ok: bool = True
    capability_id: str
    version: int
    data: Any = None
    error: str | None = None
    audit: dict[str, Any] = Field(default_factory=dict)


CapabilityHandler = Callable[
    [dict[str, Any], CapabilityContext],
    Awaitable[Any] | Any,
]

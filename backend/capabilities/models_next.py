"""Next Capability Kernel contracts used by the v3 migration slice."""
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
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}$")
    version: int = Field(default=1, ge=1)
    owner: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")
    use_when: str = ""
    do_not_use_when: str = ""
    subject_concepts: tuple[str, ...] = ()
    effects: tuple[str, ...] = ()
    deprecated: bool = False
    replaced_by: str | None = None
    description: str = ""
    execution: CapabilityExecution = CapabilityExecution.CLOUD
    risk: CapabilityRisk = CapabilityRisk.READ
    confirmation: str = Field(default="none", pattern=r"^(none|user|admin)$")
    idempotent: bool = True
    plugin_callable: bool = False
    permissions: tuple[str, ...] = ()
    input_schema: Mapping[str, Any] = Field(default_factory=dict)
    output_schema: Mapping[str, Any] = Field(default_factory=dict)
    device_capability: str | None = None
    tags: tuple[str, ...] = ()

class CapabilityContext(BaseModel):
    model_config = ConfigDict(extra="allow")
    user_gid: str
    source: str = "web"
    request_id: str | None = None
    team_gid: str | None = None
    confirmation_token: str | None = None
    permissions: tuple[str, ...] = ()
    active_roles: tuple[str, ...] = ()

class EvidenceRef(BaseModel):
    """Small, transport-safe evidence pointer; large content stays in its owner store."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")
    reference: str = Field(min_length=1, max_length=2048)
    digest: str | None = Field(default=None, max_length=256)
    summary: str = Field(default="", max_length=2000)
    metadata: Mapping[str, Any] = Field(default_factory=dict)


class CapabilityError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,127}$")
    message: str
    retryable: bool = False
    details: Mapping[str, Any] = Field(default_factory=dict)


class CapabilityBusinessError(RuntimeError):
    """Stable domain failure raised by handlers without owning HTTP semantics."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = dict(details or {})


class CapabilityOutput(BaseModel):
    """Handler return type when a capability needs first-class evidence."""
    model_config = ConfigDict(extra="forbid")
    data: Any = None
    evidence: tuple[EvidenceRef, ...] = ()


class CapabilityResult(BaseModel):
    ok: bool = True
    capability_id: str
    version: int
    data: Any = None
    error: CapabilityError | None = None
    evidence: tuple[EvidenceRef, ...] = ()
    audit: dict[str, Any] = Field(default_factory=dict)

CapabilityHandler = Callable[[dict[str, Any], CapabilityContext], Awaitable[CapabilityOutput | Any] | CapabilityOutput | Any]

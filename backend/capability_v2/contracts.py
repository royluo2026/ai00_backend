"""Frozen, transport-safe contracts for the Capability V2 boundary."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator


CAPABILITY_ID_PATTERN = r"^[a-z][a-z0-9_.-]{2,127}$"
IDENTITY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}$"


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LifecycleStatus(str, Enum):
    EXPERIMENTAL = "experimental"
    STABLE = "stable"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class ConsumerType(str, Enum):
    WEB = "web"
    PLUGIN = "plugin"
    AGENT = "agent"
    API = "api"
    MCP = "mcp"
    WORKER = "worker"
    LOCAL_RUNTIME = "local_runtime"


class AutomationLevel(str, Enum):
    A0 = "A0"
    A1 = "A1"
    A2 = "A2"
    A3 = "A3"
    A4 = "A4"
    A5 = "A5"
    A6 = "A6"


class ExecutionMode(str, Enum):
    CLOUD_SYNC = "cloud_sync"
    CLOUD_ASYNC = "cloud_async"
    LOCAL = "local"


class SideEffectLevel(str, Enum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


class MemoryClass(str, Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class CollectionPolicy(str, Enum):
    BOUNDED = "bounded"
    PAGED = "paged"
    ARTIFACT = "artifact"


class OverloadPolicy(str, Enum):
    REJECT = "reject"
    DEGRADE = "degrade"
    ASYNC_ARTIFACT = "async_artifact"


class ExecutionBudget(FrozenModel):
    memory_class: MemoryClass = MemoryClass.SMALL
    max_input_bytes: int = Field(default=1024 * 1024, gt=0)
    max_output_bytes: int = Field(default=4 * 1024 * 1024, gt=0)
    collection_policy: CollectionPolicy = CollectionPolicy.BOUNDED
    max_page_size: int | None = Field(default=None, gt=0)
    max_parallel_per_consumer: int = Field(default=4, gt=0)
    max_parallel_per_tenant: int = Field(default=32, gt=0)
    overload_policy: OverloadPolicy = OverloadPolicy.REJECT

    @model_validator(mode="after")
    def page_size_matches_collection_policy(self) -> "ExecutionBudget":
        if self.collection_policy is CollectionPolicy.PAGED and self.max_page_size is None:
            raise ValueError("paged collection policy requires max_page_size")
        if self.collection_policy is not CollectionPolicy.PAGED and self.max_page_size is not None:
            raise ValueError("max_page_size is only valid for paged collection policy")
        return self


class CapabilityStatus(str, Enum):
    COMPLETED = "completed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    FAILED = "failed"
    OUTCOME_UNKNOWN = "outcome_unknown"


class OperationStatus(str, Enum):
    ACCEPTED = "accepted"
    CLAIMED = "claimed"
    PREPARING = "preparing"
    RUNNING = "running"
    POST_PROCESSING = "post_processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    OUTCOME_UNKNOWN = "outcome_unknown"


class ExposurePolicy(FrozenModel):
    web: bool = False
    plugin: bool = False
    agent: bool = False
    api: bool = False
    mcp: bool = False
    worker: bool = False
    local_runtime: bool = False

    def allows(self, consumer_type: ConsumerType) -> bool:
        return bool(getattr(self, consumer_type.value))


class ResourceSelector(FrozenModel):
    resource_type: str = Field(min_length=1, max_length=128)
    payload_path: str = Field(min_length=1, max_length=512)
    required: bool = True


class DomainErrorContract(FrozenModel):
    code: str = Field(pattern=CAPABILITY_ID_PATTERN)
    meaning: str = Field(min_length=1, max_length=2000)
    retryable: bool = False
    # V2.1 keeps caller-fixability explicit; it must not be inferred from retryable.
    is_caller_error: bool = False

    def as_error_schema_entry(self) -> dict[str, object]:
        return {
            "error_code": self.code,
            "message_template": self.meaning,
            "is_retryable": self.retryable,
            "is_caller_error": self.is_caller_error,
        }


class ActorIdentity(FrozenModel):
    user_id: str | None = Field(default=None, pattern=IDENTITY_PATTERN)
    service_id: str | None = Field(default=None, pattern=IDENTITY_PATTERN)
    authentication_method: str = Field(min_length=1, max_length=64)
    authenticated_at: datetime

    @model_validator(mode="after")
    def one_actor_kind(self) -> "ActorIdentity":
        if (self.user_id is None) == (self.service_id is None):
            raise ValueError("actor identity requires exactly one of user_id or service_id")
        if self.authenticated_at.tzinfo is None or self.authenticated_at.utcoffset() is None:
            raise ValueError("authenticated_at must be timezone-aware")
        return self


class TenantIdentity(FrozenModel):
    tenant_id: str = Field(pattern=IDENTITY_PATTERN)
    membership: str = Field(min_length=1, max_length=64)
    active_roles: tuple[str, ...] = ()


class ConsumerDescriptor(FrozenModel):
    type: ConsumerType
    consumer_id: str = Field(pattern=IDENTITY_PATTERN)
    consumer_version: str | None = Field(default=None, max_length=128)
    installation_id: str | None = Field(default=None, pattern=IDENTITY_PATTERN)
    mount_session_id: str | None = Field(default=None, pattern=IDENTITY_PATTERN)
    agent_run_id: str | None = Field(default=None, pattern=IDENTITY_PATTERN)


class DelegationContext(FrozenModel):
    delegation_id: str = Field(pattern=IDENTITY_PATTERN)
    delegated_by: str = Field(pattern=IDENTITY_PATTERN)
    capability_scopes: tuple[str, ...] = ()
    resource_scopes: tuple[str, ...] = ()
    data_scopes: tuple[str, ...] = ()
    catalog_release: str = Field(min_length=1, max_length=128)
    maximum_automation_level: AutomationLevel
    expires_at: datetime


class ConsumerIdentity(FrozenModel):
    actor: ActorIdentity
    tenant: TenantIdentity
    consumer: ConsumerDescriptor
    delegation: DelegationContext | None = None


class ArtifactRef(FrozenModel):
    artifact_id: str = Field(pattern=IDENTITY_PATTERN)
    media_type: str = Field(min_length=1, max_length=255)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(ge=0)
    version: int = Field(default=1, ge=1)


class OperationRef(FrozenModel):
    operation_id: str = Field(pattern=IDENTITY_PATTERN)
    status: OperationStatus
    version: int = Field(default=1, ge=1)


class EvidenceRefV2(FrozenModel):
    kind: str = Field(min_length=1, max_length=64)
    reference: str = Field(min_length=1, max_length=2048)
    digest: str | None = Field(default=None, max_length=256)
    summary: str = Field(default="", max_length=2000)


class CapabilityErrorV2(FrozenModel):
    code: str = Field(pattern=CAPABILITY_ID_PATTERN)
    message: str = Field(min_length=1, max_length=4000)
    retryable: bool = False
    details: Mapping[str, Any] = Field(default_factory=dict)


class CorrelationRef(FrozenModel):
    request_id: str = Field(pattern=IDENTITY_PATTERN)
    trace_id: str | None = Field(default=None, pattern=IDENTITY_PATTERN)


class CapabilityResultV2(FrozenModel):
    ok: bool
    status: CapabilityStatus
    capability_id: str = Field(pattern=CAPABILITY_ID_PATTERN)
    major_version: int = Field(ge=1)
    data: Any = None
    operation_ref: OperationRef | None = None
    artifact_refs: tuple[ArtifactRef, ...] = ()
    error: CapabilityErrorV2 | None = None
    evidence: tuple[EvidenceRefV2, ...] = ()
    warnings: tuple[str, ...] = ()
    correlation: CorrelationRef

    @model_validator(mode="after")
    def status_contract(self) -> "CapabilityResultV2":
        if self.status is CapabilityStatus.ACCEPTED and self.operation_ref is None:
            raise ValueError("accepted result requires operation_ref")
        if self.status is CapabilityStatus.ACCEPTED and self.data is not None:
            raise ValueError("accepted result cannot contain data")
        if self.status in {CapabilityStatus.COMPLETED, CapabilityStatus.ACCEPTED} and not self.ok:
            raise ValueError(f"{self.status.value} result must be ok")
        if self.status in {CapabilityStatus.COMPLETED, CapabilityStatus.ACCEPTED} and self.error is not None:
            raise ValueError(f"{self.status.value} result cannot contain error")
        if self.status in {CapabilityStatus.REJECTED, CapabilityStatus.FAILED} and self.error is None:
            raise ValueError("rejected or failed result requires error")
        if self.ok and self.status in {CapabilityStatus.REJECTED, CapabilityStatus.FAILED}:
            raise ValueError("failed result cannot be ok")
        if self.status is CapabilityStatus.OUTCOME_UNKNOWN:
            if self.ok:
                raise ValueError("outcome_unknown result cannot be ok")
            if self.operation_ref is None or self.error is None:
                raise ValueError("outcome_unknown result requires operation_ref and error")
        return self

    @classmethod
    def accepted(
        cls,
        capability_id: str,
        major_version: int,
        correlation_id: str,
        operation: OperationRef,
    ) -> "CapabilityResultV2":
        return cls(
            ok=True,
            status=CapabilityStatus.ACCEPTED,
            capability_id=capability_id,
            major_version=major_version,
            operation_ref=operation,
            correlation=CorrelationRef(request_id=correlation_id),
        )


class InvocationEnvelope(FrozenModel):
    capability_id: str = Field(pattern=CAPABILITY_ID_PATTERN)
    major_version: int = Field(ge=1)
    catalog_release: str = Field(min_length=1, max_length=128)
    payload: Mapping[str, Any]
    identity: ConsumerIdentity
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)
    expected_resource_version: str | None = Field(default=None, max_length=255)
    request_id: str = Field(pattern=IDENTITY_PATTERN)
    trace_id: str = Field(pattern=IDENTITY_PATTERN)
    deadline: datetime | None = None
    approval_reference: str | None = Field(default=None, pattern=IDENTITY_PATTERN)


def _assert_closed_schema(schema: Mapping[str, Any], path: str) -> None:
    if schema.get("type") == "object" and schema.get("additionalProperties") is not False:
        raise ValueError(f"{path} object schema must declare additionalProperties false")
    for name, child in schema.items():
        if isinstance(child, Mapping):
            _assert_closed_schema(child, f"{path}.{name}")
        elif isinstance(child, (list, tuple)):
            for index, item in enumerate(child):
                if isinstance(item, Mapping):
                    _assert_closed_schema(item, f"{path}.{name}[{index}]")


class CapabilityDescriptorV2(FrozenModel):
    id: str = Field(pattern=CAPABILITY_ID_PATTERN)
    major_version: int = Field(ge=1)
    owner_domain: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")
    lifecycle_status: LifecycleStatus = LifecycleStatus.EXPERIMENTAL
    catalog_release: str | None = Field(default=None, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=4000)
    use_when: str = Field(min_length=1, max_length=4000)
    do_not_use_when: str = Field(min_length=1, max_length=4000)
    # V2.1 names the business outcome separately from the human description.
    business_effect: str | None = Field(default=None, max_length=4000)
    side_effect_level: SideEffectLevel = SideEffectLevel.READ
    side_effects: str | None = Field(default=None, max_length=4000)
    execution_mode: ExecutionMode = ExecutionMode.CLOUD_SYNC
    exposure: ExposurePolicy
    # Exposure must come from an explicitly reviewed provider policy. The
    # adapter default is retained only for legacy/test conversion and is not a
    # release-approved exposure grant.
    exposure_policy_source: Literal["adapter_default", "provider_explicit"] = "adapter_default"
    automation_level: AutomationLevel
    authorization_policy: str = Field(min_length=1, max_length=255)
    resource_selectors: tuple[ResourceSelector, ...] = ()
    data_classification: Literal["public", "internal", "confidential", "restricted"] = "internal"
    required_auth_freshness_seconds: int = Field(default=0, ge=0)
    delegation_policy: Literal["none", "same_actor", "scoped"] = "none"
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    agent_output_schema: Mapping[str, Any] | None = None
    schema_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    artifact_policy: Literal["none", "input", "output", "input_output"] = "none"
    operation_policy: Literal["none", "optional", "required"] = "none"
    concurrency_policy: Literal["none", "expected_version"] = "none"
    expected_version_payload_path: str | None = Field(default=None, min_length=1, max_length=512)
    idempotency_policy: Literal["none", "optional", "required"] = "none"
    # Durable outcomes are metadata-only unless a reviewed synchronous capability
    # explicitly opts into retaining its already projected result for replay.
    replay_data_policy: Literal["metadata_only", "projected"] = "metadata_only"
    consistency_policy: Literal["strong", "eventual", "external"] = "strong"
    timeout_seconds: int = Field(default=30, ge=1, le=86400)
    rate_limit_cost: int = Field(default=1, ge=1, le=10000)
    execution_budget: ExecutionBudget = Field(default_factory=ExecutionBudget)
    confirmation_policy: Literal["none", "user", "admin", "dual"] = "none"
    evidence_policy: Literal["none", "optional", "required"] = "optional"
    audit_policy: Literal["standard", "high_risk"] = "standard"
    deprecation_message: str | None = Field(default=None, max_length=2000)
    domain_errors: tuple[DomainErrorContract, ...] = ()
    domain_errors_complete: bool = False
    # V2.1 governance projection fields. Legacy adapters may leave these empty;
    # the Catalog audit requires them before a descriptor can be released stable.
    capability_version_gid: str | None = Field(default=None, min_length=1, max_length=255)
    error_schema: tuple[Mapping[str, Any], ...] = ()
    transaction_policy: Mapping[str, Any] = Field(default_factory=dict)
    consumer_refs: tuple[Mapping[str, Any] | str, ...] = ()
    no_consumer_reason: str | None = Field(default=None, min_length=1, max_length=4000)
    provider_ref: str | None = Field(default=None, min_length=1, max_length=512)
    api_refs: tuple[str, ...] = ()
    test_refs: tuple[Mapping[str, Any], ...] = ()

    @model_validator(mode="after")
    def public_schemas_are_closed(self) -> "CapabilityDescriptorV2":
        _assert_closed_schema(self.input_schema, "input_schema")
        _assert_closed_schema(self.output_schema, "output_schema")
        if self.agent_output_schema is not None:
            _assert_closed_schema(self.agent_output_schema, "agent_output_schema")
        if self.domain_errors_complete and not self.domain_errors:
            raise ValueError("complete domain error contract cannot be empty")
        if self.concurrency_policy == "expected_version" and not self.expected_version_payload_path:
            raise ValueError("expected_version concurrency requires a payload path")
        if self.concurrency_policy == "none" and self.expected_version_payload_path is not None:
            raise ValueError("expected version payload path requires expected_version concurrency")
        codes = [item.code for item in self.domain_errors]
        if len(codes) != len(set(codes)):
            raise ValueError("duplicate domain error contract")
        if not self.error_schema and self.domain_errors:
            object.__setattr__(
                self,
                "error_schema",
                tuple(item.as_error_schema_entry() for item in self.domain_errors),
            )
        return self

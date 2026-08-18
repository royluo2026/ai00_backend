from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from backend.capabilities.models_next import CapabilityExecutionBudget, CapabilityRisk, CapabilitySpec
from backend.capability_v2.contracts import (
    ActorIdentity,
    AutomationLevel,
    CapabilityDescriptorV2,
    CapabilityResultV2,
    CapabilityStatus,
    ConsumerDescriptor,
    ConsumerIdentity,
    ConsumerType,
    ExecutionBudget,
    ExposurePolicy,
    InvocationEnvelope,
    OperationRef,
    TenantIdentity,
)
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec as adapt_v1_spec


def _identity() -> ConsumerIdentity:
    return ConsumerIdentity(
        actor=ActorIdentity(user_id="user_1", authentication_method="jwt", authenticated_at=datetime.now(UTC)),
        tenant=TenantIdentity(tenant_id="tenant_1", membership="member", active_roles=("member",)),
        consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id="ai00.web"),
    )


def test_consumer_identity_forbids_client_permissions():
    with pytest.raises(ValidationError):
        ConsumerIdentity.model_validate({
            **_identity().model_dump(mode="json"),
            "permissions": ["system.admin"],
        })


def test_actor_identity_requires_exactly_one_actor_kind():
    with pytest.raises(ValidationError, match="exactly one"):
        ActorIdentity(
            user_id="user_1",
            service_id="service_1",
            authentication_method="jwt",
            authenticated_at=datetime.now(UTC),
        )

    with pytest.raises(ValidationError, match="timezone-aware"):
        ActorIdentity(
            user_id="user_1",
            authentication_method="jwt",
            authenticated_at=datetime(2026, 8, 10, 8, 0),
        )


def test_result_distinguishes_accepted_from_completed():
    result = CapabilityResultV2.accepted(
        capability_id="simulation.run.start",
        major_version=1,
        correlation_id="req_1",
        operation=OperationRef(operation_id="op_1", status="accepted"),
    )

    assert result.status is CapabilityStatus.ACCEPTED
    assert result.operation_ref is not None
    assert result.operation_ref.operation_id == "op_1"
    assert result.data is None


def test_exposure_policy_covers_worker_and_local_runtime_without_implicit_access():
    closed = ExposurePolicy()
    opened = ExposurePolicy(worker=True, local_runtime=True)

    assert closed.allows(ConsumerType.WORKER) is False
    assert closed.allows(ConsumerType.LOCAL_RUNTIME) is False
    assert opened.allows(ConsumerType.WORKER) is True
    assert opened.allows(ConsumerType.LOCAL_RUNTIME) is True


def test_result_rejects_contradictory_status_and_unknown_outcome_without_evidence():
    common = {
        "capability_id": "local.device.execute",
        "major_version": 1,
        "correlation": {"request_id": "req_1"},
    }

    with pytest.raises(ValidationError, match="completed result must be ok"):
        CapabilityResultV2(ok=False, status="completed", **common)
    with pytest.raises(ValidationError, match="accepted result cannot contain data"):
        CapabilityResultV2(
            ok=True,
            status="accepted",
            data={"completed": True},
            operation_ref={"operation_id": "op_1", "status": "accepted"},
            **common,
        )
    with pytest.raises(ValidationError, match="outcome_unknown result requires operation_ref and error"):
        CapabilityResultV2(ok=False, status="outcome_unknown", **common)


def test_descriptor_rejects_open_public_object_schema():
    with pytest.raises(ValidationError, match="additionalProperties"):
        CapabilityDescriptorV2(
            id="craft.routing.get",
            major_version=1,
            owner_domain="craft",
            title="Get routing",
            description="Return one routing.",
            use_when="A caller needs one routing.",
            do_not_use_when="A caller needs to publish a routing.",
            exposure=ExposurePolicy(web=True, plugin=True, agent=True, api=True, mcp=True),
            automation_level=AutomationLevel.A2,
            authorization_policy="craft.routing.read",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}, "additionalProperties": False},
            schema_hash="sha256:" + "0" * 64,
        )


def test_descriptor_rejects_explicitly_open_and_composed_nested_object_schemas():
    common = {
        "id": "craft.routing.get",
        "major_version": 1,
        "owner_domain": "craft",
        "title": "Get routing",
        "description": "Return one routing.",
        "use_when": "A caller needs one routing.",
        "do_not_use_when": "A caller needs to publish a routing.",
        "exposure": ExposurePolicy(web=True),
        "automation_level": AutomationLevel.A2,
        "authorization_policy": "craft.routing.read",
        "output_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "schema_hash": "sha256:" + "0" * 64,
    }

    with pytest.raises(ValidationError, match="additionalProperties false"):
        CapabilityDescriptorV2(
            **common,
            input_schema={"type": "object", "properties": {}, "additionalProperties": True},
        )
    with pytest.raises(ValidationError, match="additionalProperties false"):
        CapabilityDescriptorV2(
            **common,
            input_schema={
                "oneOf": [
                    {"type": "object", "properties": {}, "additionalProperties": False},
                    {"type": "object", "properties": {}},
                ]
            },
        )


def test_invocation_requires_catalog_and_major_version():
    with pytest.raises(ValidationError):
        InvocationEnvelope(
            capability_id="craft.routing.get",
            major_version=0,
            catalog_release="",
            payload={},
            identity=_identity(),
            request_id="req_1",
            trace_id="trace_1",
        )


def test_v1_adapter_is_experimental_and_never_infers_plugin_or_agent_write_access():
    spec = CapabilitySpec(
        id="craft.routing.publish",
        version=2,
        owner="craft",
        description="Publish a routing.",
        risk=CapabilityRisk.WRITE,
        plugin_callable=True,
        permissions=("craft.publish",),
        input_schema={"type": "object", "properties": {"routing_id": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"published": {"type": "boolean"}}},
    )

    descriptor = adapt_v1_spec(spec)

    assert descriptor.lifecycle_status == "experimental"
    assert descriptor.major_version == 2
    assert descriptor.exposure.web is True
    assert descriptor.exposure.api is True
    assert descriptor.exposure.plugin is False
    assert descriptor.exposure.agent is False
    assert descriptor.automation_level is AutomationLevel.A1
    assert descriptor.input_schema["additionalProperties"] is False
    assert descriptor.output_schema["additionalProperties"] is False


def test_v1_adapter_preserves_explicit_execution_budget():
    budget = CapabilityExecutionBudget(
        memory_class="medium",
        max_input_bytes=64 * 1024,
        max_output_bytes=1024 * 1024,
        collection_policy="paged",
        max_page_size=200,
        max_parallel_per_consumer=1,
        max_parallel_per_tenant=4,
        overload_policy="reject",
    )
    descriptor = adapt_v1_spec(CapabilitySpec(
        id="craft.bop.work-package.get",
        owner="craft",
        description="Read one bounded BOP work-package page.",
        execution_budget=budget,
    ))

    assert descriptor.execution_budget == ExecutionBudget.model_validate(budget.model_dump())
    assert descriptor.execution_budget.max_page_size == 200


def test_descriptor_always_contains_a_frozen_conservative_execution_budget():
    descriptor = adapt_v1_spec(CapabilitySpec(
        id="craft.routing.get",
        owner="craft",
        description="Read one routing.",
    ))

    assert descriptor.execution_budget.collection_policy == "bounded"
    assert descriptor.execution_budget.max_input_bytes == 1024 * 1024
    assert descriptor.execution_budget.max_output_bytes == 4 * 1024 * 1024
    with pytest.raises(ValidationError, match="frozen"):
        descriptor.execution_budget.max_output_bytes = 1


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"max_input_bytes": 0}, "greater than 0"),
        ({"max_output_bytes": 0}, "greater than 0"),
        ({"max_parallel_per_consumer": 0}, "greater than 0"),
        ({"max_parallel_per_tenant": 0}, "greater than 0"),
        ({"collection_policy": "paged", "max_page_size": None}, "max_page_size"),
        ({"collection_policy": "bounded", "max_page_size": 10}, "paged"),
    ],
)
def test_execution_budget_rejects_invalid_limits(updates, message):
    values = {
        "memory_class": "small",
        "max_input_bytes": 1024,
        "max_output_bytes": 4096,
        "collection_policy": "bounded",
        "max_page_size": None,
        "max_parallel_per_consumer": 1,
        "max_parallel_per_tenant": 1,
        "overload_policy": "reject",
        **updates,
    }

    with pytest.raises(ValidationError, match=message):
        ExecutionBudget(**values)

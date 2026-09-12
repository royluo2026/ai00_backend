"""Bind existing prepared Simulation workflows to the supported App plan protocol."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib

from backend.contracts.connector_execution_plan_v1 import ConnectorExecutionPlanV1
from backend.contracts.connector_execution_plan_v2 import ConnectorExecutionPlanV2, canonicalize_v2


def _workflow_identity(operations: set[str]) -> tuple[str, int]:
    if "vismockup.view.capture@1" in operations:
        return "simulation.capture_run.start", 2
    if operations == {"vismockup.document.snapshot@1"}:
        return "simulation.document_snapshot.request", 2
    if operations <= {
        "vismockup.application.probe@1", "vismockup.model.attach@1",
        "vismockup.scene.apply@1", "vismockup.scene.verify@1",
    }:
        return "simulation.environment.materialize", 2
    raise ValueError("workflow_v2_operation_unsupported")


def _effect(operation_id: str) -> tuple[str, str | None]:
    if operation_id in {
        "vismockup.model.attach@1", "vismockup.scene.apply@1",
        "vismockup.view.capture@1",
    }:
        return "write", "vismockup.document.snapshot@1"
    return "read", None


def workflow_plan_v2_draft(
    source: ConnectorExecutionPlanV1, *, catalog_release: str,
    confirmation_receipt_id: str | None, now: datetime,
) -> dict:
    """Reissue one prepared V1 intent against the current authenticated App session."""
    capability_id, major = _workflow_identity({step.operation_id for step in source.steps})
    if not catalog_release.startswith("rel_"):
        raise ValueError("catalog_release_required")
    if not confirmation_receipt_id:
        raise ValueError("downstream_confirmation_required")
    issued = now.astimezone(UTC).replace(microsecond=0)
    steps = []
    for step in source.steps:
        payload = dict(step.payload)
        classification, probe = _effect(step.operation_id)
        steps.append({
            "step_id": step.step_id, "operation_id": step.operation_id,
            "contract_hash": step.contract_hash, "depends_on": list(step.depends_on),
            "payload": payload,
            "payload_hash": "sha256:" + hashlib.sha256(canonicalize_v2(payload)).hexdigest(),
            "timeout_seconds": step.timeout_seconds,
            "side_effect_classification": classification,
            "post_condition_probe_id": probe,
        })
    return {
        "protocol": "ai00.connector.execution-plan.v2",
        "plan_id": source.plan_id, "capability_id": capability_id,
        "major_version": major,
        "capability_version_gid": source.capability_version_gid,
        "business_definition_hash": source.business_definition_hash,
        "catalog_release": catalog_release,
        "tenant_id": source.tenant_id, "actor_id": source.user_id,
        "device_id": source.device_id,
        "runtime_generation": 1, "runtime_instance_id": "runtime-pending",
        "adapter_id": source.adapter_id, "adapter_major": source.adapter_major,
        "target_product": source.target_product.model_dump(mode="json"),
        "normalized_input_hash": source.plan_hash,
        "confirmation_receipt_id": confirmation_receipt_id,
        "idempotency_key": source.plan_id,
        "steps": steps,
        "issued_at": issued.isoformat().replace("+00:00", "Z"),
        "expires_at": (issued + timedelta(minutes=15)).isoformat().replace("+00:00", "Z"),
    }


def same_workflow_intent(source: ConnectorExecutionPlanV1, actual: ConnectorExecutionPlanV2) -> bool:
    try:
        capability_id, major = _workflow_identity({step.operation_id for step in source.steps})
    except ValueError:
        return False
    if (
        (actual.plan_id, actual.capability_id, actual.major_version,
         actual.capability_version_gid, actual.business_definition_hash,
         actual.tenant_id, actual.actor_id, actual.device_id,
         actual.adapter_id, actual.adapter_major) !=
        (source.plan_id, capability_id, major,
         source.capability_version_gid, source.business_definition_hash,
         source.tenant_id, source.user_id, source.device_id,
         source.adapter_id, source.adapter_major)
        or actual.target_product.model_dump(mode="json") != source.target_product.model_dump(mode="json")
        or actual.normalized_input_hash != source.plan_hash
        or len(actual.steps) != len(source.steps)
    ):
        return False
    for expected, observed in zip(source.steps, actual.steps, strict=True):
        if (expected.step_id, expected.operation_id, expected.contract_hash,
            tuple(expected.depends_on), expected.timeout_seconds,
            *_effect(expected.operation_id)) != (
            observed.step_id, observed.operation_id, observed.contract_hash,
            tuple(observed.depends_on), observed.timeout_seconds,
            observed.side_effect_classification, observed.post_condition_probe_id,
        ) or canonicalize_v2(expected.payload) != canonicalize_v2(observed.payload):
            return False
    return True


def matches_prepared_plan(source: ConnectorExecutionPlanV1 | ConnectorExecutionPlanV2, actual: ConnectorExecutionPlanV1 | ConnectorExecutionPlanV2) -> bool:
    if isinstance(source, ConnectorExecutionPlanV1) and isinstance(actual, ConnectorExecutionPlanV2):
        return same_workflow_intent(source, actual)
    return source.plan_hash == actual.plan_hash and source == actual


__all__ = ["workflow_plan_v2_draft", "same_workflow_intent", "matches_prepared_plan"]

"""Deterministic AI00 Connector plans for Simulation workflows."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from backend.contracts.connector_execution_plan_v1 import (
    ConnectorExecutionPlanV1,
    ConnectorStepV1,
    ConnectorTargetProductV1,
    canonical_hash,
)

from ..domain.environment_manifest import SimulationEnvironmentManifestV1
from ..domain.environment_manifest import REQUIRED_CONNECTOR_OPERATIONS


def _step(
    requirements: dict[str, str], index: int, operation_id: str,
    payload: dict, depends_on: tuple[str, ...],
) -> ConnectorStepV1:
    step_id = f"step-{index:05d}"
    return ConnectorStepV1(
        step_id=step_id,
        operation_id=operation_id,
        contract_hash=requirements[operation_id],
        depends_on=depends_on,
        payload=payload,
        payload_hash=canonical_hash(payload),
        timeout_seconds=120,
    )


def _plan(
    manifest: SimulationEnvironmentManifestV1,
    *,
    plan_id: str,
    device_id: str,
    tenant_id: str,
    user_id: str,
    capability_version_gid: str,
    steps: Iterable[ConnectorStepV1],
    issued_at: datetime,
) -> ConnectorExecutionPlanV1:
    requirement = manifest.connector_requirement
    raw = {
        "protocol": requirement.protocol,
        "plan_id": plan_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "device_id": device_id,
        "capability_version_gid": capability_version_gid,
        "business_definition_hash": canonical_hash({
            "capability": capability_version_gid, "manifest_hash": manifest.manifest_hash,
        }),
        "adapter_id": requirement.adapter_id,
        "adapter_major": requirement.adapter_major,
        "target_product": ConnectorTargetProductV1(**{
            "product_id": requirement.product_id,
            "minimum_version": requirement.minimum_product_version,
            "maximum_version_exclusive": requirement.maximum_product_version_exclusive,
        }),
        "steps": tuple(steps),
        "issued_at": issued_at,
        "expires_at": issued_at + timedelta(minutes=15),
    }
    draft = ConnectorExecutionPlanV1.model_construct(
        **raw, plan_hash="sha256:" + "0" * 64,
    )
    return ConnectorExecutionPlanV1(**raw, plan_hash=draft.compute_hash())


def build_materialization_plan(
    manifest: SimulationEnvironmentManifestV1,
    *, plan_id: str, device_id: str, tenant_id: str, user_id: str, issued_at: datetime,
) -> ConnectorExecutionPlanV1:
    requirements = {
        item.operation_id: item.contract_hash for item in manifest.connector_requirement.operations
    }
    steps: list[ConnectorStepV1] = []

    def add(operation_id: str, payload: dict) -> None:
        dependency = (steps[-1].step_id,) if steps else ()
        steps.append(_step(requirements, len(steps) + 1, operation_id, payload, dependency))

    add("vismockup.application.probe@1", {"allow_launch": False})
    for binding in manifest.resource_bindings:
        add("vismockup.model.attach@1", {
            "document_id": manifest.document_source.document_id,
            "baseline_snapshot_hash": manifest.document_source.snapshot_hash,
            "binding": binding.model_dump(mode="json"),
        })
    baseline = manifest.operations[-1].scene
    add("vismockup.scene.apply@1", {
        "document_id": manifest.document_source.document_id,
        "baseline_snapshot_hash": manifest.document_source.snapshot_hash,
        "operation_id": baseline.operation_id,
        "scene": baseline.model_dump(mode="json"),
    })
    add("vismockup.scene.verify@1", {
        "document_id": manifest.document_source.document_id,
        "operation_id": baseline.operation_id,
        "expected_scene_hash": baseline.scene_hash,
    })
    return _plan(
        manifest, plan_id=plan_id, device_id=device_id, tenant_id=tenant_id,
        user_id=user_id, capability_version_gid="simulation.environment.materialize@1",
        steps=steps, issued_at=issued_at,
    )


def build_capture_plan(
    manifest: SimulationEnvironmentManifestV1,
    *, plan_id: str, device_id: str, tenant_id: str, user_id: str, issued_at: datetime,
    operations: Iterable[str] | None = None, attempt: int = 1,
    capture_run_id: str | None = None,
) -> ConnectorExecutionPlanV1:
    requirements = {
        item.operation_id: item.contract_hash for item in manifest.connector_requirement.operations
    }
    selected = set(operations) if operations is not None else None
    ordered = [
        item for item in sorted(
            manifest.operations, key=lambda item: (item.sequence, item.operation_id), reverse=True,
        )
        if selected is None or item.operation_id in selected
    ]
    if not ordered:
        raise ValueError("capture_plan_empty")
    if len(ordered) != 1:
        raise ValueError("capture_plan_requires_one_operation")
    steps: list[ConnectorStepV1] = []

    def add(operation_id: str, payload: dict) -> None:
        dependency = (steps[-1].step_id,) if steps else ()
        steps.append(_step(requirements, len(steps) + 1, operation_id, payload, dependency))

    for operation in ordered:
        scene = operation.scene
        common = {
            "document_id": manifest.document_source.document_id,
            "baseline_snapshot_hash": manifest.document_source.snapshot_hash,
            "operation_id": operation.operation_id,
        }
        add("vismockup.scene.apply@1", {**common, "scene": scene.model_dump(mode="json")})
        add("vismockup.scene.verify@1", {
            "document_id": common["document_id"], "operation_id": operation.operation_id,
            "expected_scene_hash": scene.scene_hash,
        })
        add("vismockup.view.capture@1", {
            "operation_id": operation.operation_id,
            "capture_run_id": capture_run_id or plan_id, "attempt": attempt,
            "artifact_resource_refs": [
                f"craft-bop-version:{manifest.execution_source.bop_version_gid}"
            ],
            **manifest.capture_profile.model_dump(mode="json"),
        })
    return _plan(
        manifest, plan_id=plan_id, device_id=device_id, tenant_id=tenant_id,
        user_id=user_id, capability_version_gid="simulation.capture_run.start@1",
        steps=steps, issued_at=issued_at,
    )


def build_document_snapshot_plan(
    *, plan_id: str, device_id: str, tenant_id: str, user_id: str, issued_at: datetime,
) -> ConnectorExecutionPlanV1:
    operation_id = "vismockup.document.snapshot@1"
    step = _step(
        REQUIRED_CONNECTOR_OPERATIONS, 1, operation_id,
        {"max_nodes": 10_000, "max_depth": 64}, (),
    )
    raw = {
        "protocol": "ai00.connector.execution-plan.v1",
        "plan_id": plan_id, "tenant_id": tenant_id, "user_id": user_id,
        "device_id": device_id,
        "capability_version_gid": "simulation.document_snapshot.request@1",
        "business_definition_hash": canonical_hash({
            "capability": "simulation.document_snapshot.request@1",
            "device_id": device_id,
        }),
        "adapter_id": "ai00.vismockup", "adapter_major": 1,
        "target_product": ConnectorTargetProductV1(
            product_id="siemens.vismockup", minimum_version="14.0.0",
            maximum_version_exclusive="15.0.0",
        ),
        "steps": (step,), "issued_at": issued_at,
        "expires_at": issued_at + timedelta(minutes=5),
    }
    draft = ConnectorExecutionPlanV1.model_construct(
        **raw, plan_hash="sha256:" + "0" * 64,
    )
    return ConnectorExecutionPlanV1(**raw, plan_hash=draft.compute_hash())


__all__ = ["build_capture_plan", "build_document_snapshot_plan", "build_materialization_plan"]

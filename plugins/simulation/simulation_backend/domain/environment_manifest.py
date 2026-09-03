"""Pure composition of immutable Connector-oriented Simulation environments."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any, Literal, Mapping

from pydantic import Field

from backend.capability_v2.contracts import FrozenModel
from backend.domain_ports.local_integration import HASH_PATTERN


def _canonical_hash(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _normalized_code(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value)).strip().casefold()


class ArtifactRefV1(FrozenModel):
    artifact_id: str
    media_type: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(ge=0)
    version: int = Field(ge=1)


class ModelSnapshotRefV1(FrozenModel):
    model_id: str
    version_id: str
    snapshot_hash: str = Field(pattern=HASH_PATTERN)
    artifact_ref: ArtifactRefV1


class CaptureProfileV1(FrozenModel):
    format: Literal["png", "jpeg"]
    width: int = Field(ge=1, le=16384)
    height: int = Field(ge=1, le=16384)
    background: Literal["current", "transparent", "white", "black"] = "current"


_OPERATION_FIELDS = {
    "vismockup.application.probe@1": (("allow_launch",), ("process_ready", "document_ready", "product_version")),
    "vismockup.document.snapshot@1": (("max_nodes", "max_depth"), ("document_id", "root_node_key", "source_identity", "snapshot_hash", "nodes")),
    "vismockup.model.attach@1": (("document_id", "baseline_snapshot_hash", "binding",), ("node_key", "binding_id")),
    "vismockup.scene.apply@1": (("document_id", "baseline_snapshot_hash", "scene"), ("actual_scene_hash",)),
    "vismockup.scene.verify@1": (("document_id", "expected_scene_hash"), ("actual_scene_hash", "matches")),
    "vismockup.view.capture@1": (("format", "width", "height", "background"), ("artifact",)),
}
REQUIRED_CONNECTOR_OPERATIONS = {
    operation_id: _canonical_hash({
        "operation_id": operation_id,
        "input_fields": input_fields,
        "output_fields": output_fields,
        "contract_version": 1,
    })
    for operation_id, (input_fields, output_fields) in _OPERATION_FIELDS.items()
}


class ConnectorOperationRequirementV1(FrozenModel):
    operation_id: str
    contract_hash: str = Field(pattern=HASH_PATTERN)


class ConnectorRequirementV1(FrozenModel):
    protocol: Literal["ai00.connector.execution-plan.v1"]
    adapter_id: Literal["ai00.vismockup"]
    adapter_major: Literal[1]
    product_id: Literal["siemens.vismockup"]
    minimum_product_version: str
    maximum_product_version_exclusive: str
    operations: tuple[ConnectorOperationRequirementV1, ...]


class ExecutionSourceV1(FrozenModel):
    bop_version_gid: str
    revision: int = Field(ge=1)
    project_gid: str
    content_hash: str = Field(pattern=HASH_PATTERN)
    execution_plan_uri: str


class DocumentSourceV1(FrozenModel):
    document_id: str
    root_node_key: str
    source_identity: str
    snapshot_hash: str = Field(pattern=HASH_PATTERN)


class ProductBindingV1(FrozenModel):
    product_ref: str
    node_key: str


class ResourceBindingV1(FrozenModel):
    resource_type: Literal["tool", "equipment", "fixture"]
    code: str
    normalized_code: str
    node_key: str
    model_ref: ModelSnapshotRefV1


class SceneStateV1(FrozenModel):
    operation_id: str
    visible_products: tuple[str, ...]
    visible_resources: tuple[str, ...]
    capture_profile: CaptureProfileV1
    scene_hash: str = Field(pattern=HASH_PATTERN)


class ManifestOperationV1(FrozenModel):
    operation_id: str
    sequence: int = Field(ge=0)
    predecessor_ids: tuple[str, ...] = ()
    product_node_keys: tuple[str, ...] = ()
    resource_node_keys: tuple[str, ...] = ()
    scene: SceneStateV1


class SimulationEnvironmentManifestV1(FrozenModel):
    environment_id: str
    environment_version: int = Field(ge=1)
    execution_source: ExecutionSourceV1
    document_source: DocumentSourceV1
    mapping_snapshot_hash: str = Field(pattern=HASH_PATTERN)
    product_bindings: tuple[ProductBindingV1, ...]
    resource_bindings: tuple[ResourceBindingV1, ...]
    operations: tuple[ManifestOperationV1, ...]
    capture_profile: CaptureProfileV1
    connector_requirement: ConnectorRequirementV1
    manifest_hash: str = Field(pattern=HASH_PATTERN)

    def scene_for(self, operation_id: str) -> SceneStateV1:
        for operation in self.operations:
            if operation.operation_id == operation_id:
                return operation.scene
        raise KeyError(operation_id)


class BindingProblem(FrozenModel):
    kind: Literal["not_found", "ambiguous"]
    source_type: Literal["product", "tool", "equipment", "fixture"]
    source_code: str
    candidates: tuple[str, ...] = ()


class CompositionResult(FrozenModel):
    manifest: SimulationEnvironmentManifestV1 | None
    problems: tuple[BindingProblem, ...]


def _candidate_ref(model: Mapping[str, Any]) -> str:
    return f"{model.get('model_id', '')}@{model.get('version_id', '')}"


def _resource_node_keys(keys: tuple[tuple[str, str], ...]) -> dict[tuple[str, str], str]:
    """Assign stable occurrence-independent local node keys in canonical order."""
    return {
        key: f"resource-node-{key[0]}-{index * 10}"
        for index, key in enumerate(keys, start=1)
    }


def compose_manifest(
    execution_plan: Mapping[str, Any],
    document_snapshot: Mapping[str, Any],
    model_mappings: Mapping[str, Any],
    capture_profile: Mapping[str, Any],
) -> CompositionResult:
    """Resolve every binding, then build a deterministic immutable manifest."""
    operations = sorted(
        (dict(item) for item in execution_plan.get("operations", ())),
        key=lambda item: (int(item.get("sequence", 0)), str(item.get("operation_id", ""))),
    )
    product_candidates: dict[str, list[str]] = {}
    for raw in document_snapshot.get("nodes", ()):
        product_ref = str(raw.get("product_ref") or "").strip()
        node_key = str(raw.get("node_key") or "").strip()
        if product_ref and node_key:
            product_candidates.setdefault(product_ref, []).append(node_key)
    for candidates in product_candidates.values():
        candidates.sort()

    requested_products = sorted({
        str(product.get("product_ref") or "").strip()
        for operation in operations
        for product in operation.get("products", ())
        if str(product.get("product_ref") or "").strip()
    })
    requested_resources = tuple(sorted({
        (str(resource.get("resource_type") or ""), _normalized_code(resource.get("code", "")))
        for operation in operations
        for resource in operation.get("resources", ())
        if str(resource.get("resource_type") or "") and _normalized_code(resource.get("code", ""))
    }))

    resolved_models: dict[tuple[str, str], list[tuple[str, Mapping[str, Any]]]] = {}
    original_codes: dict[tuple[str, str], str] = {}
    for raw in model_mappings.get("resolved", ()):
        key = (str(raw.get("resource_type") or ""), str(raw.get("normalized_code") or _normalized_code(raw.get("code", ""))))
        original_codes.setdefault(key, str(raw.get("code") or ""))
        resolved_models.setdefault(key, []).append((str(raw.get("code") or ""), raw["model_ref"]))

    unresolved = {
        (str(raw.get("resource_type") or ""), str(raw.get("normalized_code") or _normalized_code(raw.get("code", "")))): str(raw.get("code") or "")
        for raw in model_mappings.get("unresolved", ())
    }
    ambiguous = {
        (str(raw.get("resource_type") or ""), str(raw.get("normalized_code") or _normalized_code(raw.get("code", "")))): (
            str(raw.get("code") or ""), tuple(sorted(_candidate_ref(item) for item in raw.get("candidates", ())))
        )
        for raw in model_mappings.get("ambiguous", ())
    }

    problems: list[BindingProblem] = []
    for product_ref in requested_products:
        candidates = tuple(product_candidates.get(product_ref, ()))
        if not candidates:
            problems.append(BindingProblem(kind="not_found", source_type="product", source_code=product_ref))
        elif len(candidates) > 1:
            problems.append(BindingProblem(kind="ambiguous", source_type="product", source_code=product_ref, candidates=candidates))
    for key in requested_resources:
        source_type, _ = key
        rows = resolved_models.get(key, ())
        source_code = original_codes.get(key) or unresolved.get(key) or ambiguous.get(key, (key[1], ()))[0] or key[1]
        if key in ambiguous:
            problems.append(BindingProblem(kind="ambiguous", source_type=source_type, source_code=source_code, candidates=ambiguous[key][1]))
        elif not rows:
            problems.append(BindingProblem(kind="not_found", source_type=source_type, source_code=source_code))
        elif len({_candidate_ref(model) for _, model in rows}) > 1:
            problems.append(BindingProblem(
                kind="ambiguous", source_type=source_type, source_code=source_code,
                candidates=tuple(sorted({_candidate_ref(model) for _, model in rows})),
            ))
    if problems:
        return CompositionResult(
            manifest=None,
            problems=tuple(sorted(problems, key=lambda item: (item.source_code, item.source_type, item.kind))),
        )

    profile = CaptureProfileV1.model_validate(capture_profile)
    product_bindings = tuple(
        ProductBindingV1(product_ref=product_ref, node_key=product_candidates[product_ref][0])
        for product_ref in requested_products
    )
    product_nodes = {item.product_ref: item.node_key for item in product_bindings}
    resource_nodes = _resource_node_keys(requested_resources)
    resource_bindings = tuple(
        ResourceBindingV1(
            resource_type=key[0], code=resolved_models[key][0][0], normalized_code=key[1],
            node_key=resource_nodes[key], model_ref=resolved_models[key][0][1],
        )
        for key in requested_resources
    )

    cumulative_products: set[str] = set()
    manifest_operations: list[ManifestOperationV1] = []
    for operation in operations:
        current_products = tuple(sorted({
            product_nodes[str(item["product_ref"]).strip()]
            for item in operation.get("products", ())
            if str(item.get("product_ref") or "").strip()
        }))
        cumulative_products.update(current_products)
        current_resources = tuple(sorted({
            resource_nodes[(str(item["resource_type"]), _normalized_code(item["code"]))]
            for item in operation.get("resources", ())
        }))
        scene_without_hash = {
            "operation_id": str(operation["operation_id"]),
            "visible_products": tuple(sorted(cumulative_products)),
            "visible_resources": current_resources,
            "capture_profile": profile.model_dump(mode="json"),
        }
        scene = SceneStateV1(**scene_without_hash, scene_hash=_canonical_hash(scene_without_hash))
        manifest_operations.append(ManifestOperationV1(
            operation_id=str(operation["operation_id"]),
            sequence=int(operation.get("sequence", 0)),
            predecessor_ids=tuple(sorted(set(operation.get("predecessor_ids", ())))),
            product_node_keys=current_products,
            resource_node_keys=current_resources,
            scene=scene,
        ))

    source = execution_plan.get("source", {})
    execution_source = ExecutionSourceV1(
        bop_version_gid=str(source["bop_version_gid"]),
        revision=int(source["revision"]),
        project_gid=str(source["project_gid"]),
        content_hash=str(execution_plan["content_hash"]),
        execution_plan_uri=f"craft://bop/version/{source['bop_version_gid']}/execution-structure/r{source['revision']}",
    )
    document_source = DocumentSourceV1(
        document_id=str(document_snapshot["document_id"]),
        root_node_key=str(document_snapshot["root_node_key"]),
        source_identity=str(document_snapshot["source_identity"]),
        snapshot_hash=str(document_snapshot["snapshot_hash"]),
    )
    body = {
        "environment_version": 1,
        "execution_source": execution_source.model_dump(mode="json"),
        "document_source": document_source.model_dump(mode="json"),
        "mapping_snapshot_hash": str(model_mappings["mapping_snapshot_hash"]),
        "product_bindings": [item.model_dump(mode="json") for item in product_bindings],
        "resource_bindings": [item.model_dump(mode="json") for item in resource_bindings],
        "operations": [item.model_dump(mode="json") for item in manifest_operations],
        "capture_profile": profile.model_dump(mode="json"),
        "connector_requirement": ConnectorRequirementV1(
            protocol="ai00.connector.execution-plan.v1",
            adapter_id="ai00.vismockup",
            adapter_major=1,
            product_id="siemens.vismockup",
            minimum_product_version="1.0.0",
            maximum_product_version_exclusive="2.0.0",
            operations=tuple(
                ConnectorOperationRequirementV1(operation_id=operation_id, contract_hash=contract_hash)
                for operation_id, contract_hash in sorted(REQUIRED_CONNECTOR_OPERATIONS.items())
            ),
        ).model_dump(mode="json"),
    }
    content_hash = _canonical_hash(body)
    environment_id = "senv_" + re.sub(r"[^0-9a-f]", "", content_hash)[0:32]
    manifest_body = {"environment_id": environment_id, **body}
    manifest = SimulationEnvironmentManifestV1(
        **manifest_body, manifest_hash=_canonical_hash(manifest_body)
    )
    return CompositionResult(manifest=manifest, problems=())


__all__ = [
    "BindingProblem", "CaptureProfileV1", "CompositionResult", "ManifestOperationV1",
    "REQUIRED_CONNECTOR_OPERATIONS", "SceneStateV1", "SimulationEnvironmentManifestV1",
    "compose_manifest",
]

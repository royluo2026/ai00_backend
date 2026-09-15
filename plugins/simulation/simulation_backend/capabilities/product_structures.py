"""Governed persistence for read-only Teamcenter structure observations."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError, CapabilityContext, CapabilityOutput, CapabilitySpec, EvidenceRef,
)

from ..data.product_structure_observation_repository import (
    ProductStructureObservationRepository, ProductStructureRepositoryError,
)
from ..domain.product_structure_observation import (
    GeometryReference, ObservationPage, OccurrenceRecord, SourceSelector,
)


def _scope(context: CapabilityContext) -> tuple[str, str]:
    tenant_gid, actor_gid = str(context.team_gid or ""), str(context.user_gid or "")
    if not tenant_gid or not actor_gid:
        raise CapabilityBusinessError("workspace_identity_required", "workspace_identity_required")
    return tenant_gid, actor_gid


def _output(data: dict[str, Any], action: str, reference: str) -> CapabilityOutput:
    body = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return CapabilityOutput(data=data, evidence=(EvidenceRef(
        kind="simulation.product_structure", reference=reference,
        digest="sha256:" + hashlib.sha256(body.encode()).hexdigest(), summary=action,
    ),))


def _selector(value: dict[str, Any]) -> SourceSelector:
    return SourceSelector(**{key: str(value.get(key) or "") for key in (
        "endpoint_id", "object_uid", "item_revision_uid", "bom_view_uid",
        "revision_rule", "configuration_date",
    )})


def _node(value: dict[str, Any]) -> OccurrenceRecord:
    return OccurrenceRecord(
        occurrence_id=str(value.get("occurrence_id") or ""),
        parent_occurrence_id=(str(value["parent_occurrence_id"]) if value.get("parent_occurrence_id") is not None else None),
        depth=int(value.get("depth", -1)), child_order=int(value.get("child_order", -1)),
        name=str(value.get("name") or ""), item_uid=str(value.get("item_uid") or ""),
        item_id=str(value.get("item_id") or ""), item_revision_uid=str(value.get("item_revision_uid") or ""),
        revision_id=str(value.get("revision_id") or ""), component_type=str(value.get("component_type") or ""),
        owning_user=str(value.get("owning_user") or ""), owning_group=str(value.get("owning_group") or ""),
        transform=tuple(value["transform"]) if value.get("transform") is not None else None,
        bbox=tuple(value["bbox"]) if value.get("bbox") is not None else None,
        geometry_refs=tuple(GeometryReference(**item) for item in value.get("geometry_refs", [])),
        absolute_transform=tuple(value["absolute_transform"]) if value.get("absolute_transform") is not None else None,
        transform_unit=str(value.get("transform_unit") or ""),
        transform_convention=str(value.get("transform_convention") or ""),
        bbox_unit=str(value.get("bbox_unit") or ""), torque_raw=value.get("torque_raw"),
        torque_importance=value.get("torque_importance"), weight_raw=value.get("weight_raw"),
        unit_weight_raw=value.get("unit_weight_raw"),
    )


class ProductStructureProvider:
    def __init__(self, repository: ProductStructureObservationRepository | None = None) -> None:
        self.repository = repository or ProductStructureObservationRepository()

    def _call(self, action: str, reference: str, function, **kwargs) -> CapabilityOutput:
        try:
            return _output(function(**kwargs), action, reference)
        except (ProductStructureRepositoryError, TypeError, ValueError) as exc:
            code = str(exc) or "product_structure_invalid"
            raise CapabilityBusinessError(code, code, retryable=code == "version_conflict") from exc

    def bind_source(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        tenant_gid, actor_gid = _scope(context)
        workspace_gid = str(payload.get("workspace_gid") or "")
        return self._call("online_source_bound", f"simulation://workspace/{workspace_gid}/online-sources",
            self.repository.register_online_source, workspace_gid=workspace_gid,
            selector=_selector(payload["source_selector"]), display_name=str(payload.get("display_name") or ""),
            expected_workspace_version=int(payload.get("expected_row_version", 0)), actor_gid=actor_gid,
            tenant_gid=tenant_gid, insertion_instance_id=str(payload.get("insertion_instance_id") or ""))

    def begin(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        tenant_gid, actor_gid = _scope(context)
        return self._call("observation_started", f"simulation://product-structure/{payload.get('observation_id')}",
            self.repository.begin_observation, source_gid=str(payload.get("source_gid") or ""),
            workspace_gid=str(payload.get("workspace_gid") or ""), tenant_gid=tenant_gid, actor_gid=actor_gid,
            observation_id=str(payload.get("observation_id") or ""), captured_at=str(payload.get("captured_at") or ""),
            node_count=int(payload.get("node_count", 0)), page_count=int(payload.get("page_count", 0)))

    def append_page(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        tenant_gid, actor_gid = _scope(context)
        page = ObservationPage(int(payload.get("cursor", -1)), payload.get("next_cursor"),
                               tuple(_node(value) for value in payload.get("nodes", [])))
        observation_gid = str(payload.get("observation_gid") or "")
        return self._call("observation_page_appended", f"simulation://product-structure/{observation_gid}/pages",
            self.repository.append_observation_page, observation_gid=observation_gid,
            page_index=int(payload.get("page_index", -1)), page=page,
            tenant_gid=tenant_gid, actor_gid=actor_gid)

    def publish(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        tenant_gid, actor_gid = _scope(context)
        observation_gid = str(payload.get("observation_gid") or "")
        return self._call("observation_published", f"simulation://product-structure/{observation_gid}",
            self.repository.publish_observation, observation_gid=observation_gid,
            tenant_gid=tenant_gid, actor_gid=actor_gid)

    def read_page(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        tenant_gid, actor_gid = _scope(context)
        observation_id = str(payload.get("observation_id") or "")
        return self._call("snapshot_page_read", f"simulation://product-structure/{observation_id}",
            self.repository.get_observation_page, observation_id=observation_id, tenant_gid=tenant_gid,
            actor_gid=actor_gid, cursor=int(payload.get("cursor", -1)), page_size=int(payload.get("page_size", 0)))


def specs(provider: ProductStructureProvider | None = None):
    selected = provider or ProductStructureProvider()
    gid = {"type": "string", "pattern": "^[1-9][0-9]*$"}
    sha = {"type": "string", "pattern": "^sha256:[a-f0-9]{64}$"}
    observation_id = {"type": "string", "pattern": "^tcobs:[a-f0-9]{64}$"}
    selector = {"type": "object", "required": ["endpoint_id", "object_uid", "item_revision_uid", "bom_view_uid", "revision_rule", "configuration_date"],
        "properties": {"endpoint_id": {"const": "tc-production"}, "object_uid": {"type": "string", "minLength": 1, "maxLength": 128},
            "item_revision_uid": {"type": "string", "maxLength": 128}, "bom_view_uid": {"type": "string", "maxLength": 128},
            "revision_rule": {"type": "string", "minLength": 1, "maxLength": 128}, "configuration_date": {"type": "string", "format": "date-time"}},
        "additionalProperties": False}
    geometry = {"type": "object", "required": ["dataset_uid", "file_uid", "file_name", "relation_type"],
        "properties": {"dataset_uid": {"type": "string", "minLength": 1, "maxLength": 128}, "file_uid": {"type": "string", "minLength": 1, "maxLength": 128},
            "file_name": {"type": "string", "minLength": 1, "maxLength": 1024}, "relation_type": {"type": "string", "minLength": 1, "maxLength": 128}},
        "additionalProperties": False}
    node = {"type": "object", "required": ["occurrence_id", "parent_occurrence_id", "depth", "child_order", "name", "item_uid", "item_id", "item_revision_uid", "revision_id", "component_type", "owning_user", "owning_group", "transform", "absolute_transform", "transform_unit", "transform_convention", "bbox", "bbox_unit", "torque_raw", "torque_importance", "weight_raw", "unit_weight_raw", "geometry_refs"],
        "properties": {"occurrence_id": {"type": "string", "minLength": 1, "maxLength": 512}, "parent_occurrence_id": {"anyOf": [{"type": "string", "minLength": 1, "maxLength": 512}, {"type": "null"}]},
            "depth": {"type": "integer", "minimum": 0, "maximum": 128}, "child_order": {"type": "integer", "minimum": 0}, "name": {"type": "string", "maxLength": 2048},
            "item_uid": {"type": "string", "maxLength": 128}, "item_id": {"type": "string", "maxLength": 256}, "item_revision_uid": {"type": "string", "maxLength": 128},
            "revision_id": {"type": "string", "maxLength": 128}, "component_type": {"type": "string", "maxLength": 256}, "owning_user": {"type": "string", "maxLength": 256},
            "owning_group": {"type": "string", "maxLength": 256}, "transform": {"anyOf": [{"type": "array", "minItems": 16, "maxItems": 16, "items": {"type": "number"}}, {"type": "null"}]},
            "absolute_transform": {"anyOf": [{"type": "array", "minItems": 16, "maxItems": 16, "items": {"type": "number"}}, {"type": "null"}]},
            "transform_unit": {"type": "string", "maxLength": 32}, "transform_convention": {"type": "string", "maxLength": 64},
            "bbox": {"anyOf": [{"type": "array", "minItems": 6, "maxItems": 6, "items": {"type": "number"}}, {"type": "null"}]},
            "bbox_unit": {"type": "string", "maxLength": 32}, "torque_raw": {"anyOf": [{"type": "string", "maxLength": 256}, {"type": "null"}]},
            "torque_importance": {"anyOf": [{"type": "string", "maxLength": 256}, {"type": "null"}]}, "weight_raw": {"anyOf": [{"type": "string", "maxLength": 256}, {"type": "null"}]},
            "unit_weight_raw": {"anyOf": [{"type": "string", "maxLength": 256}, {"type": "null"}]},
            "geometry_refs": {"type": "array", "maxItems": 64, "items": geometry}}, "additionalProperties": False}
    common = dict(owner="simulation", permissions=("simulation.use",), plugin_callable=True,
                  tags=("simulation", "teamcenter", "product_structure", "experimental"))
    bind_out = {"type": "object", "required": ["source_gid", "document_gid", "source_identity_hash", "insertion_instance_id", "workspace_row_version", "cache_revision_hash"],
        "properties": {"source_gid": gid, "document_gid": gid, "source_identity_hash": sha, "insertion_instance_id": {"type": "string"},
            "workspace_row_version": {"type": "integer", "minimum": 2}, "cache_revision_hash": sha}, "additionalProperties": False}
    begin_out = {"type": "object", "required": ["observation_gid", "observation_id", "captured_at", "node_count", "page_count", "manifest_hash", "complete"],
        "properties": {"observation_gid": gid, "observation_id": observation_id, "captured_at": {"type": "string", "format": "date-time"},
            "node_count": {"type": "integer", "minimum": 1}, "page_count": {"type": "integer", "minimum": 1}, "manifest_hash": sha, "complete": {"const": False}}, "additionalProperties": False}
    return (
        (CapabilitySpec(id="simulation.environment.online_source.bind", version=1, description="Bind one immutable Teamcenter online selector as a model instance in a Simulation environment.", risk="write", confirmation="none", idempotent=True,
            input_schema={"type": "object", "required": ["workspace_gid", "expected_row_version", "display_name", "insertion_instance_id", "source_selector"], "properties": {"workspace_gid": gid, "expected_row_version": {"type": "integer", "minimum": 1}, "display_name": {"type": "string", "maxLength": 512}, "insertion_instance_id": {"type": "string", "minLength": 1, "maxLength": 64}, "source_selector": selector}, "additionalProperties": False}, output_schema=bind_out, **common), selected.bind_source),
        (CapabilitySpec(id="simulation.product_structure.observation.begin", version=1, description="Start an append-only product-structure observation manifest.", risk="write", confirmation="none", idempotent=True,
            input_schema={"type": "object", "required": ["workspace_gid", "source_gid", "observation_id", "captured_at", "node_count", "page_count"], "properties": {"workspace_gid": gid, "source_gid": gid, "observation_id": observation_id, "captured_at": {"type": "string", "format": "date-time"}, "node_count": {"type": "integer", "minimum": 1, "maximum": 250000}, "page_count": {"type": "integer", "minimum": 1, "maximum": 250000}}, "additionalProperties": False}, output_schema=begin_out, **common), selected.begin),
        (CapabilitySpec(id="simulation.product_structure.observation.page.append", version=1, description="Append one immutable page to a product-structure observation.", risk="write", confirmation="none", idempotent=True,
            input_schema={"type": "object", "required": ["observation_gid", "page_index", "cursor", "next_cursor", "nodes"], "properties": {"observation_gid": gid, "page_index": {"type": "integer", "minimum": 0}, "cursor": {"type": "integer", "minimum": 0}, "next_cursor": {"anyOf": [{"type": "integer", "minimum": 0}, {"type": "null"}]}, "nodes": {"type": "array", "maxItems": 1000, "items": node}}, "additionalProperties": False},
            output_schema={"type": "object", "required": ["page_hash", "replayed"], "properties": {"page_hash": sha, "replayed": {"type": "boolean"}}, "additionalProperties": False}, **common), selected.append_page),
        (CapabilitySpec(id="simulation.product_structure.observation.publish", version=1, description="Validate and publish a complete immutable product-structure observation.", risk="write", confirmation="none", idempotent=True,
            input_schema={"type": "object", "required": ["observation_gid"], "properties": {"observation_gid": gid}, "additionalProperties": False},
            output_schema={"type": "object", "required": ["observation_id", "complete", "node_count", "page_count"], "properties": {"observation_id": observation_id, "complete": {"const": True}, "node_count": {"type": "integer", "minimum": 1}, "page_count": {"type": "integer", "minimum": 1}}, "additionalProperties": False}, **common), selected.publish),
        (CapabilitySpec(id="simulation.product_structure.snapshot.page.get", version=1, description="Read one bounded page from a published product-structure snapshot.", risk="read", confirmation="none",
            input_schema={"type": "object", "required": ["observation_id", "cursor", "page_size"], "properties": {"observation_id": observation_id, "cursor": {"type": "integer", "minimum": 0}, "page_size": {"type": "integer", "minimum": 1, "maximum": 1000}}, "additionalProperties": False},
            output_schema={"type": "object", "required": ["observation_id", "cursor", "next_cursor", "nodes", "node_count"], "properties": {"observation_id": observation_id, "cursor": {"type": "integer", "minimum": 0}, "next_cursor": {"anyOf": [{"type": "integer", "minimum": 0}, {"type": "null"}]}, "nodes": {"type": "array", "maxItems": 1000, "items": node}, "node_count": {"type": "integer", "minimum": 1}}, "additionalProperties": False}, **common), selected.read_page),
    )


__all__ = ["ProductStructureProvider", "specs"]

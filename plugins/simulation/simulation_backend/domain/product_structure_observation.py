"""Pure contracts for immutable Teamcenter product-structure observations."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json


class ProductStructureValidationError(ValueError):
    pass


@dataclass(frozen=True)
class SourceSelector:
    endpoint_id: str
    object_uid: str
    item_revision_uid: str
    bom_view_uid: str
    revision_rule: str
    configuration_date: str

    @property
    def identity_hash(self) -> str:
        body = json.dumps(asdict(self), ensure_ascii=False, sort_keys=True,
                          separators=(",", ":")).encode("utf-8")
        return "sha256:" + hashlib.sha256(body).hexdigest()


@dataclass(frozen=True)
class GeometryReference:
    dataset_uid: str
    file_uid: str
    file_name: str
    relation_type: str = "IMAN_Rendering"


@dataclass(frozen=True)
class OccurrenceRecord:
    occurrence_id: str
    parent_occurrence_id: str | None
    depth: int
    child_order: int
    name: str
    item_uid: str
    item_id: str
    item_revision_uid: str
    revision_id: str
    component_type: str
    owning_user: str
    owning_group: str
    transform: tuple[float, ...] | None
    bbox: tuple[float, ...] | None
    geometry_refs: tuple[GeometryReference, ...]
    absolute_transform: tuple[float, ...] | None = None
    transform_unit: str = "m"
    transform_convention: str = "teamcenter_plmxml_4x4_row_major"
    bbox_unit: str = "m"
    torque_raw: str | None = None
    torque_importance: str | None = None
    weight_raw: str | None = None
    unit_weight_raw: str | None = None


@dataclass(frozen=True)
class ObservationPage:
    cursor: int
    next_cursor: int | None
    nodes: tuple[OccurrenceRecord, ...]


def _text(value: str, code: str, maximum: int = 4096) -> None:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ProductStructureValidationError(code)


def validate_observation_pages(pages: tuple[ObservationPage, ...], expected_nodes: int,
                               *, max_nodes: int = 250_000,
                               max_depth: int = 128) -> tuple[OccurrenceRecord, ...]:
    if not isinstance(pages, tuple) or not pages or not 1 <= expected_nodes <= max_nodes:
        raise ProductStructureValidationError("observation_pages_invalid")
    nodes: list[OccurrenceRecord] = []
    expected_cursor = 0
    for index, page in enumerate(pages):
        if page.cursor != expected_cursor or len(page.nodes) > 1000:
            raise ProductStructureValidationError("observation_cursor_invalid")
        expected_cursor += len(page.nodes)
        if page.next_cursor != (None if index == len(pages) - 1 else expected_cursor):
            raise ProductStructureValidationError("observation_cursor_invalid")
        nodes.extend(page.nodes)
    if len(nodes) != expected_nodes:
        raise ProductStructureValidationError("observation_node_count_mismatch")
    by_id: dict[str, OccurrenceRecord] = {}
    for node in nodes:
        _text(node.occurrence_id, "occurrence_identity_invalid")
        if node.occurrence_id in by_id:
            raise ProductStructureValidationError("occurrence_identity_duplicate")
        if node.parent_occurrence_id is not None:
            _text(node.parent_occurrence_id, "occurrence_parent_invalid")
        if type(node.depth) is not int or not 0 <= node.depth <= max_depth or type(node.child_order) is not int or node.child_order < 0:
            raise ProductStructureValidationError("occurrence_position_invalid")
        if node.transform is not None and len(node.transform) != 16:
            raise ProductStructureValidationError("occurrence_transform_invalid")
        if node.absolute_transform is not None and len(node.absolute_transform) != 16:
            raise ProductStructureValidationError("occurrence_transform_invalid")
        if node.bbox is not None and len(node.bbox) != 6:
            raise ProductStructureValidationError("occurrence_bbox_invalid")
        for ref in node.geometry_refs:
            _text(ref.dataset_uid, "geometry_reference_invalid")
            _text(ref.file_uid, "geometry_reference_invalid")
            _text(ref.file_name, "geometry_reference_invalid")
            _text(ref.relation_type, "geometry_reference_invalid", 128)
        by_id[node.occurrence_id] = node
    roots = [node for node in nodes if node.parent_occurrence_id is None]
    if not roots or any(root.depth != 0 for root in roots):
        raise ProductStructureValidationError("occurrence_graph_invalid")
    for node in nodes:
        if node.parent_occurrence_id is None:
            continue
        parent = by_id.get(node.parent_occurrence_id)
        if parent is None or node.depth != parent.depth + 1:
            raise ProductStructureValidationError("occurrence_graph_invalid")
    visited: set[str] = set()
    remaining = {node.occurrence_id for node in nodes}
    children: dict[str, list[str]] = {}
    for node in nodes:
        if node.parent_occurrence_id is not None:
            children.setdefault(node.parent_occurrence_id, []).append(node.occurrence_id)
    frontier = [root.occurrence_id for root in roots]
    while frontier:
        current = frontier.pop()
        if current in visited:
            raise ProductStructureValidationError("occurrence_graph_invalid")
        visited.add(current)
        remaining.discard(current)
        frontier.extend(children.get(current, ()))
    if remaining:
        raise ProductStructureValidationError("occurrence_graph_invalid")
    return tuple(nodes)


__all__ = ["GeometryReference", "ObservationPage", "OccurrenceRecord",
           "ProductStructureValidationError", "SourceSelector", "validate_observation_pages"]

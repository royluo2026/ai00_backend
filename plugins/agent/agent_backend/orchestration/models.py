from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


X_AXIS = ["TG0前", "TG0", "TG1", "TG2", "EP", "PPV", "PP", "P", "SOP"]
Y_AXIS = ["项目管理", "同步工程", "工艺规划", "设备规划"]
MAX_GRAPH_NODES = 500
MAX_GRAPH_EDGES = 2_000
MAX_DECOMPOSITION_ITEMS = 2_000
MAX_BINDINGS = 4_000
MAX_GRAPH_DEPTH = 32
MAX_GRAPH_JSON_BYTES = 2_000_000


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Point(Contract):
    x: float
    y: float


class AxisView(Contract):
    x_items: list[str] = Field(default_factory=lambda: list(X_AXIS), min_length=1)
    y_items: list[str] = Field(default_factory=lambda: list(Y_AXIS), min_length=1)


class BusinessNode(Contract):
    gid: str = Field(min_length=1)
    node_key: str = Field(min_length=1)
    title: str = Field(min_length=1)
    x_item_key: str
    y_item_key: str
    objective: str = ""
    owner_ref: str = ""
    inputs: list[dict[str, Any]] = Field(default_factory=list)
    outputs: list[dict[str, Any]] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    position: Point = Field(default_factory=lambda: Point(x=0, y=0))


class FlowEdge(Contract):
    gid: str = Field(min_length=1)
    edge_type: Literal["business", "data", "command", "semantic"]
    source_node_gid: str = Field(min_length=1)
    target_node_gid: str = Field(min_length=1)
    label: str = ""
    route_points: list[Point] = Field(default_factory=list)

    @model_validator(mode="after")
    def route_is_orthogonal(self):
        for start, end in zip(self.route_points, self.route_points[1:]):
            if start.x != end.x and start.y != end.y:
                raise ValueError("route segments must be orthogonal")
        return self


ItemType = Literal[
    "large_flow",
    "medium_flow",
    "standard_workflow",
    "skill",
    "workflow_node",
    "task_tool",
    "human_task",
    "human_approval",
]


class DecompositionItem(Contract):
    gid: str = Field(min_length=1)
    item_type: ItemType
    title: str = Field(min_length=1)
    business_node_gid: str | None = None
    sequence_no: int = Field(default=0, ge=0)
    config: dict[str, Any] = Field(default_factory=dict)


class DecompositionEdge(Contract):
    gid: str = Field(min_length=1)
    source_item_gid: str = Field(min_length=1)
    target_item_gid: str = Field(min_length=1)
    relation_type: Literal["contains", "realized_by", "guides", "sequence", "implements"]
    sequence_no: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def reject_self_reference(self):
        if self.source_item_gid == self.target_item_gid:
            raise ValueError("decomposition edge cannot reference itself")
        return self


class CapabilityBindingIntent(Contract):
    gid: str = Field(min_length=1)
    source_item_gid: str = Field(min_length=1)
    capability_version_gid: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    input_mapping: dict[str, Any] = Field(default_factory=dict)
    output_mapping: dict[str, Any] = Field(default_factory=dict)
    authorization_scope: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=30, gt=0, le=300)
    retry_policy: dict[str, Any] = Field(default_factory=dict)
    fallback_policy: dict[str, Any] = Field(default_factory=dict)
    evidence_policy: dict[str, Any] = Field(default_factory=dict)


class ContextBinding(Contract):
    gid: str = Field(min_length=1)
    source_item_gid: str = Field(min_length=1)
    ref_type: Literal["data", "rule", "knowledge", "ontology", "code"]
    ref_gid: str = Field(min_length=1)
    ref_version: str | None = None
    snapshot_gid: str | None = None
    purpose: str = Field(min_length=1)


class GraphDraft(Contract):
    mode: Literal["exploration", "fixed"] = "fixed"
    axis: AxisView = Field(default_factory=AxisView)
    nodes: list[BusinessNode] = Field(max_length=MAX_GRAPH_NODES)
    edges: list[FlowEdge] = Field(max_length=MAX_GRAPH_EDGES)
    items: list[DecompositionItem] = Field(default_factory=list, max_length=MAX_DECOMPOSITION_ITEMS)
    item_edges: list[DecompositionEdge] = Field(default_factory=list, max_length=MAX_GRAPH_EDGES)
    capability_bindings: list[CapabilityBindingIntent] = Field(default_factory=list, max_length=MAX_BINDINGS)
    context_bindings: list[ContextBinding] = Field(default_factory=list, max_length=MAX_BINDINGS)

    @model_validator(mode="after")
    def validate_graph_references(self):
        node_ids = {node.gid for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("duplicate node gid")
        if len({node.node_key for node in self.nodes}) != len(self.nodes):
            raise ValueError("duplicate node key")
        for node in self.nodes:
            if node.x_item_key not in self.axis.x_items or node.y_item_key not in self.axis.y_items:
                raise ValueError("business node coordinate is outside axis")
        for edge in self.edges:
            if edge.source_node_gid not in node_ids or edge.target_node_gid not in node_ids:
                raise ValueError("flow edge points to missing node")

        items = {item.gid: item for item in self.items}
        if len(items) != len(self.items):
            raise ValueError("duplicate item gid")
        for item in self.items:
            if item.business_node_gid is not None and item.business_node_gid not in node_ids:
                raise ValueError("decomposition item points to missing business node")
        for edge in self.item_edges:
            if edge.source_item_gid not in items or edge.target_item_gid not in items:
                raise ValueError("decomposition edge points to missing item")
        self._validate_decomposition_dag(items)
        for binding in self.capability_bindings:
            source = items.get(binding.source_item_gid)
            if source is None or source.item_type != "task_tool":
                raise ValueError("Capability bindings must originate from a Task Tool")
        for binding in self.context_bindings:
            if binding.source_item_gid not in items:
                raise ValueError("context binding points to missing item")
        for collection, label in (
            (self.edges, "flow edge"),
            (self.item_edges, "decomposition edge"),
            (self.capability_bindings, "Capability binding"),
            (self.context_bindings, "context binding"),
        ):
            if len({entry.gid for entry in collection}) != len(collection):
                raise ValueError(f"duplicate {label} gid")
        payload = json.dumps(self.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
        if len(payload.encode("utf-8")) > MAX_GRAPH_JSON_BYTES:
            raise ValueError("graph serialized payload exceeds limit")
        return self

    def _validate_decomposition_dag(self, items: dict[str, DecompositionItem]) -> None:
        adjacency = {item_gid: [] for item_gid in items}
        indegree = {item_gid: 0 for item_gid in items}
        for edge in self.item_edges:
            adjacency[edge.source_item_gid].append(edge.target_item_gid)
            indegree[edge.target_item_gid] += 1
        queue = [item_gid for item_gid, degree in indegree.items() if degree == 0]
        depth = {item_gid: 1 for item_gid in queue}
        visited = 0
        while queue:
            item_gid = queue.pop()
            visited += 1
            if depth[item_gid] > MAX_GRAPH_DEPTH:
                raise ValueError("decomposition depth exceeds limit")
            for target_gid in adjacency[item_gid]:
                depth[target_gid] = max(depth.get(target_gid, 1), depth[item_gid] + 1)
                indegree[target_gid] -= 1
                if indegree[target_gid] == 0:
                    queue.append(target_gid)
        if visited != len(items):
            raise ValueError("decomposition graph contains a cycle")


# Temporary source-compatibility name; the contract contains intent fields only.
CapabilityBinding = CapabilityBindingIntent


class PanoramaCreate(Contract):
    name: str = Field(min_length=1, max_length=255)


class PublishResult(Contract):
    panorama_gid: str
    version_gid: str
    revision: int = Field(ge=1)
    status: Literal["published"] = "published"

import copy

import pytest
from pydantic import ValidationError

from plugins.agent.agent_backend.orchestration.models import (
    MAX_BINDINGS,
    MAX_DECOMPOSITION_ITEMS,
    MAX_GRAPH_DEPTH,
    MAX_GRAPH_EDGES,
    MAX_GRAPH_JSON_BYTES,
    MAX_GRAPH_NODES,
    CapabilityBindingIntent,
    FlowEdge,
    GraphDraft,
)


@pytest.fixture
def valid_graph_dict():
    return {
        "axis": {"x_items": ["TG0", "TG1"], "y_items": ["项目管理"]},
        "nodes": [{"gid": "node-1", "node_key": "N1", "title": "立项", "x_item_key": "TG0", "y_item_key": "项目管理"}],
        "edges": [],
        "items": [{"gid": "tool-1", "business_node_gid": "node-1", "item_type": "task_tool", "title": "读取 BOP"}],
        "item_edges": [],
        "capability_bindings": [{"gid": "binding-1", "source_item_gid": "tool-1", "capability_version_gid": "cv2_1", "purpose": "读取已治理 BOP"}],
        "context_bindings": [{"gid": "context-1", "source_item_gid": "tool-1", "ref_type": "data", "ref_gid": "data-1", "purpose": "输入数据"}],
    }


def test_graph_defaults_to_confirmed_project_axes():
    graph = GraphDraft.model_validate({"nodes": [], "edges": []})
    assert graph.axis.x_items == ["TG0前", "TG0", "TG1", "TG2", "EP", "PPV", "PP", "P", "SOP"]
    assert graph.axis.y_items == ["项目管理", "同步工程", "工艺规划", "设备规划"]


def test_capability_binding_requires_business_purpose_and_version_identity():
    with pytest.raises(ValidationError):
        CapabilityBindingIntent.model_validate({"gid": "b1", "source_item_gid": "tool-1"})


@pytest.mark.parametrize("field", ["capability_id", "version_constraint", "gateway_ref", "provider_ref"])
def test_binding_rejects_client_asserted_catalog_fields(field):
    payload = {"gid": "b1", "source_item_gid": "tool-1", "capability_version_gid": "cv2_1", "purpose": "读取 BOP", field: "forged-value"}
    with pytest.raises(ValidationError, match=field):
        CapabilityBindingIntent.model_validate(payload)


def test_flow_route_rejects_diagonal_segments():
    with pytest.raises(ValidationError, match="orthogonal"):
        FlowEdge.model_validate({"gid": "e1", "edge_type": "business", "source_node_gid": "n1", "target_node_gid": "n2", "route_points": [{"x": 0, "y": 0}, {"x": 5, "y": 5}]})


def test_graph_rejects_edges_to_missing_nodes():
    with pytest.raises(ValidationError, match="missing node"):
        GraphDraft.model_validate({"nodes": [], "edges": [{"gid": "e1", "edge_type": "data", "source_node_gid": "n1", "target_node_gid": "n2"}]})


def test_graph_rejects_capability_binding_from_non_task_tool(valid_graph_dict):
    graph = copy.deepcopy(valid_graph_dict)
    graph["items"][0]["item_type"] = "skill"
    with pytest.raises(ValidationError, match="Task Tool"):
        GraphDraft.model_validate(graph)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("duplicate_node_gid", "duplicate node gid"),
        ("coordinate_outside_axis", "outside axis"),
        ("missing_business_node", "missing business node"),
        ("missing_context_source_item", "context binding points to missing item"),
        ("duplicate_item_gid", "duplicate item gid"),
        ("decomposition_cycle", "cycle"),
        ("excessive_depth", "depth"),
    ],
)
def test_graph_rejects_invalid_topology(valid_graph_dict, mutation, message):
    graph = copy.deepcopy(valid_graph_dict)
    if mutation == "duplicate_node_gid":
        graph["nodes"].append({**graph["nodes"][0], "node_key": "N2"})
    elif mutation == "coordinate_outside_axis":
        graph["nodes"][0]["x_item_key"] = "SOP"
    elif mutation == "missing_business_node":
        graph["items"][0]["business_node_gid"] = "missing"
    elif mutation == "missing_context_source_item":
        graph["context_bindings"][0]["source_item_gid"] = "missing"
    elif mutation == "duplicate_item_gid":
        graph["items"].append({**graph["items"][0], "title": "重复"})
    elif mutation == "decomposition_cycle":
        graph["items"].append({"gid": "skill-2", "item_type": "skill", "title": "分析"})
        graph["item_edges"] = [
            {"gid": "ie-1", "source_item_gid": "tool-1", "target_item_gid": "skill-2", "relation_type": "contains"},
            {"gid": "ie-2", "source_item_gid": "skill-2", "target_item_gid": "tool-1", "relation_type": "contains"},
        ]
    elif mutation == "excessive_depth":
        graph["capability_bindings"] = []
        graph["context_bindings"] = []
        graph["items"] = [{"gid": f"item-{index}", "item_type": "skill", "title": str(index)} for index in range(MAX_GRAPH_DEPTH + 2)]
        graph["item_edges"] = [{"gid": f"edge-{index}", "source_item_gid": f"item-{index}", "target_item_gid": f"item-{index + 1}", "relation_type": "contains"} for index in range(MAX_GRAPH_DEPTH + 1)]
    with pytest.raises(ValidationError, match=message):
        GraphDraft.model_validate(graph)


@pytest.mark.parametrize(
    ("field", "limit", "factory"),
    [
        ("nodes", MAX_GRAPH_NODES, lambda index: {"gid": f"n-{index}", "node_key": f"N{index}", "title": "n", "x_item_key": "TG0", "y_item_key": "项目管理"}),
        ("edges", MAX_GRAPH_EDGES, lambda index: {"gid": f"e-{index}", "edge_type": "business", "source_node_gid": "node-1", "target_node_gid": "node-1"}),
        ("items", MAX_DECOMPOSITION_ITEMS, lambda index: {"gid": f"i-{index}", "item_type": "skill", "title": "i"}),
        ("capability_bindings", MAX_BINDINGS, lambda index: {"gid": f"b-{index}", "source_item_gid": "tool-1", "capability_version_gid": "cv2_1", "purpose": "p"}),
        ("context_bindings", MAX_BINDINGS, lambda index: {"gid": f"c-{index}", "source_item_gid": "tool-1", "ref_type": "data", "ref_gid": "d", "purpose": "p"}),
    ],
)
def test_graph_rejects_collection_over_limit(valid_graph_dict, field, limit, factory):
    graph = copy.deepcopy(valid_graph_dict)
    graph[field] = [factory(index) for index in range(limit + 1)]
    with pytest.raises(ValidationError):
        GraphDraft.model_validate(graph)


def test_graph_rejects_serialized_payload_over_limit(valid_graph_dict):
    graph = copy.deepcopy(valid_graph_dict)
    graph["nodes"][0]["objective"] = "x" * MAX_GRAPH_JSON_BYTES
    with pytest.raises(ValidationError, match="serialized payload"):
        GraphDraft.model_validate(graph)

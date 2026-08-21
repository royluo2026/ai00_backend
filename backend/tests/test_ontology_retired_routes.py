from __future__ import annotations

import ast
from pathlib import Path


RETIRED_ROUTE_FUNCTIONS = {
    "list_db_tables",
    "list_node_type_suggestions",
    "list_unbound_classes",
    "list_class_individuals",
    "sync_props_from_table",
    "seed_from_bop",
    "get_entity_props",
    "patch_entity_props",
    "schema_diff",
    "get_node_type_config",
    "validate_entry",
    "get_agent_schema",
}


def test_ontology_legacy_routes_are_explicitly_marked_gone() -> None:
    source = Path("plugins/craft/craft_backend/routers/ontology.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in RETIRED_ROUTE_FUNCTIONS:
            continue
        found.add(node.name)
        assert any(
            isinstance(decorator, ast.Call)
            and any(
                keyword.arg == "status_code"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value == 410
                for keyword in decorator.keywords
            )
            for decorator in node.decorator_list
        ), f"{node.name} must expose HTTP 410 in its route decorator"

    assert found == RETIRED_ROUTE_FUNCTIONS

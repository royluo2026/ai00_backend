from pathlib import Path
import ast


ROUTER = Path("plugins/craft/craft_backend/routers/projects.py")


def test_project_bop_lines_route_uses_craft_gateway_projection():
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    fn = next(node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_project_bop_lines")
    assert any(isinstance(node, ast.Constant) and node.value == "craft.bop.entry.legacy_read" for node in ast.walk(fn))


def test_bop_entry_legacy_read_declares_project_lines_operation():
    from plugins.craft.craft_backend.capabilities.bop_entry_legacy_read import OPERATIONS

    assert "project_bop_lines" in OPERATIONS

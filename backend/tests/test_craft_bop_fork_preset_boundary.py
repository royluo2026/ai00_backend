from pathlib import Path
import ast


ROUTER = Path("plugins/craft/craft_backend/routers/_bop/fork.py")


def test_fork_preset_read_routes_use_gateway_capability():
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    names = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)}
    assert {"list_fork_presets", "get_fork_preset"} <= names.keys()
    for fn in (names["list_fork_presets"], names["get_fork_preset"]):
        assert any(isinstance(node, ast.Constant) and node.value == "craft.bop.fork_preset.read" for node in ast.walk(fn))


def test_fork_preset_provider_is_bounded_read_only():
    from plugins.craft.craft_backend.capabilities.bop_fork_preset_read import MAX_ITEMS, OPERATIONS

    assert OPERATIONS == ("list", "get")
    assert MAX_ITEMS == 500

from pathlib import Path
import ast


ROUTER = Path("plugins/craft/craft_backend/routers/ebom.py")


def test_vpps_check_route_is_gateway_bound_to_dedicated_capability():
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    fn = next(node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "vpps_check")
    assert isinstance(fn, ast.AsyncFunctionDef)
    assert any(isinstance(node, ast.Constant) and node.value == "craft.ebom.vpps_check.read" for node in ast.walk(fn))


def test_vpps_check_provider_is_explicitly_read_only_and_bounded():
    from plugins.craft.craft_backend.capabilities.vpps_check import OPERATIONS, MAX_ERRORS

    assert OPERATIONS == ("check",)
    assert MAX_ERRORS == 500

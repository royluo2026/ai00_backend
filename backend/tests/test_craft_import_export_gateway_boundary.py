from pathlib import Path
import ast


ROUTER = Path("plugins/craft/craft_backend/routers/import_export.py")


def test_template_list_route_uses_base_gateway_capability():
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    fn = functions["list_templates"]
    assert isinstance(fn, ast.AsyncFunctionDef)
    assert any(
        isinstance(node, ast.Constant) and node.value == "base.export_template.read"
        for node in ast.walk(fn)
    )
    assert any(
        isinstance(node, ast.Name) and node.id == "get_default_gateway"
        for node in ast.walk(fn)
    )


def test_template_mutations_use_base_gateway_capability():
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    helper = functions["_invoke_template_change"]
    assert any(
        isinstance(node, ast.Constant)
        and node.value == "base.export_template.change.apply"
        for node in ast.walk(helper)
    )
    for name in ("create_template", "update_template", "delete_template"):
        fn = functions[name]
        assert isinstance(fn, ast.AsyncFunctionDef)
        assert any(
            isinstance(node, ast.Name) and node.id == "_invoke_template_change"
            for node in ast.walk(fn)
        )

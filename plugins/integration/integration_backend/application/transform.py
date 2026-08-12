"""Small, deterministic mapping language; never evaluates Python source."""
from __future__ import annotations

import ast
from typing import Any, Mapping


_FUNCTIONS = {
    "lower": lambda value: str(value).lower(),
    "upper": lambda value: str(value).upper(),
    "strip": lambda value: str(value).strip(),
    "string": lambda value: str(value),
}


class RestrictedExpression:
    def __init__(self, expression: str):
        self.expression = str(expression or "").strip()
        try:
            tree = ast.parse(self.expression, mode="eval")
        except (SyntaxError, ValueError) as exc:
            raise ValueError("invalid mapping expression") from exc
        self._validate(tree)
        self._tree = tree

    @classmethod
    def _validate(cls, node: ast.AST) -> None:
        allowed = (ast.Expression, ast.Call, ast.Name, ast.Attribute, ast.Load, ast.Constant)
        if not isinstance(node, allowed):
            raise ValueError("mapping expression contains a forbidden operation")
        if isinstance(node, ast.Name) and node.id not in {"source", *_FUNCTIONS}:
            raise ValueError("mapping expression contains an unknown name")
        if isinstance(node, ast.Attribute):
            if not isinstance(node.value, ast.Name) or node.value.id != "source" or node.attr.startswith("_"):
                raise ValueError("mapping expression contains forbidden field access")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS or node.keywords:
                raise ValueError("mapping expression contains a forbidden call")
        for child in ast.iter_child_nodes(node):
            cls._validate(child)

    def evaluate(self, source: Mapping[str, Any]) -> Any:
        def visit(node: ast.AST) -> Any:
            if isinstance(node, ast.Expression):
                return visit(node.body)
            if isinstance(node, ast.Constant):
                return node.value
            if isinstance(node, ast.Attribute):
                if node.attr not in source:
                    raise ValueError(f"mapping expression source field is missing: {node.attr}")
                return source[node.attr]
            if isinstance(node, ast.Call):
                return _FUNCTIONS[node.func.id](*(visit(arg) for arg in node.args))
            raise ValueError("mapping expression cannot be evaluated")

        return visit(self._tree)


__all__ = ["RestrictedExpression"]

from __future__ import annotations

import ast
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ALLOWED = {
    "backend/capability_v2/gateway.py",
    "backend/capabilities/registry.py",
    "backend/capabilities/registry_next.py",
}


def test_no_production_consumer_invokes_registry_or_provider_handler_directly():
    violations = []
    for root in (REPOSITORY_ROOT / "backend", REPOSITORY_ROOT / "plugins"):
        for path in root.rglob("*.py"):
            relative = path.relative_to(REPOSITORY_ROOT).as_posix()
            if "/tests/" in f"/{relative}/" or relative in ALLOWED:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                dotted = _dotted(node.func)
                if dotted.endswith("capability_registry.invoke") or dotted.endswith("item.handler"):
                    violations.append(f"{relative}:{node.lineno}:{dotted}")
    assert violations == []


def test_public_route_does_not_trust_client_supplied_consumer_identity_headers():
    source = (REPOSITORY_ROOT / "backend/routers/capabilities.py").read_text(encoding="utf-8")
    assert "X-AI00-Source" not in source
    assert "X-AI00-Plugin-ID" not in source
    assert "X-AI00-Agent-Run-ID" not in source


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""

#!/usr/bin/env python3
"""Audit domain imports, SQL ownership and runtime DDL.

The baseline is a migration aid, not an allow-list: existing debt is recorded once,
and CI fails whenever a new fingerprint appears.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.governance import DomainRegistry, load_registry

DDL_RE = re.compile(r"\b(?:CREATE|ALTER|DROP|RENAME|TRUNCATE)\s+(?:TABLE|INDEX)\b", re.IGNORECASE)
REFERENCE_RE = re.compile(r"\bREFERENCES\s+(workmanship_[a-z0-9_]+)", re.IGNORECASE)
CREATE_TABLE_RE = re.compile(r"\bCREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+(workmanship_[a-z0-9_]+)", re.IGNORECASE)


@dataclass(frozen=True)
class Violation:
    category: str
    path: str
    scope: str
    target: str
    detail: str

    @property
    def fingerprint(self) -> str:
        raw = "|".join((self.category, self.path, self.scope, self.target))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]

    def serialized(self) -> dict:
        value = asdict(self)
        value["fingerprint"] = self.fingerprint
        return value


class PythonAudit(ast.NodeVisitor):
    def __init__(self, path: Path, relative: str, domain: str, registry: DomainRegistry):
        self.path = path
        self.relative = relative
        self.domain = domain
        self.registry = registry
        self.scope = "<module>"
        self.violations: list[Violation] = []

    def _add(self, category: str, target: str, detail: str) -> None:
        self.violations.append(Violation(category, self.relative, self.scope, target, detail))

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        old = self.scope
        self.scope = node.name
        self.generic_visit(node)
        self.scope = old

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._audit_import(alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self._audit_import(node.module)

    def _audit_import(self, module: str) -> None:
        if self.domain == "base" or not module.startswith("backend.") or self.registry.is_public_import(module):
            return
        self._add("internal_import", module, f"{self.domain} imports Base internal module {module}")

    def visit_Constant(self, node: ast.Constant) -> None:
        if not isinstance(node.value, str):
            return
        text = node.value
        tables = self.registry.tables_in(text)
        for table in sorted(tables):
            ownership = self.registry.table_owner(table)
            if ownership is None:
                self._add("unowned_table", table, f"no owner registered for {table}")
            elif ownership.runtime_domain != self.domain:
                self._add(
                    "cross_domain_sql",
                    table,
                    f"{self.domain} SQL accesses {ownership.owner}-owned table {table}",
                )
        if DDL_RE.search(text) and not self.registry.is_migration_path(self.relative):
            for target in sorted(tables) or ["<unknown>"]:
                self._add("runtime_ddl", target, "DDL is only allowed in versioned migration files")
        source_match = CREATE_TABLE_RE.search(text)
        if source_match:
            source_owner = self.registry.table_owner(source_match.group(1))
            for target in REFERENCE_RE.findall(text):
                target_owner = self.registry.table_owner(target)
                if source_owner and target_owner and source_owner.owner != target_owner.owner:
                    self._add(
                        "cross_domain_foreign_key",
                        f"{source_match.group(1)}->{target.lower()}",
                        "cross-domain foreign keys are forbidden",
                    )


    def visit_Expr(self, node: ast.Expr) -> None:
        # Docstrings are descriptive text, not executable SQL.
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return
        self.generic_visit(node)

def audit_repository(root: Path, registry: DomainRegistry) -> tuple[list[Violation], list[str]]:
    violations: list[Violation] = []
    tables: set[str] = set()
    ignored_dirs = {".git", "dist", "node_modules", "__pycache__", ".venv", "venv"}
    for path in root.rglob("*.py"):
        if any(part in ignored_dirs for part in path.parts):
            continue
        relative = path.relative_to(root).as_posix()
        if "/tests/" in f"/{relative}":
            continue
        domain = registry.source_domain(relative)
        if not domain:
            continue
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text, filename=relative)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            violations.append(Violation("scan_error", relative, "<module>", type(exc).__name__, str(exc)))
            continue
        tables.update(registry.tables_in(text))
        if registry.is_non_runtime_path(relative):
            continue
        visitor = PythonAudit(path, relative, domain, registry)
        visitor.visit(tree)
        violations.extend(visitor.violations)

    for path in root.rglob("*.sql"):
        if any(part in ignored_dirs for part in path.parts):
            continue
        relative = path.relative_to(root).as_posix()
        if "/tests/" in f"/{relative}":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        found = registry.tables_in(text)
        tables.update(found)
        for table in sorted(found):
            if registry.table_owner(table) is None:
                violations.append(Violation("unowned_table", relative, "<sql>", table, "no owner registered"))

    unique = {v.fingerprint: v for v in violations}
    return sorted(unique.values(), key=lambda v: (v.category, v.path, v.scope, v.target)), sorted(tables)


def load_baseline(path: Path) -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {item["fingerprint"] if isinstance(item, dict) else item for item in data.get("violations", [])}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--baseline", type=Path, default=REPO_ROOT / "backend/governance/boundary_baseline.json")
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    registry = load_registry(args.registry)
    violations, tables = audit_repository(args.root.resolve(), registry)
    unowned = registry.validate_tables(tables)
    payload = {
        "registry_version": registry.version,
        "table_count": len(tables),
        "tables": [
            {
                "table": table,
                "owner": registry.table_owner(table).owner if registry.table_owner(table) else None,
                "runtime_domain": registry.table_owner(table).runtime_domain if registry.table_owner(table) else None,
            }
            for table in tables
        ],
        "violations": [item.serialized() for item in violations],
    }
    if args.inventory:
        args.inventory.parent.mkdir(parents=True, exist_ok=True)
        inventory = {k: payload[k] for k in ("registry_version", "table_count", "tables")}
        args.inventory.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.write_baseline:
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        baseline = {"registry_version": registry.version, "violations": payload["violations"]}
        args.baseline.write_text(json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    baseline = load_baseline(args.baseline)
    current = {item.fingerprint for item in violations}
    new = sorted(current - baseline)
    resolved = sorted(baseline - current)
    summary = {
        "tables": len(tables),
        "unowned_tables": unowned,
        "violations": len(violations),
        "new_violations": len(new),
        "resolved_baseline_items": len(resolved),
    }
    if args.json:
        print(json.dumps({"summary": summary, **payload}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(summary, ensure_ascii=False))
        for item in violations:
            if item.fingerprint in new:
                print(f"NEW {item.category} {item.path}:{item.scope} -> {item.target}: {item.detail}")
    return 1 if unowned or new else 0


if __name__ == "__main__":
    raise SystemExit(main())

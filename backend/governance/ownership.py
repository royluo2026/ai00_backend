from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

TABLE_RE = re.compile(r"\bworkmanship_[a-z0-9_]+\b", re.IGNORECASE)


class OwnershipError(ValueError):
    pass


@dataclass(frozen=True)
class TableOwnership:
    table: str
    owner: str
    runtime_domain: str


class DomainRegistry:
    def __init__(self, data: dict):
        self.data = data
        self.version = int(data["version"])
        self.product_domains = tuple(data["product_domains"])
        self.data_owners = data["data_owners"]
        self.source_roots = tuple(data["source_roots"])
        self.source_overrides = tuple(data.get("source_overrides", ()))
        self.public_import_prefixes = tuple(data.get("public_import_prefixes", ()))
        self.migration_paths = tuple(data.get("migration_paths", ()))
        self.non_runtime_paths = tuple(data.get("non_runtime_paths", ()))
        self.ignored_identifiers = frozenset(data.get("ignored_identifiers", ()))
        self.table_prefix_owners = tuple(data.get("table_prefix_owners", ()))
        self.table_overrides = data.get("table_overrides", {})
        self.migration_owner_overrides = data.get("migration_owner_overrides", {})
        self.migration_table_exceptions = data.get("migration_table_exceptions", {})
        self._validate()

    def _validate(self) -> None:
        known = set(self.data_owners)
        missing = set(self.product_domains) - known
        if missing:
            raise OwnershipError(f"product domains missing data-owner definitions: {sorted(missing)}")
        for owner, config in self.data_owners.items():
            if config["runtime_domain"] not in self.product_domains:
                raise OwnershipError(f"{owner} has invalid runtime_domain")
        for rule in self.source_overrides:
            if rule.get("domain") not in self.product_domains or not rule.get("path"):
                raise OwnershipError(f"invalid source override: {rule}")
        for rule in self.table_prefix_owners:
            if rule["owner"] not in known:
                raise OwnershipError(f"unknown owner in prefix rule: {rule}")
        for table, owner in self.table_overrides.items():
            if owner not in known or not TABLE_RE.fullmatch(table):
                raise OwnershipError(f"invalid table override: {table}={owner}")
        for migration_id, owner in self.migration_owner_overrides.items():
            if not re.fullmatch(r"\d{12}", migration_id) or owner not in known:
                raise OwnershipError(f"invalid migration owner override: {migration_id}={owner}")
        for migration_id, exception in self.migration_table_exceptions.items():
            tables = exception.get("tables", ())
            reason = exception.get("reason", "")
            if (not re.fullmatch(r"\d{12}", migration_id)
                    or not tables
                    or any(not TABLE_RE.fullmatch(table) for table in tables)
                    or not isinstance(reason, str)
                    or len(reason.strip()) < 40):
                raise OwnershipError(f"invalid migration table exception: {migration_id}")

    def source_domain(self, relative_path: str | Path) -> str | None:
        normalized = Path(relative_path).as_posix().lstrip("./")
        for rule in self.source_overrides:
            if normalized == rule["path"]:
                return rule["domain"]
        for rule in self.source_roots:
            root = rule["path"].rstrip("/")
            if normalized == root or normalized.startswith(root + "/"):
                return rule["domain"]
        return None

    def table_owner(self, table: str) -> TableOwnership | None:
        table = table.lower()
        if table in self.ignored_identifiers:
            return None
        owner = self.table_overrides.get(table)
        if owner is None:
            matches = [r["owner"] for r in self.table_prefix_owners if table.startswith(r["prefix"])]
            if len(matches) > 1 and len(set(matches)) > 1:
                raise OwnershipError(f"ambiguous owner for {table}: {matches}")
            owner = matches[0] if matches else None
        if owner is None:
            return None
        return TableOwnership(table, owner, self.data_owners[owner]["runtime_domain"])

    def tables_in(self, text: str) -> set[str]:
        return {match.lower() for match in TABLE_RE.findall(text) if match.lower() not in self.ignored_identifiers}

    def validate_tables(self, tables: Iterable[str]) -> list[str]:
        return sorted({table for table in tables if self.table_owner(table) is None})

    def migration_owner(self, migration_id: str, declared_domain: str) -> str:
        """Resolve immutable legacy filenames to their reviewed first-class owner."""
        return self.migration_owner_overrides.get(migration_id, declared_domain)

    def migration_allows_table(self, migration_id: str, table: str) -> bool:
        exception = self.migration_table_exceptions.get(migration_id, {})
        return table in exception.get("tables", ())

    def is_migration_path(self, relative_path: str | Path) -> bool:
        normalized = Path(relative_path).as_posix().lstrip("./")
        return any(normalized == root or normalized.startswith(root.rstrip("/") + "/") for root in self.migration_paths)

    def is_non_runtime_path(self, relative_path: str | Path) -> bool:
        normalized = Path(relative_path).as_posix().lstrip("./")
        return any(normalized == root or normalized.startswith(root.rstrip("/") + "/") for root in self.non_runtime_paths)

    def is_public_import(self, module: str) -> bool:
        return any(module == prefix or module.startswith(prefix + ".") for prefix in self.public_import_prefixes)


def load_registry(path: str | Path | None = None) -> DomainRegistry:
    registry_path = Path(path) if path else Path(__file__).with_name("domain_boundaries.json")
    return DomainRegistry(json.loads(registry_path.read_text(encoding="utf-8")))

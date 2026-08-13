from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    data_type: str
    nullable: bool
    default: str | None = None
    extra: str = ""
    sources: tuple[str, ...] = ()

    def structural_key(self) -> tuple[object, ...]:
        return (self.name, self.data_type, self.nullable, self.default, self.extra)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name, "data_type": self.data_type,
            "nullable": self.nullable, "default": self.default,
            "extra": self.extra, "sources": list(self.sources),
        }


@dataclass(frozen=True)
class IndexSpec:
    name: str
    columns: tuple[str, ...]
    unique: bool = False
    primary: bool = False
    sources: tuple[str, ...] = ()

    def structural_key(self) -> tuple[object, ...]:
        return (self.name, self.columns, self.unique, self.primary)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name, "columns": list(self.columns),
            "unique": self.unique, "primary": self.primary,
            "sources": list(self.sources),
        }


@dataclass(frozen=True)
class ConstraintSpec:
    name: str
    kind: str
    columns: tuple[str, ...] = ()
    referenced_table: str | None = None
    referenced_columns: tuple[str, ...] = ()
    expression: str | None = None
    sources: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name, "kind": self.kind, "columns": list(self.columns),
            "referenced_table": self.referenced_table,
            "referenced_columns": list(self.referenced_columns),
            "expression": self.expression, "sources": list(self.sources),
        }


@dataclass(frozen=True)
class TableSpec:
    name: str
    owner: str
    runtime_domain: str
    legacy_name: bool
    columns: tuple[ColumnSpec, ...] = ()
    indexes: tuple[IndexSpec, ...] = ()
    constraints: tuple[ConstraintSpec, ...] = ()
    sources: tuple[str, ...] = ()

    def require_column(self, name: str) -> ColumnSpec:
        return next(column for column in self.columns if column.name == name)

    def require_index(self, name: str) -> IndexSpec:
        return next(index for index in self.indexes if index.name == name)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name, "owner": self.owner,
            "runtime_domain": self.runtime_domain, "legacy_name": self.legacy_name,
            "columns": [item.to_dict() for item in self.columns],
            "indexes": [item.to_dict() for item in self.indexes],
            "constraints": [item.to_dict() for item in self.constraints],
            "sources": list(self.sources),
        }


@dataclass(frozen=True)
class ExpectedSchema:
    tables: tuple[TableSpec, ...]
    schema_version: int = 1
    isolation_profile: str = "single_database_domain_tables"
    database_name: str = "ai00_test"
    schema_sha256: str = field(init=False)

    def __post_init__(self):
        payload = {"tables": [table.to_dict() for table in self.tables]}
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        object.__setattr__(self, "schema_sha256", "sha256:" + digest)

    def require_table(self, name: str) -> TableSpec:
        return next(table for table in self.tables if table.name == name)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "isolation_profile": self.isolation_profile,
            "database_name": self.database_name,
            "schema_sha256": self.schema_sha256,
            "tables": [table.to_dict() for table in self.tables],
        }

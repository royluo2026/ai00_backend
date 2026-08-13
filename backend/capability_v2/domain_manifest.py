"""Immutable declarations for independently maintained official domains."""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import Field, model_validator

from .catalog import ProviderArtifact
from .contracts import FrozenModel


DOMAIN_ID_PATTERN = r"^[a-z][a-z0-9_]{1,63}$"
CAPABILITY_ID_PATTERN = r"^[a-z][a-z0-9_.]{2,127}$"


def _require_repository_relative_posix_path(value: str, *, field_name: str) -> None:
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or path.is_absolute()
        or path == PurePosixPath(".")
        or ".." in path.parts
    ):
        raise ValueError(f"{field_name} must be a repository-relative POSIX path")


class DomainDatabaseManifest(FrozenModel):
    database_name: str = Field(pattern=r"^ai00_[a-z][a-z0-9_]{1,62}$")
    runtime_url_env: str = Field(pattern=r"^AI00_[A-Z0-9_]+_DB_URL$")
    ddl_url_env: str = Field(pattern=r"^AI00_[A-Z0-9_]+_DDL_DB_URL$")
    migration_path: str
    schema_paths: tuple[str, ...]

    @model_validator(mode="after")
    def validate_migration_path(self) -> "DomainDatabaseManifest":
        _require_repository_relative_posix_path(
            self.migration_path,
            field_name="migration_path",
        )
        if not self.schema_paths:
            raise ValueError("schema_paths must not be empty")
        for path in self.schema_paths:
            _require_repository_relative_posix_path(path, field_name="schema_paths")
        if len(self.schema_paths) != len(set(self.schema_paths)):
            raise ValueError("duplicate schema_paths")
        if self.migration_path not in self.schema_paths:
            raise ValueError("schema_paths must include migration_path")
        return self


class CapabilityExportManifest(FrozenModel):
    capability_id: str = Field(pattern=CAPABILITY_ID_PATTERN)
    major_version: int = Field(ge=1)


class EventSubscriptionManifest(FrozenModel):
    subscription_id: str = Field(pattern=CAPABILITY_ID_PATTERN)
    producer_domain: str = Field(pattern=DOMAIN_ID_PATTERN)
    event_type: str = Field(
        pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$"
    )
    min_version: int = Field(ge=1)
    max_version: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_version_range(self) -> "EventSubscriptionManifest":
        if self.min_version > self.max_version:
            raise ValueError("min_version must not exceed max_version")
        return self


class DomainManifest(FrozenModel):
    domain_id: str = Field(pattern=DOMAIN_ID_PATTERN)
    artifact: ProviderArtifact
    artifact_path: str
    allowed_owners: tuple[str, ...]
    database: DomainDatabaseManifest
    search_export: CapabilityExportManifest | None = None
    event_subscriptions: tuple[EventSubscriptionManifest, ...] = ()

    @model_validator(mode="after")
    def validate_domain_contract(self) -> "DomainManifest":
        _require_repository_relative_posix_path(
            self.artifact_path,
            field_name="artifact_path",
        )
        if self.domain_id not in self.allowed_owners:
            raise ValueError("allowed_owners must include domain_id")
        subscription_ids = [item.subscription_id for item in self.event_subscriptions]
        if len(subscription_ids) != len(set(subscription_ids)):
            raise ValueError("duplicate subscription_id in domain manifest")
        return self


class DomainManifestSet(FrozenModel):
    schema_version: Literal[1]
    domains: tuple[DomainManifest, ...]

    @model_validator(mode="after")
    def validate_unique_domain_resources(self) -> "DomainManifestSet":
        self._require_unique(
            [item.domain_id for item in self.domains],
            resource_name="domain_id",
        )
        self._require_unique(
            [item.artifact.plugin_id for item in self.domains],
            resource_name="plugin_id",
        )
        self._require_unique(
            [item.database.database_name for item in self.domains],
            resource_name="database_name",
        )
        self._require_unique(
            [path for item in self.domains for path in item.database.schema_paths],
            resource_name="schema_path",
        )
        return self

    @staticmethod
    def _require_unique(values: list[str], *, resource_name: str) -> None:
        seen: set[str] = set()
        for value in values:
            if value in seen:
                raise ValueError(f"duplicate {resource_name}: {value}")
            seen.add(value)

    def require(self, domain_id: str) -> DomainManifest:
        for manifest in self.domains:
            if manifest.domain_id == domain_id:
                return manifest
        raise KeyError(f"unknown domain_id: {domain_id}")


def load_domain_manifests(path: Path) -> DomainManifestSet:
    """Load and validate a versioned official-domain manifest document."""

    document = json.loads(path.read_text(encoding="utf-8"))
    return DomainManifestSet.model_validate(document)

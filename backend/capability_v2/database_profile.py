"""Explicit, secret-free database deployment profiles."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .contracts import FrozenModel
from .domain_manifest import DomainManifestSet


IsolationProfile = Literal[
    "database_per_domain",
    "single_database_domain_tables",
]


class DatabaseDeploymentProfile(FrozenModel):
    schema_version: Literal[1]
    profile_id: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    isolation_profile: IsolationProfile
    database_name: str = Field(pattern=r"^ai00_[a-z][a-z0-9_]{1,62}$")
    runtime_url_env: str = Field(pattern=r"^AI00_[A-Z0-9_]+_DB_URL$")
    domains: tuple[str, ...]

    @model_validator(mode="after")
    def validate_domains(self) -> "DatabaseDeploymentProfile":
        if len(self.domains) != len(set(self.domains)):
            raise ValueError("duplicate profile domain")
        if tuple(sorted(self.domains)) != self.domains:
            raise ValueError("profile domains must be sorted")
        return self


def load_database_profile(
    path: Path,
    manifests: DomainManifestSet,
) -> DatabaseDeploymentProfile:
    document = json.loads(path.read_text(encoding="utf-8"))
    profile = DatabaseDeploymentProfile.model_validate(document)
    expected = tuple(sorted(item.domain_id for item in manifests.domains))
    if profile.domains != expected:
        raise ValueError("domain_coverage_mismatch")
    return profile


__all__ = [
    "DatabaseDeploymentProfile",
    "IsolationProfile",
    "load_database_profile",
]

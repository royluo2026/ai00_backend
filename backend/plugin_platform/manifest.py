"""Strict Manifest v2 parser. Third-party executable backend code is forbidden."""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


PLUGIN_ID = re.compile(r"^[a-z][a-z0-9]*(?:\.[a-z][a-z0-9-]*){2,7}$")
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
CAPABILITY = re.compile(r"^[a-z][a-z0-9_.-]{2,127}$")


class ManifestError(ValueError):
    pass


class Compatibility(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform_api: str = Field(min_length=1, max_length=64)
    web_sdk: str = Field(min_length=1, max_length=64)


class WebRuntime(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entry: str = Field(min_length=1, max_length=512)
    sandbox: Literal["allow-scripts"] = "allow-scripts"

    @field_validator("entry")
    @classmethod
    def safe_entry(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        if normalized.startswith(("/", "http://", "https://")) or ".." in normalized.split("/"):
            raise ValueError("web entry must be a package-relative path")
        return normalized


class Artifact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    object_key: str = Field(min_length=1, max_length=1024)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(gt=0, le=100 * 1024 * 1024)
    media_type: Literal["application/zip"] = "application/zip"


class DataPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stores_personal_data: bool = False
    retention: Literal["none", "while-installed", "tenant-policy"] = "none"
    uninstall: Literal["delete", "retain", "export-then-delete"] = "delete"


class CapabilityRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}$")
    major: int = Field(ge=1, le=2147483647)


class CapabilityRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    required: tuple[CapabilityRequirement, ...] = ()
    optional: tuple[CapabilityRequirement, ...] = ()

    @model_validator(mode="after")
    def unique_requirements(self):
        required = {(item.id, item.major) for item in self.required}
        optional = {(item.id, item.major) for item in self.optional}
        if len(required) != len(self.required) or len(optional) != len(self.optional):
            raise ValueError("capability requirements must be unique")
        if required & optional:
            raise ValueError("a capability cannot be both required and optional")
        return self


class PluginManifestV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["2.0"]
    plugin_id: str
    publisher_id: str = Field(min_length=3, max_length=128)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    version: str
    compatibility: Compatibility
    runtimes: dict[Literal["web"], WebRuntime]
    permissions: tuple[str, ...] = ()
    capabilities: CapabilityRequirements = Field(default_factory=CapabilityRequirements)
    artifact: Artifact
    data: DataPolicy = Field(default_factory=DataPolicy)

    @field_validator("plugin_id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        if not PLUGIN_ID.fullmatch(value):
            raise ValueError("plugin_id must be reverse-DNS-like lowercase identity")
        return value

    @field_validator("version")
    @classmethod
    def valid_version(cls, value: str) -> str:
        if not SEMVER.fullmatch(value):
            raise ValueError("version must be SemVer")
        return value

    @field_validator("permissions")
    @classmethod
    def valid_permissions(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("permissions must be unique")
        if any(not CAPABILITY.fullmatch(value) for value in values):
            raise ValueError("permissions must contain capability ids only")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def publisher_owns_namespace(self):
        if not self.plugin_id.startswith(self.publisher_id + "."):
            raise ValueError("plugin_id must be within publisher namespace")
        if "web" not in self.runtimes:
            raise ValueError("first public version requires a web runtime")
        return self


def parse_manifest(value: dict[str, Any]) -> PluginManifestV2:
    forbidden = {"backend", "routers_module", "python", "executable", "entrypoint"}
    found: set[str] = set()

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if str(key).lower() in forbidden:
                    found.add(str(key))
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    if found:
        raise ManifestError(f"third-party executable declarations are forbidden: {', '.join(sorted(found))}")
    try:
        return PluginManifestV2.model_validate(value)
    except ValidationError as exc:
        raise ManifestError(str(exc)) from exc

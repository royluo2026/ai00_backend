"""Factory owns physical topology and resources, never BOP plan nodes."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PhysicalStructure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    gid: str
    kind: Literal["factory", "section", "line", "station"]
    name: str
    parent_gid: str | None = None
    version: int = Field(default=1, ge=1)
    archived: bool = False
    attributes: dict = Field(default_factory=dict)


class ResourceCatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    gid: str
    resource_type: Literal["equipment", "tool", "fixture"]
    name: str
    revision: int = Field(default=1, ge=1)
    status: Literal["draft", "published", "deprecated"] = "draft"
    specification: dict = Field(default_factory=dict)


class PhysicalAsset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    gid: str
    asset_no: str
    asset_type: Literal["equipment", "tool", "fixture"]
    catalog_gid: str | None = None
    status: Literal["in_use", "maintenance", "scrapped"] = "in_use"
    version: int = Field(default=1, ge=1)
    meta: dict = Field(default_factory=dict)


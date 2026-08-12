from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Connector(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    gid: str
    revision: int = Field(ge=1)
    name: str
    connector_type: str
    host: str
    port: int = Field(ge=1, le=65535)
    database_name: str
    username: str
    credential_ref: str
    status: str = "untested"


class MappingDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    gid: str
    revision: int = Field(ge=1)
    datasource_gid: str
    name: str
    source_object: str
    target_domain: str
    target_capability_id: str
    target_major_version: int = Field(ge=1)
    minimum_catalog_release: str
    field_mappings: tuple[dict, ...] = ()


from pydantic import BaseModel, ConfigDict, Field


class AgentResource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    resource_gid: str
    resource_type: str
    version: int = Field(ge=1)
    status: str
    content: dict = Field(default_factory=dict)

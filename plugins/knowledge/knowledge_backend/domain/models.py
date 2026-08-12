from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DocumentRevision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    gid: str
    document_gid: str
    revision_no: int
    immutable: bool = True


class PublicationEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    event_type: str = "knowledge.document.published.v1"
    subject_ref: str
    revision_ref: str


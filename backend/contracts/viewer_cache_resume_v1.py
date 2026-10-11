"""Main-owned resume of an existing frozen-cache native document."""
from pydantic import Field
from .viewer_interaction_v1 import ClosedModel, Gid, SignedGrant
from .viewer_open_completion_v1 import OpenBinding


class CacheResumeRequest(ClosedModel):
    workspace_gid: Gid
    document_gid: Gid
    identity_operation_id: str = Field(min_length=1, max_length=191)
    expected_document_session: str = Field(pattern=r'^sha256:[0-9a-f]{64}$')
    expected_workspace_row_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=191)
    session_nonce: str = Field(pattern=r'^[0-9a-f]{64}$')


class CacheResumeResult(ClosedModel):
    binding: OpenBinding
    grant: SignedGrant

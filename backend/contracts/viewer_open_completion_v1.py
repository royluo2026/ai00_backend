"""Main-owned completion request. Runtime identity comes only from signed launch evidence."""
from typing import Literal
from pydantic import Field
from .viewer_interaction_v1 import ClosedModel, Gid, Identity, SignedGrant


class OpenCompletionRequest(ClosedModel):
    workspace_gid: Gid
    document_gid: Gid
    launch_operation_id: str = Field(min_length=1, max_length=191)
    expected_workspace_row_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=191)
    session_nonce: str = Field(pattern=r'^[0-9a-f]{64}$')


class OpenBinding(ClosedModel):
    workspace_gid: Gid
    document_gid: Gid
    state: Literal['importing', 'bound']
    connector_device_id: Identity
    document_session: str = Field(pattern=r'^sha256:[0-9a-f]{64}$')
    workspace_row_version: int = Field(ge=1)
    cache_revision_hash: str = Field(pattern=r'^sha256:[0-9a-f]{64}$')
    source_association_id: Identity


class OpenCompletionResult(ClosedModel):
    binding: OpenBinding
    grant: SignedGrant

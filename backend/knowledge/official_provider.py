"""Transitional official Provider entry point for the Knowledge domain."""
from __future__ import annotations

from typing import Any

from backend.capabilities.knowledge_context_next import register_knowledge_context_capability
from backend.capabilities.knowledge_documents_next import register_knowledge_document_capabilities
from backend.capabilities.knowledge_migration_next import register_knowledge_migration_capabilities
from backend.capabilities.knowledge_next import register_knowledge_capabilities
from backend.capabilities.outbox_next import register_outbox_capability
from backend.capabilities.outbox_retry_next import register_retry_capability
from backend.capabilities.proposal_query_next import register_proposal_query_capabilities
from backend.capabilities.proposals_next import register_proposal_capability
from backend.capabilities.review_next import register_review_capability

def register_capabilities(registry: Any) -> None:
    register_knowledge_capabilities(registry)
    register_knowledge_document_capabilities(registry)
    register_knowledge_context_capability(registry)
    register_knowledge_migration_capabilities(registry)
    register_proposal_capability(registry)
    register_review_capability(registry)
    register_proposal_query_capabilities(registry)
    register_outbox_capability(registry)
    register_retry_capability(registry)


__all__ = ["register_capabilities"]

"""Official native Knowledge Provider entry point."""
from __future__ import annotations

from .knowledge_context_next import register_knowledge_context_capability
from .knowledge_documents_next import register_knowledge_document_capabilities
from .knowledge_migration_next import register_knowledge_migration_capabilities
from .knowledge_next import register_knowledge_capabilities
from .outbox_next import register_outbox_capability
from .outbox_retry_next import register_retry_capability
from .proposal_query_next import register_proposal_query_capabilities
from .proposals_next import register_proposal_capability
from .review_next import register_review_capability
from .reviewed import register_reviewed_capabilities
from .reference_data import register_reference_data_capabilities
from .resource_model_mapping import register_resource_model_mapping_capability
from backend.domain_ports.simulation_runtime import simulation_runtime_ports
from ..public_ports import KnowledgeResourceModelMappingAdapter


def register_capabilities(registry) -> None:
    simulation_runtime_ports.register(
        "knowledge.resource_model_mapping", KnowledgeResourceModelMappingAdapter(),
    )
    register_knowledge_capabilities(registry)
    register_knowledge_document_capabilities(registry)
    register_knowledge_context_capability(registry)
    register_knowledge_migration_capabilities(registry)
    register_proposal_capability(registry)
    register_review_capability(registry)
    register_proposal_query_capabilities(registry)
    register_outbox_capability(registry)
    register_retry_capability(registry)
    register_reviewed_capabilities(registry)
    register_reference_data_capabilities(registry)
    register_resource_model_mapping_capability(registry)


__all__ = ["register_capabilities"]

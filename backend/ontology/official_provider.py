"""Transitional official Provider entry point for the Ontology domain."""
from __future__ import annotations

from typing import Any

from backend.capabilities.ontology_concepts_next import register_ontology_concept_capabilities
from backend.capabilities.ontology_proposals_next import register_ontology_proposal_capabilities
from backend.capabilities.ontology_releases_next import register_ontology_release_capabilities

def register_capabilities(registry: Any) -> None:
    register_ontology_concept_capabilities(registry)
    register_ontology_proposal_capabilities(registry)
    register_ontology_release_capabilities(registry)


__all__ = ["register_capabilities"]

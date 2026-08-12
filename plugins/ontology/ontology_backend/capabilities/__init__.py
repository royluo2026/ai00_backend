from .ontology_concepts_next import register_ontology_concept_capabilities
from .ontology_proposals_next import register_ontology_proposal_capabilities
from .ontology_releases_next import register_ontology_release_capabilities
from ..provider import GovernedRegistry
from .reviewed import register_reviewed_capabilities


def register_capabilities(registry):
    governed = GovernedRegistry(registry)
    register_ontology_concept_capabilities(governed)
    register_ontology_proposal_capabilities(governed)
    register_ontology_release_capabilities(governed)
    register_reviewed_capabilities(governed)


__all__ = ["register_capabilities"]

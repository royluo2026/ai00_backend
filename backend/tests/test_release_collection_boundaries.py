from contextlib import nullcontext
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from backend.base.contracts import OUTPUT_SCHEMAS
from plugins.agent.agent_backend.orchestration.models import MAX_GRAPH_NODES
from plugins.agent.agent_backend.orchestration.workspace_model import Variant
from plugins.ontology.ontology_backend.capabilities.ontology_proposals_next import REVIEWABLE_PROPOSAL_SCHEMA
from plugins.ontology.ontology_backend.capabilities.ontology_releases_next import RELEASE_SEARCH_SCHEMA
from plugins.ontology.ontology_backend.proposals import OntologyProposalRepository, ProposalIntegrityError


def test_environment_collections_match_runtime_limits():
    options = OUTPUT_SCHEMAS['base.runtime.data_environment.get']['properties']['options']
    assert options['maxItems'] == 3
    assert options['items']['properties']['reasons']['maxItems'] == 30


def test_variant_active_nodes_are_bounded_by_graph_capacity():
    values = dict(gid='v', task_gid='t', stage_ref='s')
    assert len(Variant(**values, active_node_gids=['n'] * MAX_GRAPH_NODES).active_node_gids) == MAX_GRAPH_NODES
    with pytest.raises(ValidationError):
        Variant(**values, active_node_gids=['n'] * (MAX_GRAPH_NODES + 1))


def test_ontology_search_and_review_contracts_are_bounded():
    assert RELEASE_SEARCH_SCHEMA['properties']['items']['maxItems'] == 100
    assert REVIEWABLE_PROPOSAL_SCHEMA['properties']['reviews']['maxItems'] == 1000


def test_review_overflow_is_rejected_instead_of_hiding_review_decisions():
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.fetchall.return_value = [{'review_gid': str(i)} for i in range(1001)]
    connection = MagicMock()
    connection.cursor.return_value = cursor
    repository = OntologyProposalRepository(lambda: nullcontext(connection))
    with pytest.raises(ProposalIntegrityError, match='review collection exceeds'):
        repository.list_reviews('p', 'r')
    assert 'LIMIT %s' in cursor.execute.call_args.args[0]
    assert cursor.execute.call_args.args[1] == ('p', 'r', 1001)


@pytest.mark.parametrize('capability_id,codes', [
    ('knowledge.source.pull', {'knowledge_source_limit_exceeded', 'knowledge_source_cycle'}),
    ('knowledge.source.snapshot.get', {'knowledge_source_limit_exceeded'}),
    ('knowledge.source.catalog.sync', {'knowledge_catalog_limit_exceeded'}),
    ('knowledge.source.import.preview', {'knowledge_source_conflict_limit_exceeded'}),
])
def test_knowledge_overflow_errors_are_declared(capability_id, codes):
    from backend.capabilities.models_next import CapabilitySpec
    from plugins.knowledge.knowledge_backend.provider import descriptor_for
    descriptor = descriptor_for(CapabilitySpec(id=capability_id, owner='knowledge'))
    assert codes <= {error.code for error in descriptor.domain_errors}


def test_review_overflow_has_a_governed_error(monkeypatch):
    from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityOutput
    from plugins.ontology.ontology_backend.capabilities import ontology_proposals_next as module
    repository = MagicMock()
    from plugins.ontology.ontology_backend.proposals import ProposalReviewLimitExceeded
    repository.list_reviews.side_effect = ProposalReviewLimitExceeded('review collection exceeds the bounded proposal contract')
    monkeypatch.setattr(module, 'get_proposal', lambda *args: CapabilityOutput(data={'proposal_gid':'p','proposal_revision_gid':'r'}))
    monkeypatch.setattr(module, 'OntologyProposalRepository', lambda: repository)
    with pytest.raises(CapabilityBusinessError) as caught:
        module.get_reviewable_proposal({}, None)
    assert caught.value.code == 'proposal_review_limit_exceeded'

"""Workspace reads must accept node types already persisted by BOP adoption."""
import pytest
from backend.capabilities.validation_next import validate_payload
from plugins.simulation.simulation_backend.capabilities.workspaces import candidate_specs


def specs():
    return {spec.id: spec for spec, _ in candidate_specs()}


@pytest.mark.parametrize('node_type', [
    'part', 'standard_part', 'non_standard_part', 'support_material',
    'tool_need', 'fixture_need', 'equipment_need',
])
def test_workspace_get_accepts_adopted_bop_part_and_resource_nodes(node_type):
    schema = specs()['simulation.environment.workspace.get'].output_schema['properties']['nodes']['items']
    validate_payload(schema, {
        'node_gid': '233854993277554689', 'parent_gid': '233854993277554688',
        'node_type': node_type, 'name': 'BOP source node', 'position': 0, 'row_version': 1,
    }, label='output.nodes[1153]')


def test_workspace_get_still_rejects_unknown_node_types():
    schema = specs()['simulation.environment.workspace.get'].output_schema['properties']['nodes']['items']
    with pytest.raises(ValueError, match='not an allowed value'):
        validate_payload(schema, {
            'node_gid': '1', 'parent_gid': None, 'node_type': 'unregistered_node',
            'name': 'invalid', 'position': 0, 'row_version': 1,
        }, label='output.nodes[0]')

def test_workspace_manual_creation_does_not_accept_imported_part_nodes():
    schema = specs()['simulation.environment.structure_node.create'].input_schema
    with pytest.raises(ValueError, match='not an allowed value'):
        validate_payload(schema, {
            'workspace_gid': '1', 'expected_row_version': 1, 'idempotency_key': 'create-part',
            'node_type': 'part', 'name': 'imported-only',
        }, label='input')

import pytest

from plugins.craft.craft_backend.services.tc_import_hierarchy import existing_label_index, resolve_parent


def test_existing_child_edge_disambiguates_duplicate_parent_fingerprints():
    parents = [dict(gid=gid, node_type='operation', title='Same') for gid in ['a', 'b']]
    child = dict(gid='c', parent_gid='b', parent_bop_title='OP/02', node_type='part')
    labels = existing_label_index(parents + [child], [dict(node_type='operation', title='Same', bom_row_label='OP/02')])
    assert resolve_parent('OP/02', labels) == 'b'


def test_full_revision_is_exact_and_ambiguous_short_label_is_rejected():
    labels = {'OP/01': {'a'}, 'OP/02': {'b'}}
    assert resolve_parent('OP/02', labels) == 'b'
    with pytest.raises(ValueError, match='ambiguous'):
        resolve_parent('OP', labels)
    with pytest.raises(ValueError, match='missing'):
        resolve_parent('ABSENT', labels)
    with pytest.raises(ValueError, match='missing'):
        resolve_parent('OP/03', {'OP/02': {'b'}})


def test_child_edge_to_absent_parent_does_not_create_a_candidate():
    labels = existing_label_index([dict(gid='c', parent_gid='deleted', parent_bop_title='OP/02')], [])
    with pytest.raises(ValueError, match='missing'):
        resolve_parent('OP/02', labels)

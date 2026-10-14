from plugins.project_management.project_management_backend.domain.models import apply_line_change, OrgManagementError
import pytest


def test_sync_uses_lineage_preserves_people_and_manual_identity():
    meta = {'org_management': {'revision': 3, 'lines': [
        {'gid': 'manual', 'name': '旧名', 'leader_user_gids': ['u1'], 'bop_line_gid': 'v1-line'}]}}
    result, changed = apply_line_change(meta, operation='managed_line.sync',
        arguments={'bop_lines': [{'gid': 'v2-line', 'title': '新名', 'ancestor_gids': ['v1-line']}]},
        expected_revision=3, new_gid=lambda: 'unused')
    assert result['org_management']['lines'] == [
        {'gid': 'manual', 'name': '旧名', 'leader_user_gids': ['u1'], 'bop_line_gid': 'v2-line'}]
    assert changed['lines'][0]['gid'] == 'manual'


def test_bulk_assignment_adds_people_without_replacing_existing_leaders():
    lines = [{'gid': gid, 'name': gid, 'leader_user_gids': ['old'], 'bop_line_gid': None} for gid in ['a', 'b']]
    meta = {'org_management': {'revision': 1, 'lines': lines}}
    result, changed = apply_line_change(meta, operation='managed_line.assign',
        arguments={'line_gids': ['a', 'b'], 'leader_user_gids': ['new']}, expected_revision=1, new_gid=lambda: 'x')
    assert result['org_management']['revision'] == 2
    assert all(line['leader_user_gids'] == ['new', 'old'] for line in changed['lines'])
    with pytest.raises(OrgManagementError):
        apply_line_change(meta, operation='managed_line.assign', arguments={'line_gids': ['a', 'missing'], 'leader_user_gids': ['new']}, expected_revision=1, new_gid=lambda: 'x')
    assert meta['org_management']['lines'][0]['leader_user_gids'] == ['old']


def test_sync_does_not_match_same_title_and_rejects_ambiguous_lineage():
    meta = {'org_management': {'revision': 0, 'lines': [
        {'gid': 'manual', 'name': 'A', 'leader_user_gids': ['u'], 'bop_line_gid': 'old'}]}}
    result, _ = apply_line_change(meta, operation='managed_line.sync',
        arguments={'bop_lines': [{'gid': 'different', 'title': 'A', 'ancestor_gids': []}]}, expected_revision=0, new_gid=lambda: 'new')
    assert len(result['org_management']['lines']) == 2
    assert next(x for x in result['org_management']['lines'] if x['gid'] == 'new')['leader_user_gids'] == []
    with pytest.raises(OrgManagementError):
        apply_line_change(meta, operation='managed_line.sync', arguments={'bop_lines': [
            {'gid': 'one', 'title': 'A', 'ancestor_gids': ['old']},
            {'gid': 'two', 'title': 'B', 'ancestor_gids': ['old']}]}, expected_revision=0, new_gid=lambda: 'new')


def test_sync_reprojects_current_mapping_to_recover_a_previous_failure():
    meta = {'org_management': {'revision': 1, 'lines': [
        {'gid': 'manual', 'name': 'A', 'leader_user_gids': ['u'], 'bop_line_gid': 'current'}]}}
    _, changed = apply_line_change(meta, operation='managed_line.sync',
        arguments={'bop_lines': [{'gid': 'current', 'title': 'A', 'ancestor_gids': []}]}, expected_revision=1, new_gid=lambda: 'unused')
    assert changed['lines'][0]['leader_user_gids'] == ['u']
